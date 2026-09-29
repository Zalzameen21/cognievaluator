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

    # Delete existing NON-rescheduled schedules from start_date onwards to regenerate cleanly
    BatchTaskSchedule.objects.filter(
        batch=batch,
        is_rescheduled=False,
        date__gte=start_date
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
    from .models import Batch, Attendance, ClassException
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
                exception = ClassException.objects.filter(batch=batch, original_date=check_date).first()
                if exception:
                    if exception.rescheduled_date:
                        actual_date = exception.rescheduled_date
                    else:
                        actual_date = None
                        
                if actual_date and actual_date < today:
                    existing_student_ids = set(Attendance.objects.filter(batch=batch, date=actual_date).values_list('student_id', flat=True))
                    
                    missing_students = [s for s in students if s.id not in existing_student_ids]
                    
                    if missing_students:
                        Attendance.objects.bulk_create([
                            Attendance(
                                student=student,
                                batch=batch,
                                date=actual_date,
                                status='ABSENT',
                                remarks='Auto-marked absent (End of day)'
                            ) for student in missing_students
                        ])
            
            check_date += datetime.timedelta(days=1)


