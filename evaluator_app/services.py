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


def get_task_for_batch_date(batch, date):
    """
    Returns the BatchTaskSchedule for a batch on a specific date, or None.
    """
    return BatchTaskSchedule.objects.filter(batch=batch, date=date).first()
