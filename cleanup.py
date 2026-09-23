from django.conf import settings
import os

from evaluator_app.models import (
    StudentTask, ProjectUpdate, Project, DailyEvaluation, Attendance,
    BatchScheduleException, BatchTaskSchedule, BatchSyllabus,
    Student, Batch, SyllabusTask, Syllabus
)

def cleanup_db(using_db='default'):
    print(f"Cleaning up database: {using_db}")
    
    models_to_clear = [
        StudentTask, ProjectUpdate, Project, DailyEvaluation, Attendance,
        BatchScheduleException, BatchTaskSchedule, BatchSyllabus,
        Student, Batch, SyllabusTask, Syllabus
    ]
    
    for model in models_to_clear:
        count, _ = model.objects.using(using_db).all().delete()
        print(f"Deleted {count} instances of {model.__name__} from {using_db}")

# Add sqlite3 dynamically to DATABASES to clean it too
settings.DATABASES['sqlite3'] = {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': os.path.join(settings.BASE_DIR, 'db.sqlite3'),
}

cleanup_db('default')
try:
    cleanup_db('sqlite3')
except Exception as e:
    print("Could not clean sqlite3:", e)
