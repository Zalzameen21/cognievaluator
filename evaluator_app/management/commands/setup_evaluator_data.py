import random
import datetime as dt
from datetime import timedelta, time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from evaluator_app.models import Location, UserProfile, Batch, Student, DailyEvaluation, Attendance, StudentTask

class Command(BaseCommand):
    help = 'Seeds initial sample data with admin, evaluator (Kozhikode), locations, batches, students, attendance, and evaluations.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[*] Starting database seeding..."))

        # 1. Create Locations
        locations_data = [
            {'name': 'Kozhikode', 'code': 'CLT', 'address': 'Cyberpark IT Campus, Kozhikode, Kerala', 'description': 'Main Northern Kerala Tech Hub'},
            {'name': 'Kochi', 'code': 'COK', 'address': 'Infopark Phase 2, Kakkanad, Kochi, Kerala', 'description': 'Central Kerala Technology Center'},
            {'name': 'Wayanad', 'code': 'WND', 'address': 'Innovation Center, Kalpetta, Wayanad, Kerala', 'description': 'Highlands Tech & Training Center'},
        ]
        
        locations = {}
        for loc_info in locations_data:
            loc, created = Location.objects.get_or_create(
                name=loc_info['name'],
                defaults={
                    'code': loc_info['code'],
                    'address': loc_info['address'],
                    'description': loc_info['description'],
                    'is_active': True
                }
            )
            locations[loc_info['name']] = loc
            if created:
                self.stdout.write(self.style.SUCCESS(f"  + Created Location: {loc.name}"))

        # 2. Create Admin User (admin / admin123)
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@evaluator.edu',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'Global',
                'last_name': 'Admin'
            }
        )
        admin_user.set_password('admin123')
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

        admin_profile, _ = UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'role': 'ADMIN',
                'designation': 'Chief Academic Director',
                'phone': '+91 9900011122',
                'avatar_color': '#6366F1'
            }
        )
        admin_profile.role = 'ADMIN'
        admin_profile.assigned_locations.set(Location.objects.all())
        admin_profile.save()
        self.stdout.write(self.style.SUCCESS("  + Admin User configured: admin / admin123"))

        # 3. Create Evaluator User (eva / eva123) assigned to Kozhikode
        eva_user, created = User.objects.get_or_create(
            username='eva',
            defaults={
                'email': 'eva.clt@evaluator.edu',
                'first_name': 'Eva',
                'last_name': 'Nair'
            }
        )
        eva_user.set_password('eva123')
        eva_user.save()

        eva_profile, _ = UserProfile.objects.get_or_create(
            user=eva_user,
            defaults={
                'role': 'EVALUATOR',
                'designation': 'Lead Technical Evaluator (Kozhikode)',
                'phone': '+91 9847012345',
                'avatar_color': '#10B981'
            }
        )
        eva_profile.role = 'EVALUATOR'
        eva_profile.assigned_locations.set([locations['Kozhikode']])
        eva_profile.save()
        self.stdout.write(self.style.SUCCESS("  + Evaluator User configured: eva / eva123 (Assigned to Kozhikode)"))

        # 4. Create secondary Evaluators for testing location isolation
        eva_kochi_user, _ = User.objects.get_or_create(
            username='eva_kochi',
            defaults={'email': 'eva.kochi@evaluator.edu', 'first_name': 'Kochi', 'last_name': 'Evaluator'}
        )
        eva_kochi_user.set_password('kochi123')
        eva_kochi_user.save()
        p_kochi, _ = UserProfile.objects.get_or_create(user=eva_kochi_user, defaults={'role': 'EVALUATOR'})
        p_kochi.assigned_locations.set([locations['Kochi']])
        p_kochi.save()

        eva_wnd_user, _ = User.objects.get_or_create(
            username='eva_wayanad',
            defaults={'email': 'eva.wnd@evaluator.edu', 'first_name': 'Wayanad', 'last_name': 'Evaluator'}
        )
        eva_wnd_user.set_password('wayanad123')
        eva_wnd_user.save()
        p_wnd, _ = UserProfile.objects.get_or_create(user=eva_wnd_user, defaults={'role': 'EVALUATOR'})
        p_wnd.assigned_locations.set([locations['Wayanad']])
        p_wnd.save()

        import datetime

        # 5. Create Batches (Daily & Weekly)
        batches_data = [
            # Kozhikode Batches
            {
                'name': 'Python Full Stack - Daily Fast Track',
                'code': 'PY-CLT-D1',
                'location': locations['Kozhikode'],
                'created_by': eva_user,
                'schedule_type': 'DAILY',
                'class_days': 'Monday, Tuesday, Wednesday, Thursday, Friday',
                'start_time': datetime.time(9, 30),
                'end_time': datetime.time(13, 0),
                'start_date': timezone.now().date() - timedelta(days=20),
                'status': 'ACTIVE',
                'description': 'Intensive daily bootcamp covering Django, PostgreSQL, HTML5, CSS3, and JavaScript.'
            },
            {
                'name': 'Cybersecurity & Ethical Hacking - Weekend',
                'code': 'SEC-CLT-W1',
                'location': locations['Kozhikode'],
                'created_by': eva_user,
                'schedule_type': 'WEEKLY',
                'class_days': 'Saturday',
                'start_time': datetime.time(10, 0),
                'end_time': datetime.time(16, 30),
                'start_date': timezone.now().date() - timedelta(days=30),
                'status': 'ACTIVE',
                'description': 'Weekly Saturday masterclass on Network Security, Penetration Testing & Web Vulnerabilities.'
            },
            # Kochi Batch
            {
                'name': 'MERN Stack Pro - Daily Morning',
                'code': 'MERN-COK-D1',
                'location': locations['Kochi'],
                'created_by': eva_kochi_user,
                'schedule_type': 'DAILY',
                'class_days': 'Monday, Tuesday, Wednesday, Thursday, Friday, Saturday',
                'start_time': datetime.time(9, 0),
                'end_time': datetime.time(12, 30),
                'start_date': timezone.now().date() - timedelta(days=15),
                'status': 'ACTIVE',
                'description': 'Daily full-stack JavaScript bootcamp with React, Node, Express, and MongoDB.'
            },
            # Wayanad Batch
            {
                'name': 'AI & Data Science Foundation',
                'code': 'AI-WND-W1',
                'location': locations['Wayanad'],
                'created_by': eva_wnd_user,
                'schedule_type': 'WEEKLY',
                'class_days': 'Sunday',
                'start_time': datetime.time(10, 0),
                'end_time': datetime.time(16, 0),
                'start_date': timezone.now().date() - timedelta(days=40),
                'status': 'ACTIVE',
                'description': 'Weekly Sunday advanced series on Machine Learning, Python Data Stack, and Neural Networks.'
            },
        ]

        batches = {}
        for b_info in batches_data:
            batch, created = Batch.objects.get_or_create(
                code=b_info['code'],
                defaults=b_info
            )
            batches[b_info['code']] = batch
            if created:
                self.stdout.write(self.style.SUCCESS(f"  + Created Batch: {batch.name} [{batch.schedule_type}]"))

        # 6. Create Students
        students_by_batch = {
            'PY-CLT-D1': [
                ('STU-CLT-001', 'Rahul Menon', 'rahul.m@gmail.com', '+91 9847112233', '#4F46E5'),
                ('STU-CLT-002', 'Ananya Nair', 'ananya.nair@gmail.com', '+91 9847223344', '#EC4899'),
                ('STU-CLT-003', 'Mohammed Favaz', 'favaz.m@outlook.com', '+91 9847334455', '#10B981'),
                ('STU-CLT-004', 'Sneha Pillai', 'sneha.pillai@gmail.com', '+91 9847445566', '#F59E0B'),
                ('STU-CLT-005', 'Arun Kumar', 'arun.k@yahoo.com', '+91 9847556677', '#3B82F6'),
                ('STU-CLT-006', 'Fathima Raniya', 'raniya.f@gmail.com', '+91 9847667788', '#8B5CF6'),
                ('STU-CLT-007', 'Akhil Dev', 'akhildev.k@gmail.com', '+91 9847778899', '#06B6D4'),
                ('STU-CLT-008', 'Haritha Krishnan', 'haritha.k@gmail.com', '+91 9847889900', '#F97316'),
            ],
            'SEC-CLT-W1': [
                ('STU-CLT-101', 'Vishnu Prasad', 'vishnu.p@gmail.com', '+91 9745112233', '#6366F1'),
                ('STU-CLT-102', 'Deepika Varma', 'deepika.v@gmail.com', '+91 9745223344', '#EC4899'),
                ('STU-CLT-103', 'Naveen Joseph', 'naveen.j@gmail.com', '+91 9745334455', '#10B981'),
                ('STU-CLT-104', 'Keerthi Suresh', 'keerthi.s@gmail.com', '+91 9745445566', '#F59E0B'),
            ],
            'MERN-COK-D1': [
                ('STU-COK-001', 'Adarsh George', 'adarsh.g@gmail.com', '+91 9447112233', '#3B82F6'),
                ('STU-COK-002', 'Divya Mohan', 'divya.m@gmail.com', '+91 9447223344', '#EC4899'),
                ('STU-COK-003', 'Sanjay Raj', 'sanjay.r@gmail.com', '+91 9447334455', '#10B981'),
                ('STU-COK-004', 'Gopika Chandran', 'gopika.c@gmail.com', '+91 9447445566', '#8B5CF6'),
            ],
            'AI-WND-W1': [
                ('STU-WND-001', 'Basil Mathew', 'basil.m@gmail.com', '+91 9946112233', '#06B6D4'),
                ('STU-WND-002', 'Meera Nambiar', 'meera.n@gmail.com', '+91 9946223344', '#F97316'),
                ('STU-WND-003', 'Sidharth Vinod', 'sidharth.v@gmail.com', '+91 9946334455', '#4F46E5'),
            ]
        }

        created_students = []
        for batch_code, student_list in students_by_batch.items():
            batch_obj = batches[batch_code]
            for roll, name, email, phone, color in student_list:
                stu, created = Student.objects.get_or_create(
                    roll_number=roll,
                    defaults={
                        'batch': batch_obj,
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'avatar_color': color,
                        'join_date': batch_obj.start_date,
                        'status': 'ACTIVE',
                        'notes': f"Enrolled in {batch_obj.name}"
                    }
                )
                created_students.append(stu)

        self.stdout.write(self.style.SUCCESS(f"  + Enrolled {len(created_students)} students across all batches."))

        # 7. Seed Past 6 Days Attendance & Daily Evaluations for Kozhikode Daily Batch
        py_batch = batches['PY-CLT-D1']
        py_students = py_batch.students.all()
        today = timezone.now().date()

        topics = [
            "Django MVT Architecture & URL Dispatcher",
            "Django Models, Migrations & Field Validation",
            "Django QuerySet Lookups, Aggregations & F-Expressions",
            "Django Template Inheritance & Custom Context Processors",
            "Django ModelForms & Form Validation Rules",
            "Class-Based Views, Mixins & Auth Guards",
            "Building REST APIs with Django & JSON Responses"
        ]

        strongest_areas_list = [
            "Strong logical thinking & clean Django model architecture design",
            "Excellent presentation confidence and slide structure",
            "High grasp of database ORM queries and backend REST endpoints",
            "Quick at debugging complex errors and active in peer code reviews",
            "Great frontend integration with modern CSS and JavaScript interactivity",
            "Thorough slide preparation with clear architecture diagrams"
        ]

        improvement_areas_list = [
            "Practice more nested QuerySet optimization to eliminate N+1 query overhead",
            "Work on time management during live technical presentation Q&A",
            "Improve code docstring comments and git commit message consistency",
            "Review asynchronous fetch exception handling and CSRF security",
            "Speak with more confidence when explaining complex algorithms"
        ]

        interested_areas_list = [
            "Backend Systems, Scalable Django REST APIs, PostgreSQL optimization",
            "Full Stack Web Development, React UI/UX, Cloud Deployments",
            "AI Integration, Automated Machine Learning Pipelines, Data Analytics",
            "Cybersecurity, Penetration Testing, Secure Software Engineering",
            "DevOps, Docker Containerization, CI/CD Automated Pipelines"
        ]

        ppt_notes_list = [
            "Clean 8-slide deck with system architecture diagrams and code snippets.",
            "Well organized presentation with clear problem-solution flow and visual mockups.",
            "Included ER diagrams, API schema screenshots, and benchmark results.",
            "Effective use of bullet points and live terminal demo screenshots."
        ]

        # Populate last 6 days of attendance & daily evaluations
        for day_offset in range(5, -1, -1):
            eval_date = today - timedelta(days=day_offset)
            topic_today = topics[5 - day_offset]

            for index, stu in enumerate(py_students):
                # Realistic Attendance: 90% Present, occasional Late or Absent
                if (index + day_offset) % 11 == 0:
                    att_status = 'ABSENT'
                    att_remarks = 'Informed leave due to family function'
                elif (index + day_offset) % 7 == 0:
                    att_status = 'LATE'
                    att_remarks = 'Arrived 15 mins late due to traffic'
                else:
                    att_status = 'PRESENT'
                    att_remarks = 'On time and active'

                Attendance.objects.update_or_create(
                    student=stu,
                    date=eval_date,
                    defaults={
                        'batch': py_batch,
                        'status': att_status,
                        'remarks': att_remarks,
                        'marked_by': eva_user
                    }
                )

                # Daily Evaluation if present or late
                if att_status != 'ABSENT':
                    base_score = random.randint(75, 95)
                    punct = 95 if att_status == 'PRESENT' else 72
                    tutor_int = min(100, max(55, base_score + random.randint(-6, 5)))
                    peer_int = min(100, max(55, base_score + random.randint(-5, 6)))
                    study_tend = min(100, max(60, base_score + random.randint(-4, 5)))
                    
                    tasks_g = random.choice([3, 4, 5])
                    tasks_c = tasks_g if base_score > 80 else tasks_g - 1

                    pres = min(100, max(55, base_score + random.randint(-8, 5)))
                    prob = min(100, max(55, base_score + random.randint(-6, 6)))
                    ppt_eval = min(100, max(60, base_score + random.randint(-5, 5)))
                    slides = random.randint(5, 12)
                    has_imgs = random.choice([True, True, True, False])

                    comm = min(100, max(55, base_score + random.randint(-6, 7)))
                    sugg_impl = min(100, max(60, base_score + random.randint(-4, 6)))
                    doubt_clr = min(100, max(60, base_score + random.randint(-5, 6)))

                    att_pct = round(stu.attendance_percentage, 1)

                    DailyEvaluation.objects.update_or_create(
                        student=stu,
                        date=eval_date,
                        defaults={
                            'batch': py_batch,
                            'evaluator': eva_user,
                            'topic': topic_today,
                            # Behavioral & Engagement
                            'attendance_percentage': att_pct,
                            'punctuality_score': punct,
                            'tutor_interaction_score': tutor_int,
                            'classmate_interaction_score': peer_int,
                            'tendency_to_study_score': study_tend,
                            'tasks_given': tasks_g,
                            'tasks_completed': tasks_c,
                            # Project / Task Based
                            'presentation_score': pres,
                            'problem_solving_score': prob,
                            'ppt_evaluation_score': ppt_eval,
                            'ppt_slide_count': slides,
                            'ppt_has_images': has_imgs,
                            'ppt_explanation_notes': random.choice(ppt_notes_list),
                            # Communication & Mentorship
                            'communication_score': comm,
                            'suggestion_implementation_score': sugg_impl,
                            'doubt_clearing_score': doubt_clr,
                            # Remarks
                            'strongest_areas': random.choice(strongest_areas_list),
                            'areas_for_improvement': random.choice(improvement_areas_list),
                            'interested_areas': random.choice(interested_areas_list),
                            'general_remarks': f"Solid progress on {topic_today}. Consistently engaging in problem-solving and implementing feedback rapidly."
                        }
                    )

        # 8. Seed Specific Tasks & Deliverables with Pending, Completed, and Late statuses
        sample_tasks = [
            ("Build Django User Registration & Login with Password Validators", "Implement custom forms, validation, and session auth.", 5, 3, 'COMPLETED'),
            ("Design Product Catalog Model Schema with ForeignKeys", "Create Product, Category, and Order models with migrations.", 4, 2, 'COMPLETED'),
            ("Create REST API Endpoints with Django Serializers", "Build GET/POST endpoints and test in Postman.", 3, 1, 'LATE'),
            ("Implement Dynamic Ajax Filter for Batch Student List", "Write vanilla JavaScript fetch call and DOM rendering.", 2, 0, 'PENDING'),
            ("Develop Automated Unit Tests for Authentication & Models", "Write at least 6 test cases using Django TestCase.", 1, 1, 'PENDING'),
            ("Prepare Final PPT Presentation & Architecture Deck", "Include 8 slides with system architecture diagrams.", 0, 2, 'PENDING'),
        ]

        StudentTask.objects.all().delete()
        for stu in py_students:
            for task_title, task_desc, days_ago_assigned, due_days_offset, expected_status in sample_tasks:
                assigned_d = today - timedelta(days=days_ago_assigned)
                due_d = assigned_d + timedelta(days=due_days_offset)

                completed_dt = None
                if expected_status == 'COMPLETED':
                    # Completed on time (e.g. 1 day after assigned)
                    c_date = assigned_d + timedelta(days=1)
                    completed_dt = timezone.make_aware(dt.datetime.combine(c_date, time(16, 30)))
                elif expected_status == 'LATE':
                    # Completed late (1 day after due date)
                    c_date = due_d + timedelta(days=1)
                    completed_dt = timezone.make_aware(dt.datetime.combine(c_date, time(18, 45)))

                StudentTask.objects.update_or_create(
                    student=stu,
                    title=task_title,
                    defaults={
                        'batch': py_batch,
                        'assigned_by': eva_user,
                        'description': task_desc,
                        'assigned_date': assigned_d,
                        'due_date': due_d,
                        'completed_at': completed_dt,
                        'status': expected_status,
                        'priority': 'HIGH' if 'REST API' in task_title else 'NORMAL',
                        'evaluator_remarks': 'Code reviewed and tested.' if completed_dt else ''
                    }
                )

        self.stdout.write(self.style.SUCCESS("  + Generated comprehensive student tasks (Pending, Completed & Late)."))
        self.stdout.write(self.style.SUCCESS("  + Generated comprehensive attendance & daily evaluations."))
        self.stdout.write(self.style.SUCCESS("Seeding completed successfully!"))

