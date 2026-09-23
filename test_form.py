import os
import sys
import django
sys.path.insert(0, r'c:\Users\zalza\OneDrive\Desktop\evaluater')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'student_evaluator.settings')
django.setup()

from evaluator_app.forms import ProjectForm

data = {
    'title': 'Test Project',
    'project_type': 'MAIN',
    'assign_to_whole_batch': True,
    'batch_ids': ['1', '2'],
    'start_date': '2026-09-21'
}
form = ProjectForm(data)
print("Is valid:", form.is_valid())
print("Errors:", form.errors)
