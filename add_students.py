import os
import sys
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'student_evaluator.settings')
django.setup()

from evaluator_app.models import Batch, Student

try:
    mca_batch = Batch.objects.get(name__icontains='mca')
except Batch.DoesNotExist:
    print("MCA batch not found.")
    exit()
except Batch.MultipleObjectsReturned:
    print("Multiple MCA batches found. Please be more specific.")
    mca_batch = Batch.objects.filter(name__icontains='mca').first()
    print(f"Using {mca_batch.name}")

students_data = [
    {"name": "Aysha Safa", "phone": "9645786362"},
    {"name": "Nesa Maryam", "phone": "6238692753"},
    {"name": "Fathima Liya", "phone": "9895039707"},
    {"name": "Aysha Hameema", "phone": "7012213317"},
    {"name": "Sameeha", "phone": "9633469153"},
    {"name": "Arijith", "phone": "6238883077"},
    {"name": "Navas Moosa", "phone": "7559967648"},
    {"name": "Shada Nafeesa", "phone": "9656935345"},
    {"name": "Fathima Hamna", "phone": "9645087259"},
    {"name": "Abdulla fadhi", "phone": "82817 05826"},
    {"name": "Ameeque", "phone": "9778700376"},
]

for data in students_data:
    student, created = Student.objects.get_or_create(
        batch=mca_batch,
        name=data["name"],
        defaults={"phone": data["phone"]}
    )
    if created:
        print(f"Added {student.name}")
    else:
        print(f"Student {student.name} already exists.")
