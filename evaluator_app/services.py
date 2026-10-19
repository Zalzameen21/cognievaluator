import datetime
from django.utils import timezone
from .models import BatchSyllabus, BatchTaskSchedule, SyllabusTask


def generate_batch_schedule(batch_syllabus):
    """
    Generate or update the task schedule for a batch based on its assigned syllabus.

    Assignment logic:
    - Finds the actual class days for the batch (e.g. only Wednesday for a weekly batch).
    - Assigns Task 1 to the first class session on or after start_date,
      Task 2 to the second class session, and so on.
    - Each task covers exactly ONE class session (one day).
    - Non-rescheduled entries are cleared and regenerated each time.
    - Rescheduled entries (is_rescheduled=True) are left untouched.
    """
    batch = batch_syllabus.batch
    syllabus = batch_syllabus.syllabus
    start_date = batch_syllabus.start_date

    # Parse class days from batch.class_days string (e.g. "Wednesday" or "Monday, Wednesday, Friday")
    DAYS_MAP = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    class_days_str = batch.class_days.lower()
    # Sort weekdays in weekly order so we iterate through days correctly
    valid_weekdays = sorted([v for k, v in DAYS_MAP.items() if k in class_days_str])

    if not valid_weekdays:
        valid_weekdays = [0, 1, 2, 3, 4]  # Fallback: Mon-Fri

    tasks = list(syllabus.tasks.order_by('order'))
    if not tasks:
        return

    # If this batch was split from a parent batch, exclude tasks already covered in parent before split_date
    if batch.parent_batch and batch.split_date:
        covered_task_ids = set(BatchTaskSchedule.objects.filter(
            batch=batch.parent_batch,
            date__lt=batch.split_date,
            syllabus_task__isnull=False
        ).values_list('syllabus_task_id', flat=True))
        remaining_tasks = [t for t in tasks if t.id not in covered_task_ids]
        if remaining_tasks:
            tasks = remaining_tasks

    # Delete existing NON-rescheduled schedules to regenerate cleanly
    BatchTaskSchedule.objects.filter(
        batch=batch,
        is_rescheduled=False
    ).delete()

    # Build the list of actual upcoming class dates (one per session)
    # We need at least len(tasks) sessions to schedule all tasks
    class_dates = []
    check_date = start_date
    # Scan up to 2 years ahead to find enough sessions
    max_days_to_scan = 365 * 2

    for _ in range(max_days_to_scan):
        if check_date.weekday() in valid_weekdays:
            class_dates.append(check_date)
            if len(class_dates) >= len(tasks):
                break
        check_date += datetime.timedelta(days=1)

    # Assign each task to its corresponding class session date
    for task, class_date in zip(tasks, class_dates):
        # Skip if there's already a manually rescheduled entry on this date
        if BatchTaskSchedule.objects.filter(batch=batch, date=class_date, is_rescheduled=True).exists():
            continue
        BatchTaskSchedule.objects.update_or_create(
            batch=batch,
            date=class_date,
            defaults={
                'syllabus_task': task,
                'custom_task_title': '',
                'custom_task_description': '',
                'is_rescheduled': False,
            }
        )

    # Automatically generate/sync student tasks based on the generated schedule
    sync_student_tasks_for_batch(batch, batch_syllabus.assigned_by)


def get_task_for_batch_date(batch, date):
    """
    Returns the BatchTaskSchedule for a batch on a specific date, or None.
    """
    return BatchTaskSchedule.objects.filter(batch=batch, date=date).first()

def sync_student_tasks_for_batch(batch, user=None):
    from .models import StudentTask, BatchTaskSchedule
    import datetime
    
    students = batch.students.all()
    # Order schedules by date so we can find the next date easily
    schedules = list(BatchTaskSchedule.objects.filter(batch=batch).order_by('date'))
    
    # Parse class days for fallback (last task)
    DAYS_MAP = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    class_days_str = batch.class_days.lower()
    valid_weekdays = sorted([v for k, v in DAYS_MAP.items() if k in class_days_str])
    if not valid_weekdays:
        valid_weekdays = [0, 1, 2, 3, 4]
        
    for i, schedule in enumerate(schedules):
        title = schedule.syllabus_task.title if schedule.syllabus_task else schedule.custom_task_title
        description = schedule.syllabus_task.description if schedule.syllabus_task else schedule.custom_task_description
        date = schedule.date
        
        # Calculate due_date as the date of the next scheduled task
        if i + 1 < len(schedules):
            due_date = schedules[i+1].date
        else:
            # For the last task, find the next class date
            due_date = date
            check_date = date + datetime.timedelta(days=1)
            for _ in range(14):
                if check_date.weekday() in valid_weekdays:
                    due_date = check_date
                    break
                check_date += datetime.timedelta(days=1)
        
        for student in students:
            task, created = StudentTask.objects.get_or_create(
                student=student,
                batch=batch,
                title=title,
                defaults={
                    'description': description,
                    'assigned_date': date,
                    'due_date': due_date,
                    'assigned_by': user,
                    'status': 'PENDING'
                }
            )
            # If the schedule changed (e.g. date shifted), update the student's task date
            if not created and (task.assigned_date != date or task.due_date != due_date):
                task.assigned_date = date
                if not task.completed_at:  # Only update due date if not yet completed
                    task.due_date = due_date
                task.save()


def auto_mark_absent_for_past_days(user_batches=None):
    """
    Checks past class days up to yesterday for the given batches.
    If a student was supposed to have a class but has no attendance record, 
    they are automatically marked as ABSENT.
    """
    from .models import Batch, Attendance, BatchScheduleException
    import datetime
    from django.utils import timezone

    today = timezone.now().date()
    
    if user_batches is not None:
        batches = user_batches.filter(status='ACTIVE')
    else:
        batches = Batch.objects.filter(status='ACTIVE')
        
    for batch in batches:
        start_date = batch.start_date
        if not start_date:
            continue
            
        DAYS_MAP = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        class_days_str = batch.class_days.lower()
        valid_weekdays = [v for k, v in DAYS_MAP.items() if k in class_days_str]
        
        if not valid_weekdays:
            continue
            
        students = list(batch.students.filter(status='ACTIVE'))
        if not students:
            continue
            
        check_date = start_date
        
        # Prevent massive loop if start date is extremely old, cap to 60 days
        limit_date = today - datetime.timedelta(days=60)
        if check_date < limit_date:
            check_date = limit_date
            
        while check_date < today:
            if check_date.weekday() in valid_weekdays:
                actual_date = check_date
                exception = BatchScheduleException.objects.filter(batch=batch, original_date=check_date).first()
                if exception:
                    if exception.rescheduled_date:
                        actual_date = exception.rescheduled_date
                    else:
                        actual_date = None
                        
                if actual_date and actual_date < today:
                    # If this actual_date is a rescheduled makeup date, verify original date didn't already have records
                    existing_student_ids = set(Attendance.objects.filter(student__in=students, date=actual_date).values_list('student_id', flat=True))
                    
                    # Also respect student batch transfer effective date
                    # A student is only eligible for this batch on actual_date if:
                    # 1) join_date <= actual_date
                    # 2) Not transferred into this batch on a date AFTER actual_date
                    # 3) If transferred from another batch, transfer effective_date <= actual_date
                    eligible_students = []
                    for s in students:
                        # If student enrolled after actual_date, skip
                        if s.join_date and s.join_date > actual_date:
                            continue
                        
                        # If student was transferred into this batch, they only have classes from effective_date onwards
                        transfer_in = s.batch_transfers.filter(to_batch=batch).order_by('-effective_date').first()
                        if transfer_in and transfer_in.effective_date > actual_date:
                            continue

                        eligible_students.append(s)

                    missing_students = [s for s in eligible_students if s.id not in existing_student_ids]
                    
                    if missing_students:
                        for student in missing_students:
                            Attendance.objects.get_or_create(
                                student=student,
                                date=actual_date,
                                defaults={
                                    'batch': batch,
                                    'status': 'ABSENT',
                                    'remarks': 'Auto-marked absent (End of day)'
                                }
                            )
            
def get_batch_class_dates(batch=None, group=None, start_limit=None, end_limit=None):
    """
    Returns a sorted list of datetime.date objects representing all valid class dates
    for a given Batch or BatchGroup.
    
    Rules:
    1. Weekly scheduled days from batch.days_list (or union of days for group).
    2. Bounds: From batch start_date (or group's earliest start_date) up to end_limit (defaults to today + 30 days).
    3. Excludes: original_date of BatchScheduleException (cancelled or shifted class days).
    4. Includes: rescheduled_date of BatchScheduleException (makeup class days).
    """
    from .models import BatchScheduleException
    today = timezone.now().date()
    
    DAYS_MAP = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    batches = []
    if group:
        batches = list(group.batches.all())
    elif batch:
        batches = [batch]
        
    if not batches:
        return []
        
    # Determine valid weekdays across batches
    valid_weekdays = set()
    start_dates = []
    for b in batches:
        if b.start_date:
            s_date = b.start_date.date() if hasattr(b.start_date, 'date') else b.start_date
            start_dates.append(s_date)
        if b.class_days:
            c_str = b.class_days.lower()
            for day_name, w_idx in DAYS_MAP.items():
                if day_name in c_str:
                    valid_weekdays.add(w_idx)
                    
    if not valid_weekdays:
        return []
        
    earliest_start = min(start_dates) if start_dates else (today - datetime.timedelta(days=90))
    if start_limit and start_limit > earliest_start:
        earliest_start = start_limit
        
    latest_end = end_limit if end_limit else (today + datetime.timedelta(days=60))
    
    # Gather exceptions across all batches
    exceptions = BatchScheduleException.objects.filter(batch__in=batches)
    cancelled_dates = set(e.original_date for e in exceptions if e.original_date)
    makeup_dates = set(e.rescheduled_date for e in exceptions if e.rescheduled_date)
    
    class_dates = set()
    curr = earliest_start
    while curr <= latest_end:
        if curr.weekday() in valid_weekdays and curr not in cancelled_dates:
            class_dates.add(curr)
        curr += datetime.timedelta(days=1)
        
    # Add makeup dates that fall within bounds
    for md in makeup_dates:
        if earliest_start <= md <= latest_end:
            class_dates.add(md)
            
    return sorted(list(class_dates))


