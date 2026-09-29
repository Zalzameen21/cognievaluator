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

students_data = [
    {"name": "Abhiraj", "student_class": "CSE", "academic_year": "S7(4th YEAR)", "phone": "+91 86065 40566", "payment_status": "UNPAID"},
    {"name": "Abin", "student_class": "CSE-A", "academic_year": "S3(2nd YEAR)", "phone": "+91 81293 12006", "payment_status": "UNPAID"},
    {"name": "Amaan Qasim", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 79941 14701", "payment_status": "PAID"},
    {"name": "Anan", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 80781 78338", "payment_status": "UNPAID"},
    {"name": "Anjesh", "student_class": "CSE", "academic_year": "S7(4th YEAR)", "phone": "+91 94466 40069", "payment_status": "UNPAID"},
    {"name": "Dhanish", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 82899 22979", "payment_status": "UNPAID"},
    {"name": "Jinyl", "student_class": "CSE-A", "academic_year": "S3(2nd YEAR)", "phone": "+91 77360 74644", "payment_status": "UNPAID"},
    {"name": "Misba", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 89216 58437", "payment_status": "UNPAID"},
    {"name": "Nahla", "student_class": "AD", "academic_year": "S3(2nd YEAR)", "phone": "8089080010", "payment_status": "UNPAID"},
    {"name": "Nihad", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 85901 69650", "payment_status": "UNPAID"},
    {"name": "Raheel", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 85905 46620", "payment_status": "UNPAID"},
    {"name": "Sivani", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "+91 73068 93360", "payment_status": "UNPAID"},
    {"name": "AdvikaAK", "student_class": "CSE-A", "academic_year": "S5(3rd YEAR)", "phone": "", "payment_status": "UNPAID"},
]

def get_batch(class_name):
    try:
        return Batch.objects.get(name__iexact=class_name)
    except Batch.DoesNotExist:
        matches = Batch.objects.filter(name__icontains=class_name)
        if class_name == 'CSE':
            matches = [m for m in matches if 'CSE-A' not in m.name.upper() and 'CSE-B' not in m.name.upper()]
        if matches:
            return matches[0]
        else:
            print(f"Batch for {class_name} not found.")
            return None
    except Batch.MultipleObjectsReturned:
        return Batch.objects.filter(name__iexact=class_name).first()

for data in students_data:
    if data["student_class"] not in ["CSE", "CSE-A"]:
        print(f"Skipping {data['name']} because they are not in CSE or CSE-A (Class: {data['student_class']})")
        continue
        
    batch = get_batch(data["student_class"])
    if not batch:
        continue
        
    student, created = Student.objects.get_or_create(
        batch=batch,
        name=data["name"],
        defaults={
            "phone": data["phone"],
            "student_class": data["student_class"],
            "academic_year": data["academic_year"],
            "payment_status": data["payment_status"]
        }
    )
    if created:
        print(f"Added {student.name} to {batch.name}")
    else:
        student.phone = data["phone"]
        student.student_class = data["student_class"]
        student.academic_year = data["academic_year"]
        student.payment_status = data["payment_status"]
        student.save()
        print(f"Student {student.name} updated in {batch.name}.")
