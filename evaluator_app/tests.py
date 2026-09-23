from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from .models import (
    Location, UserProfile, Batch, Student, DailyEvaluation, Attendance, StudentTask,
    Project, ProjectUpdate
)

class EvaluatorPortalTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Create Locations
        self.loc_clt = Location.objects.create(name='Kozhikode', code='CLT')
        self.loc_cok = Location.objects.create(name='Kochi', code='COK')
        self.loc_wnd = Location.objects.create(name='Wayanad', code='WND')

        # 2. Admin User
        self.admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user, role='ADMIN', designation='Administrator'
        )
        self.admin_profile.assigned_locations.set([self.loc_clt, self.loc_cok, self.loc_wnd])

        # 3. Evaluator User for Kozhikode
        self.eva_user = User.objects.create_user('eva', 'eva@example.com', 'eva123')
        self.eva_profile = UserProfile.objects.create(
            user=self.eva_user, role='EVALUATOR', designation='Kozhikode Evaluator'
        )
        self.eva_profile.assigned_locations.set([self.loc_clt])

        # 4. Evaluator User for Kochi
        self.eva_kochi = User.objects.create_user('eva_kochi', 'kochi@example.com', 'kochi123')
        self.eva_kochi_profile = UserProfile.objects.create(
            user=self.eva_kochi, role='EVALUATOR', designation='Kochi Evaluator'
        )
        self.eva_kochi_profile.assigned_locations.set([self.loc_cok])

        import datetime

        # 5. Batches (Daily and Weekly)
        self.batch_clt_daily = Batch.objects.create(
            name='Python Full Stack - Daily',
            code='PY-CLT-D1',
            location=self.loc_clt,
            created_by=self.eva_user,
            schedule_type='DAILY',
            class_days='Monday, Tuesday, Wednesday, Thursday, Friday',
            start_time=datetime.time(9, 30),
            end_time=datetime.time(13, 0),
            start_date=timezone.now().date()
        )
        self.batch_clt_weekly = Batch.objects.create(
            name='Cyber Security - Weekend',
            code='SEC-CLT-W1',
            location=self.loc_clt,
            created_by=self.eva_user,
            schedule_type='WEEKLY',
            class_days='Saturday',
            start_time=datetime.time(10, 0),
            end_time=datetime.time(16, 30),
            start_date=timezone.now().date()
        )
        self.batch_cok_daily = Batch.objects.create(
            name='MERN Stack Pro - Daily',
            code='MERN-COK-D1',
            location=self.loc_cok,
            created_by=self.eva_kochi,
            schedule_type='DAILY',
            class_days='Monday, Tuesday, Wednesday, Thursday, Friday, Saturday',
            start_time=datetime.time(9, 0),
            end_time=datetime.time(12, 30),
            start_date=timezone.now().date()
        )

        # 6. Students
        self.student_clt = Student.objects.create(
            batch=self.batch_clt_daily,
            roll_number='STU-CLT-001',
            name='Rahul Menon',
            email='rahul@example.com'
        )
        self.student_cok = Student.objects.create(
            batch=self.batch_cok_daily,
            roll_number='STU-COK-001',
            name='Adarsh George',
            email='adarsh@example.com'
        )

    def test_login_and_dashboard_access(self):
        # Test Evaluator Login
        login_success = self.client.login(username='eva', password='eva123')
        self.assertTrue(login_success)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kozhikode')

    def test_evaluator_location_isolation(self):
        # Eva (assigned to Kozhikode) should ONLY see Kozhikode batches
        self.client.login(username='eva', password='eva123')
        response = self.client.get(reverse('batch_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Python Full Stack - Daily')
        self.assertContains(response, 'Cyber Security - Weekend')
        self.assertNotContains(response, 'MERN Stack Pro - Daily')

        # Eva should NOT be able to access Kochi batch details (redirected with error)
        resp_kochi = self.client.get(reverse('batch_detail', args=[self.batch_cok_daily.id]))
        self.assertEqual(resp_kochi.status_code, 302)

    def test_admin_global_access(self):
        # Admin should see ALL batches across all locations
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('batch_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Python Full Stack - Daily')
        self.assertContains(response, 'MERN Stack Pro - Daily')

        # Admin can access admin panel
        resp_admin_loc = self.client.get(reverse('admin_locations'))
        self.assertEqual(resp_admin_loc.status_code, 200)
        resp_admin_eva = self.client.get(reverse('admin_evaluators'))
        self.assertEqual(resp_admin_eva.status_code, 200)

    def test_batch_schedule_and_days_selection(self):
        # Verify days selection and timings are properly formatted
        self.assertEqual(self.batch_clt_daily.schedule_type, 'DAILY')
        self.assertIn('Monday', self.batch_clt_daily.days_list)
        self.assertEqual(self.batch_clt_daily.timing, '10:00 AM - 06:00 PM')

        self.assertEqual(self.batch_clt_weekly.schedule_type, 'WEEKLY')
        self.assertEqual(self.batch_clt_weekly.days_list, ['Saturday'])
        self.assertEqual(self.batch_clt_weekly.timing, '10:00 AM - 04:30 PM')

    def test_batch_creation_validation_prevents_past_date(self):
        from datetime import timedelta
        from .forms import BatchForm
        self.client.login(username='eva', password='eva123')

        # Attempt to create batch with a past date
        past_date = timezone.now().date() - timedelta(days=5)
        form_data = {
            'name': 'Invalid Past Batch',
            'code': 'INV-PAST-01',
            'location': self.loc_clt.id,
            'schedule_type': 'DAILY',
            'selected_days': ['Monday', 'Wednesday', 'Friday'],
            'start_time': '10:00',
            'end_time': '13:00',
            'start_date': past_date.strftime('%Y-%m-%d'),
            'status': 'ACTIVE'
        }
        form = BatchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)
        self.assertIn('cannot be in the past', str(form.errors['start_date']))

        # Valid upcoming date should succeed
        future_date = timezone.now().date() + timedelta(days=2)
        form_data['start_date'] = future_date.strftime('%Y-%m-%d')
        form_valid = BatchForm(data=form_data)
        self.assertTrue(form_valid.is_valid())


    def test_daily_evaluation_creation_and_auto_grading(self):
        self.client.login(username='eva', password='eva123')
        
        # Post daily evaluation for student with all new behavioral, project, communication, and remarks criteria
        eval_data = {
            'topic': 'Django Models and Form Validations',
            'attendance_percentage': 95.0,
            'punctuality_score': 90,
            'tutor_interaction_score': 85,
            'classmate_interaction_score': 90,
            'tendency_to_study_score': 95,
            'tasks_given': 5,
            'tasks_completed': 5,
            'presentation_score': 88,
            'problem_solving_score': 92,
            'ppt_evaluation_score': 85,
            'ppt_slide_count': 8,
            'ppt_has_images': True,
            'ppt_explanation_notes': 'Clear architecture diagrams and code samples',
            'communication_score': 90,
            'suggestion_implementation_score': 95,
            'doubt_clearing_score': 90,
            'strongest_areas': 'High analytical ability and solid understanding of Django ORM',
            'areas_for_improvement': 'Practice more QuerySet optimization',
            'interested_areas': 'Backend API Architecture & Database Design',
            'general_remarks': 'Excellent overall performance and proactive attitude in class'
        }
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        response = self.client.post(
            reverse('student_evaluate', args=[self.student_clt.id]) + f'?date={today_str}',
            eval_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify evaluation object in database
        eval_obj = DailyEvaluation.objects.get(student=self.student_clt, date=timezone.now().date())
        self.assertGreater(eval_obj.total_score, 85.0)
        self.assertEqual(eval_obj.grade, 'A+')
        self.assertEqual(eval_obj.tasks_completed, 5)
        self.assertEqual(eval_obj.tasks_given, 5)
        self.assertEqual(eval_obj.strongest_areas, 'High analytical ability and solid understanding of Django ORM')
        self.assertEqual(eval_obj.areas_for_improvement, 'Practice more QuerySet optimization')
        self.assertEqual(eval_obj.interested_areas, 'Backend API Architecture & Database Design')

    def test_evaluation_hub_view_rendering_and_filters(self):
        self.client.login(username='eva', password='eva123')

        # 1. Base Hub Access
        resp = self.client.get(reverse('evaluation_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Daily Student Evaluation')
        self.assertContains(resp, 'Student Evaluation Roster')
        self.assertContains(resp, 'Rahul Menon')
        self.assertContains(resp, 'Batch Students')
        self.assertContains(resp, 'btnTableView')
        self.assertContains(resp, 'btnCardView')

        # 2. Filter by search query
        resp_search = self.client.get(reverse('evaluation_hub'), {'q': 'Rahul'})
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, 'Rahul Menon')

        resp_search_none = self.client.get(reverse('evaluation_hub'), {'q': 'NonExistentStudent12345'})
        self.assertEqual(resp_search_none.status_code, 200)
        self.assertNotContains(resp_search_none, 'Rahul Menon')

        # 3. Status filter: before evaluation -> Pending
        resp_pending = self.client.get(reverse('evaluation_hub'), {'status': 'pending'})
        self.assertEqual(resp_pending.status_code, 200)
        self.assertContains(resp_pending, 'Rahul Menon')

        resp_eval = self.client.get(reverse('evaluation_hub'), {'status': 'evaluated'})
        self.assertEqual(resp_eval.status_code, 200)
        self.assertNotContains(resp_eval, 'Rahul Menon')

    def test_batch_attendance_marking(self):
        self.client.login(username='eva', password='eva123')
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        
        # Mark attendance
        post_data = {
            f'status_{self.student_clt.id}': 'PRESENT',
            f'remarks_{self.student_clt.id}': 'Present on time'
        }
        response = self.client.post(
            reverse('attendance_hub') + f'?batch_id={self.batch_clt_daily.id}&date={today_str}',
            post_data
        )
        self.assertEqual(response.status_code, 302)

        # Verify attendance record
        att_record = Attendance.objects.get(student=self.student_clt, date=timezone.now().date())
        self.assertEqual(att_record.status, 'PRESENT')
        self.assertEqual(att_record.remarks, 'Present on time')

    def test_csv_export(self):
        self.client.login(username='eva', password='eva123')
        response = self.client.get(reverse('batch_export_csv', args=[self.batch_clt_daily.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Rahul Menon', response.content.decode('utf-8'))

    def test_student_task_creation_and_due_date(self):
        self.client.login(username='eva', password='eva123')
        from datetime import timedelta
        assigned_date = timezone.now().date()
        due_date = assigned_date + timedelta(days=2)

        # Create Task via POST
        post_data = {
            'target_type': 'STUDENT',
            'batch': self.batch_clt_daily.id,
            'student': self.student_clt.id,
            'title': 'Build Authentication Views & Forms',
            'description': 'Implement user login, register, and logout views.',
            'assigned_date': assigned_date.strftime('%Y-%m-%d'),
            'due_date': due_date.strftime('%Y-%m-%d'),
            'priority': 'HIGH'
        }
        response = self.client.post(reverse('task_create'), post_data)
        self.assertEqual(response.status_code, 302)

        # Verify task exists in DB
        task = StudentTask.objects.get(student=self.student_clt, title='Build Authentication Views & Forms')
        self.assertEqual(task.status, 'PENDING')
        self.assertEqual(task.assigned_date, assigned_date)
        self.assertEqual(task.due_date, due_date)
        self.assertEqual(task.description, 'Implement user login, register, and logout views.')
        self.assertIsNone(task.completed_at)
        self.assertFalse(task.is_overdue)

        # Verify task description input in task_hub modal
        hub_resp = self.client.get(reverse('task_hub'))
        self.assertEqual(hub_resp.status_code, 200)
        self.assertContains(hub_resp, 'Task Description')

    def test_student_task_marking_completed_and_late(self):
        self.client.login(username='eva', password='eva123')
        from datetime import timedelta
        assigned_date = timezone.now().date() - timedelta(days=4)
        due_date = timezone.now().date() - timedelta(days=2)

        task = StudentTask.objects.create(
            student=self.student_clt,
            batch=self.batch_clt_daily,
            assigned_by=self.eva_user,
            title='Overdue Task Example',
            assigned_date=assigned_date,
            due_date=due_date,
            status='PENDING'
        )
        self.assertTrue(task.is_overdue)

        # Mark as completed now (which is past due date -> should automatically become LATE)
        now_str = timezone.now().strftime('%Y-%m-%d %H:%M')
        response = self.client.post(
            reverse('task_update_status', args=[task.id]),
            {
                'status': 'COMPLETED',
                'completed_at': now_str,
                'evaluator_remarks': 'Submitted late after review.'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, 'LATE')
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.evaluator_remarks, 'Submitted late after review.')

    def test_task_hub_and_dashboard_monitoring(self):
        self.client.login(username='eva', password='eva123')
        
        # Create a pending task
        StudentTask.objects.create(
            student=self.student_clt,
            batch=self.batch_clt_daily,
            assigned_by=self.eva_user,
            title='Dashboard Monitor Verification Task',
            assigned_date=timezone.now().date(),
            status='PENDING'
        )

        # Check Task Hub page
        resp_tasks = self.client.get(reverse('task_hub'))
        self.assertEqual(resp_tasks.status_code, 200)
        self.assertContains(resp_tasks, 'Dashboard Monitor Verification Task')

        # Check Dashboard page shows pending task count
        resp_dash = self.client.get(reverse('dashboard'))
        self.assertEqual(resp_dash.status_code, 200)
        self.assertContains(resp_dash, 'Pending Tasks')

    def test_attendance_lock_and_admin_override(self):
        # 1. Evaluator marks attendance on a new date
        self.client.login(username='eva', password='eva123')
        test_date = timezone.now().date()
        date_str = test_date.strftime('%Y-%m-%d')
        
        post_url = f"{reverse('attendance_hub')}?batch_id={self.batch_clt_daily.id}&date={date_str}"
        resp_mark = self.client.post(post_url, {
            f'status_{self.student_clt.id}': 'PRESENT',
            f'remarks_{self.student_clt.id}': 'Initial on time'
        })
        self.assertEqual(resp_mark.status_code, 302)

        # Verify attendance is PRESENT in DB
        att = Attendance.objects.get(student=self.student_clt, date=test_date)
        self.assertEqual(att.status, 'PRESENT')
        self.assertEqual(att.remarks, 'Initial on time')

        # 2. Evaluator attempts to change the saved attendance -> MUST BE BLOCKED / LOCKED
        resp_attempt_edit = self.client.post(post_url, {
            f'status_{self.student_clt.id}': 'ABSENT',
            f'remarks_{self.student_clt.id}': 'Trying to change to absent'
        }, follow=True)
        self.assertEqual(resp_attempt_edit.status_code, 200)
        self.assertContains(resp_attempt_edit, 'Attendance for this date has already been marked and saved')

        # Verify attendance in DB remained PRESENT (was NOT overwritten by evaluator)
        att.refresh_from_db()
        self.assertEqual(att.status, 'PRESENT')
        self.assertEqual(att.remarks, 'Initial on time')

        # 3. Admin logs in and edits the attendance -> MUST BE ALLOWED
        self.client.login(username='admin', password='admin123')
        resp_admin_edit = self.client.post(post_url, {
            f'status_{self.student_clt.id}': 'LATE',
            f'remarks_{self.student_clt.id}': 'Admin corrected to late'
        }, follow=True)
        self.assertEqual(resp_admin_edit.status_code, 200)
        self.assertContains(resp_admin_edit, 'Admin Update')

        # Verify DB is updated by Admin
        att.refresh_from_db()
        self.assertEqual(att.status, 'LATE')
        self.assertEqual(att.remarks, 'Admin corrected to late')

    def test_low_attendance_detection_below_50_percent(self):
        self.client.login(username='eva', password='eva123')
        from datetime import timedelta
        today = timezone.now().date()

        # Create attendance records for student_clt: 1 Present, 3 Absent -> 25% attendance (< 50%)
        Attendance.objects.filter(student=self.student_clt).delete()
        Attendance.objects.create(student=self.student_clt, batch=self.batch_clt_daily, date=today - timedelta(days=1), status='PRESENT')
        Attendance.objects.create(student=self.student_clt, batch=self.batch_clt_daily, date=today - timedelta(days=2), status='ABSENT')
        Attendance.objects.create(student=self.student_clt, batch=self.batch_clt_daily, date=today - timedelta(days=3), status='ABSENT')
        Attendance.objects.create(student=self.student_clt, batch=self.batch_clt_daily, date=today - timedelta(days=4), status='ABSENT')

        self.assertEqual(self.student_clt.attendance_percentage, 25.0)

        # Check Attendance Hub alerts
        resp_att = self.client.get(reverse('attendance_hub'))
        self.assertEqual(resp_att.status_code, 200)
        self.assertContains(resp_att, 'Critical Attendance Alert')
        self.assertContains(resp_att, self.student_clt.name)
        self.assertContains(resp_att, '25.0%')

        # Check Dashboard alerts
        resp_dash = self.client.get(reverse('dashboard'))
        self.assertEqual(resp_dash.status_code, 200)
        self.assertContains(resp_dash, 'Critical Student Attendance Alert')
        self.assertContains(resp_dash, self.student_clt.name)
        self.assertContains(resp_dash, '25.0%')

    def test_project_crud_and_location_scoping(self):
        # 1. Create a project in Kozhikode batch
        self.client.login(username='eva', password='eva123')
        create_resp = self.client.post(reverse('project_create'), {
            'title': 'Hospital Management System',
            'project_type': 'MAIN',
            'batch': self.batch_clt_daily.id,
            'students': [self.student_clt.id],
            'technologies': 'Python, Django, PostgreSQL, HTML5, CSS3',
            'description': 'End-to-end appointment booking and patient record system.',
            'status': 'IN_PROGRESS',
            'progress_percentage': 35,
            'start_date': timezone.now().date().strftime('%Y-%m-%d'),
            'github_repo_url': 'https://github.com/student/hospital-system',
            'live_demo_url': 'https://hospital-demo.app',
            'documentation_url': 'https://notion.so/hospital-docs',
        }, follow=True)
        self.assertEqual(create_resp.status_code, 200)
        self.assertContains(create_resp, 'Hospital Management System')

        # Verify in DB
        proj = Project.objects.get(title='Hospital Management System')
        self.assertEqual(proj.batch, self.batch_clt_daily)
        self.assertEqual(proj.progress_percentage, 35)
        self.assertIn(self.student_clt, proj.students.all())
        self.assertIn('Python', proj.tech_list)
        self.assertIn('Django', proj.tech_list)

        # 2. Eva (Kozhikode) should see it in Project Hub
        hub_resp = self.client.get(reverse('project_hub'))
        self.assertEqual(hub_resp.status_code, 200)
        self.assertContains(hub_resp, 'Hospital Management System')

        # 3. Eva Kochi (assigned to Kochi only) should NOT see Kozhikode project in their hub
        self.client.login(username='eva_kochi', password='kochi123')
        hub_kochi = self.client.get(reverse('project_hub'))
        self.assertEqual(hub_kochi.status_code, 200)
        self.assertNotContains(hub_kochi, 'Hospital Management System')

        # 4. Eva Kochi cannot access project detail for Kozhikode project
        detail_forbidden = self.client.get(reverse('project_detail', args=[proj.id]), follow=True)
        self.assertContains(detail_forbidden, 'Permission denied')

    def test_project_progress_update_and_milestones(self):
        # Create initial project
        proj = Project.objects.create(
            title='E-Commerce Store',
            batch=self.batch_clt_daily,
            project_type='MAIN',
            technologies='Python, Django, React, Stripe',
            progress_percentage=20,
            status='IN_PROGRESS',
            created_by=self.eva_user
        )
        proj.students.add(self.student_clt)

        self.client.login(username='eva', password='eva123')

        # Update progress to 80% with milestone notes
        update_resp = self.client.post(reverse('project_update_progress', args=[proj.id]), {
            'progress_percentage': 80,
            'status': 'UNDER_REVIEW',
            'milestone_notes': 'Integrated Stripe checkout and completed inventory models.',
            'github_repo_url': 'https://github.com/student/ecommerce',
            'live_demo_url': 'https://ecommerce.vercel.app',
            'documentation_url': '',
        }, follow=True)
        self.assertEqual(update_resp.status_code, 200)

        proj.refresh_from_db()
        self.assertEqual(proj.progress_percentage, 80)
        self.assertEqual(proj.status, 'UNDER_REVIEW')
        self.assertEqual(proj.github_repo_url, 'https://github.com/student/ecommerce')

        # Verify milestone log was generated
        latest_update = proj.updates.first()
        self.assertIsNotNone(latest_update)
        self.assertEqual(latest_update.progress_percentage, 80)
        self.assertIn('Stripe checkout', latest_update.notes)

    def test_project_evaluation_rubric_scoring(self):
        proj = Project.objects.create(
            title='AI Chatbot Platform',
            batch=self.batch_clt_daily,
            project_type='MAIN',
            technologies='Python, Django, OpenAI, TailwindCSS',
            progress_percentage=100,
            status='COMPLETED',
            created_by=self.eva_user
        )
        proj.students.add(self.student_clt)

        self.client.login(username='eva', password='eva123')

        # Grade rubric: Functionality (90), Code Quality (85), Presentation (80), UI/UX (90), Viva (85)
        # Expected composite weighted score:
        # 90*0.30 + 85*0.25 + 80*0.20 + 90*0.15 + 85*0.10 = 27 + 21.25 + 16 + 13.5 + 8.5 = 86.25 -> round 86.2 or 86.3
        eval_resp = self.client.post(reverse('project_evaluate', args=[proj.id]), {
            'functionality_score': 90,
            'code_quality_score': 85,
            'presentation_score': 80,
            'ui_ux_score': 90,
            'viva_score': 85,
            'strengths': 'Clean architecture, responsive UI, good API handling.',
            'areas_to_improve': 'Add caching for frequently queried endpoints.',
            'evaluator_feedback': 'Outstanding project execution!',
        }, follow=True)
        self.assertEqual(eval_resp.status_code, 200)

        proj.refresh_from_db()
        self.assertTrue(proj.is_evaluated)
        self.assertAlmostEqual(proj.total_score, 86.2, delta=0.2)
        self.assertEqual(proj.grade, 'A')
        self.assertEqual(proj.strengths, 'Clean architecture, responsive UI, good API handling.')

        # Verify student profile shows project
        student_resp = self.client.get(reverse('student_detail', args=[self.student_clt.id]))
        self.assertEqual(student_resp.status_code, 200)
        self.assertContains(student_resp, 'AI Chatbot Platform')
        self.assertContains(student_resp, '86.2%')

    def test_assigned_students_strictly_scoped_to_selected_batch(self):
        # Create a second student in weekly batch
        student_clt_weekly = Student.objects.create(
            batch=self.batch_clt_weekly,
            roll_number='STU-CLT-W01',
            name='Kavya Nair',
            email='kavya@example.com'
        )

        self.client.login(username='eva', password='eva123')

        # 1. Test ProjectForm initializes students to target batch only
        from .forms import ProjectForm
        form_daily = ProjectForm(user=self.eva_user, initial_batch=self.batch_clt_daily)
        student_ids_daily = list(form_daily.fields['students'].queryset.values_list('id', flat=True))
        self.assertIn(self.student_clt.id, student_ids_daily)
        self.assertNotIn(student_clt_weekly.id, student_ids_daily)

        form_weekly = ProjectForm(user=self.eva_user, initial_batch=self.batch_clt_weekly)
        student_ids_weekly = list(form_weekly.fields['students'].queryset.values_list('id', flat=True))
        self.assertIn(student_clt_weekly.id, student_ids_weekly)
        self.assertNotIn(self.student_clt.id, student_ids_weekly)

        # 2. Test batch_students_api returns only students belonging to that batch
        api_resp = self.client.get(reverse('batch_students_api', args=[self.batch_clt_daily.id]))
        self.assertEqual(api_resp.status_code, 200)
        data = api_resp.json()
        self.assertTrue(data['success'])
        student_names = [s['name'] for s in data['students']]
        self.assertIn(self.student_clt.name, student_names)
        self.assertNotIn(student_clt_weekly.name, student_names)

        # 3. Test form submission validation: Assigning student from another batch fails
        invalid_post_resp = self.client.post(reverse('project_create'), {
            'title': 'Cross Batch Test Project',
            'project_type': 'MINI',
            'batch': self.batch_clt_daily.id,
            'students': [student_clt_weekly.id], # Belongs to batch_clt_weekly, not batch_clt_daily!
            'technologies': 'Python, Django',
            'status': 'PLANNING',
            'progress_percentage': 0,
            'start_date': timezone.now().date().strftime('%Y-%m-%d'),
        })
        self.assertEqual(invalid_post_resp.status_code, 200)
        # Form error should indicate student does not belong to selected batch
        self.assertContains(invalid_post_resp, "Select a valid choice")


class TaskEvaluationTests(TestCase):
    def setUp(self):
        self.loc_clt = Location.objects.create(name='Kozhikode', code='CLT')
        self.loc_cok = Location.objects.create(name='Kochi', code='COK')

        self.evaluator = User.objects.create_user(username='evaluator_test', password='password123')
        self.profile = UserProfile.objects.create(user=self.evaluator, role='EVALUATOR')
        self.profile.assigned_locations.add(self.loc_clt)

        self.other_user = User.objects.create_user(username='other_evaluator', password='password123')
        self.other_profile = UserProfile.objects.create(user=self.other_user, role='EVALUATOR')
        self.other_profile.assigned_locations.add(self.loc_cok)

        self.batch_clt = Batch.objects.create(
            name='Python Batch CLT',
            code='PY-CLT-01',
            location=self.loc_clt,
            schedule_type='DAILY',
            start_date=timezone.now().date(),
        )

        self.batch_cok = Batch.objects.create(
            name='Python Batch COK',
            code='PY-COK-01',
            location=self.loc_cok,
            schedule_type='DAILY',
            start_date=timezone.now().date(),
        )

        self.student_1 = Student.objects.create(
            batch=self.batch_clt,
            roll_number='STU-001',
            name='Aditi Sharma',
            email='aditi@example.com'
        )

        self.student_2 = Student.objects.create(
            batch=self.batch_clt,
            roll_number='STU-002',
            name='Bilal Khan',
            email='bilal@example.com'
        )

        self.student_other = Student.objects.create(
            batch=self.batch_cok,
            roll_number='STU-099',
            name='Deepak Nair',
            email='deepak@example.com'
        )

        self.task_1 = StudentTask.objects.create(
            student=self.student_1,
            batch=self.batch_clt,
            assigned_by=self.evaluator,
            title='Build REST API Endpoint',
            description='Create Django REST Framework API for articles',
            assigned_date=timezone.now().date(),
            status='PENDING',
            priority='HIGH'
        )

        self.task_2 = StudentTask.objects.create(
            student=self.student_2,
            batch=self.batch_clt,
            assigned_by=self.evaluator,
            title='Database Schema Design',
            description='Design normalized PostgreSQL tables',
            assigned_date=timezone.now().date(),
            status='COMPLETED',
            priority='NORMAL'
        )

    def test_calculate_total_score_and_grade(self):
        task = self.task_1
        task.code_quality_score = 90
        task.problem_solving_score = 90
        task.timeliness_score = 85
        task.presentation_score = 85
        score = task.calculate_total_score()
        # 90*0.35 + 90*0.35 + 85*0.15 + 85*0.15 = 31.5 + 31.5 + 12.75 + 12.75 = 88.5
        self.assertAlmostEqual(score, 88.5, places=1)
        self.assertEqual(task.grade, 'A')

    def test_task_evaluation_hub_view_and_filters(self):
        self.client.login(username='evaluator_test', password='password123')

        # 1. Access Hub
        resp = self.client.get(reverse('task_evaluation_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Build REST API Endpoint')
        self.assertContains(resp, 'Database Schema Design')
        self.assertContains(resp, 'Aditi Sharma')
        self.assertContains(resp, 'Bilal Khan')
        # Scoped batch check: other location task shouldn't be accessible
        self.assertNotContains(resp, 'Deepak Nair')

        # 2. Search by Student Name
        search_resp = self.client.get(reverse('task_evaluation_hub') + '?q=Aditi')
        self.assertEqual(search_resp.status_code, 200)
        self.assertContains(search_resp, 'Aditi Sharma')
        self.assertNotContains(search_resp, 'Bilal Khan')

        # 3. Filter by Batch
        batch_resp = self.client.get(reverse('task_evaluation_hub') + f'?batch={self.batch_clt.id}')
        self.assertEqual(batch_resp.status_code, 200)
        self.assertContains(batch_resp, 'PY-CLT-01')

    def test_evaluate_task_post_and_modal_api(self):
        self.client.login(username='evaluator_test', password='password123')

        # 1. GET via AJAX returns task json
        get_resp = self.client.get(reverse('task_evaluate', args=[self.task_1.id]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['title'], 'Build REST API Endpoint')
        self.assertEqual(data['student_name'], 'Aditi Sharma')

        # 2. POST evaluation
        post_resp = self.client.post(reverse('task_evaluate', args=[self.task_1.id]), {
            'code_quality_score': 95,
            'problem_solving_score': 92,
            'timeliness_score': 90,
            'presentation_score': 90,
            'evaluation_status': 'EXCELLENT',
            'status': 'COMPLETED',
            'evaluator_feedback': 'Exceptional modular structure, clean docstrings and full test coverage.',
            'strengths': 'Clean code, excellent serializer validation',
            'areas_for_improvement': 'None, ready for production',
            'submission_url': 'https://github.com/aditi/rest-api-task',
        }, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        self.task_1.refresh_from_db()
        self.assertTrue(self.task_1.is_evaluated)
        self.assertEqual(self.task_1.evaluation_status, 'EXCELLENT')
        self.assertEqual(self.task_1.grade, 'A+')
        self.assertAlmostEqual(self.task_1.score, 92.4, places=1)
        self.assertEqual(self.task_1.status, 'COMPLETED')
        self.assertEqual(self.task_1.evaluated_by, self.evaluator)
        self.assertIsNotNone(self.task_1.evaluated_at)

    def test_evaluation_permission_denied_for_unassigned_batch(self):
        # Other evaluator has access only to COK, not CLT
        self.client.login(username='other_evaluator', password='password123')
        resp = self.client.post(reverse('task_evaluate', args=[self.task_1.id]), {
            'code_quality_score': 80,
            'evaluation_status': 'PASSED',
        })
        # Should redirect with error
        self.assertEqual(resp.status_code, 302)
        self.task_1.refresh_from_db()
        self.assertFalse(self.task_1.is_evaluated)


class StudentAddWithoutBatchSelectionTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(name='Kozhikode Center', code='CLT')
        self.other_location = Location.objects.create(name='Kochi Center', code='COK')
        
        import datetime
        self.batch = Batch.objects.create(
            name='MES Batch',
            code='MES-01',
            location=self.location,
            schedule_type='WEEKLY',
            class_days='Monday, Tuesday',
            start_time=datetime.time(10, 30),
            end_time=datetime.time(17, 30),
            start_date=timezone.now().date(),
            status='ACTIVE'
        )
        self.other_batch = Batch.objects.create(
            name='Kochi Batch',
            code='KOC-01',
            location=self.other_location,
            schedule_type='DAILY',
            class_days='Monday',
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            start_date=timezone.now().date(),
            status='ACTIVE'
        )
        
        self.user = User.objects.create_user(username='eval_user', password='password123')
        self.profile = UserProfile.objects.create(user=self.user, role='EVALUATOR')
        self.profile.assigned_locations.add(self.location)

    def test_student_add_to_batch_get_removes_batch_assignment_dropdown(self):
        self.client.login(username='eval_user', password='password123')
        resp = self.client.get(reverse('student_add_to_batch', args=[self.batch.id]))
        self.assertEqual(resp.status_code, 200)
        # Should NOT contain visible Batch Assignment * input label
        self.assertNotContains(resp, '<label class="form-label">Batch Assignment *</label>')
        # Should contain hidden input with batch id
        self.assertContains(resp, f'type="hidden" name="batch" value="{self.batch.id}"')
        # Should contain contextual batch name
        self.assertContains(resp, 'Enrolling to Batch')
        self.assertContains(resp, 'MES Batch')
        # Should contain student roll number and name fields
        self.assertContains(resp, 'Roll Number')
        self.assertContains(resp, 'Default / Batch-Based')
        self.assertContains(resp, 'Full Name *')

    def test_student_add_to_batch_post_creates_student_in_correct_batch(self):
        self.client.login(username='eval_user', password='password123')
        post_data = {
            'batch': str(self.batch.id),
            'roll_number': 'STU-MES-001',
            'name': 'Rahul Sharma',
            'email': 'rahul@example.com',
            'phone': '+91 9876543210',
            'join_date': timezone.now().date().strftime('%Y-%m-%d'),
            'status': 'ACTIVE',
            'notes': 'Experienced with Python'
        }
        resp = self.client.post(reverse('student_add_to_batch', args=[self.batch.id]), post_data)
        self.assertEqual(resp.status_code, 302)
        
        student = Student.objects.get(roll_number='STU-MES-001')
        self.assertEqual(student.name, 'Rahul Sharma')
        self.assertEqual(student.batch, self.batch)

    def test_student_add_permission_denied_for_unauthorized_batch(self):
        self.client.login(username='eval_user', password='password123')
        # eval_user is only assigned to CLT, cannot add to COK
        resp = self.client.get(reverse('student_add_to_batch', args=[self.other_batch.id]))
        self.assertEqual(resp.status_code, 302)

    def test_student_enrollment_date_min_attribute_in_html(self):
        self.client.login(username='eval_user', password='password123')
        resp = self.client.get(reverse('student_add_to_batch', args=[self.batch.id]))
        self.assertEqual(resp.status_code, 200)
        expected_min = self.batch.start_date.strftime('%Y-%m-%d')
        self.assertContains(resp, f'min="{expected_min}"')
        self.assertContains(resp, 'Cannot be earlier than Batch Start Date')

    def test_student_enrollment_date_earlier_than_batch_start_date_fails(self):
        import datetime
        self.client.login(username='eval_user', password='password123')
        earlier_date = (self.batch.start_date - datetime.timedelta(days=5)).strftime('%Y-%m-%d')
        post_data = {
            'batch': str(self.batch.id),
            'roll_number': 'STU-INVALID-001',
            'name': 'Invalid Date Student',
            'join_date': earlier_date,
            'status': 'ACTIVE'
        }
        resp = self.client.post(reverse('student_add_to_batch', args=[self.batch.id]), post_data)
        self.assertEqual(resp.status_code, 200)  # Re-renders form with error
        self.assertContains(resp, 'Enrollment Date cannot be earlier than the Batch Start Date')
        self.assertFalse(Student.objects.filter(roll_number='STU-INVALID-001').exists())

    def test_student_model_clean_raises_validation_error_when_earlier_than_start_date(self):
        import datetime
        from django.core.exceptions import ValidationError
        earlier_date = self.batch.start_date - datetime.timedelta(days=2)
        student = Student(
            batch=self.batch,
            roll_number='STU-MODEL-001',
            name='Model Check',
            join_date=earlier_date
        )
        with self.assertRaises(ValidationError) as ctx:
            student.clean()
        self.assertIn('join_date', ctx.exception.message_dict)


class BatchStudentExcelImportTests(TestCase):
    def setUp(self):
        import datetime
        self.location = Location.objects.create(name='Kozhikode Center', code='CLT')
        self.other_location = Location.objects.create(name='Kochi Center', code='COK')

        self.batch = Batch.objects.create(
            name='MES Batch',
            code='MES-01',
            location=self.location,
            schedule_type='WEEKLY',
            class_days='Monday, Tuesday',
            start_time=datetime.time(10, 30),
            end_time=datetime.time(17, 30),
            start_date=timezone.now().date(),
            status='ACTIVE'
        )
        self.other_batch = Batch.objects.create(
            name='Kochi Batch',
            code='KOC-01',
            location=self.other_location,
            schedule_type='DAILY',
            class_days='Monday',
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            start_date=timezone.now().date(),
            status='ACTIVE'
        )

        self.user = User.objects.create_user(username='eval_user', password='password123')
        self.profile = UserProfile.objects.create(user=self.user, role='EVALUATOR')
        self.profile.assigned_locations.add(self.location)

    def test_download_student_template_xlsx_and_csv(self):
        self.client.login(username='eval_user', password='password123')
        
        # 1. Download XLSX
        resp_xlsx = self.client.get(reverse('download_student_template', args=[self.batch.id, 'xlsx']))
        self.assertEqual(resp_xlsx.status_code, 200)
        self.assertEqual(resp_xlsx['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        # 2. Download CSV
        resp_csv = self.client.get(reverse('download_student_template', args=[self.batch.id, 'csv']))
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv['Content-Type'], 'text/csv')
        self.assertContains(resp_csv, 'Roll Number,Full Name,Email,Phone,Enrollment Date,Status,Notes')

    def test_batch_student_import_get_renders_page(self):
        self.client.login(username='eval_user', password='password123')
        resp = self.client.get(reverse('batch_student_import', args=[self.batch.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Import Students via Excel / CSV')
        self.assertContains(resp, 'MES Batch')
        self.assertContains(resp, 'Upload Spreadsheet')

    def test_batch_student_import_csv_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='eval_user', password='password123')

        csv_content = (
            "Roll Number,Full Name,Email,Phone,Enrollment Date,Status,Notes\n"
            f"CSV-001,Althaf Mohammed,althaf@example.com,+91 9999988888,{self.batch.start_date.strftime('%Y-%m-%d')},ACTIVE,CSV student test\n"
            f"CSV-002,Fathima Zahra,fathima@example.com,+91 9999988889,{self.batch.start_date.strftime('%Y-%m-%d')},ACTIVE,Fast learner\n"
        ).encode('utf-8')

        uploaded_file = SimpleUploadedFile("students.csv", csv_content, content_type="text/csv")
        resp = self.client.post(reverse('batch_student_import', args=[self.batch.id]), {
            'file': uploaded_file,
            'duplicate_action': 'skip',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Student.objects.filter(roll_number='CSV-001', batch=self.batch).exists())
        self.assertTrue(Student.objects.filter(roll_number='CSV-002', batch=self.batch).exists())

        stu1 = Student.objects.get(roll_number='CSV-001')
        self.assertEqual(stu1.name, 'Althaf Mohammed')
        self.assertEqual(stu1.email, 'althaf@example.com')

    def test_batch_student_import_xlsx_success(self):
        import io
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='eval_user', password='password123')

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['Roll Number', 'Full Name', 'Email', 'Phone', 'Enrollment Date', 'Status', 'Notes'])
        ws.append(['XLSX-001', 'Devika Menon', 'devika@example.com', '+91 9123456789', self.batch.start_date.strftime('%Y-%m-%d'), 'ACTIVE', 'Python Fullstack'])
        
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        uploaded_file = SimpleUploadedFile("students.xlsx", output.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp = self.client.post(reverse('batch_student_import', args=[self.batch.id]), {
            'file': uploaded_file,
            'duplicate_action': 'skip',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Student.objects.filter(roll_number='XLSX-001', batch=self.batch).exists())
        stu = Student.objects.get(roll_number='XLSX-001')
        self.assertEqual(stu.name, 'Devika Menon')

    def test_batch_student_import_enforces_start_date_constraint(self):
        import datetime
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='eval_user', password='password123')

        earlier_date = (self.batch.start_date - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        csv_content = (
            "Roll Number,Full Name,Email,Phone,Enrollment Date,Status,Notes\n"
            f"INVALID-DATE-001,Date Violator,bad@example.com,,{earlier_date},ACTIVE,\n"
        ).encode('utf-8')

        uploaded_file = SimpleUploadedFile("invalid_date.csv", csv_content, content_type="text/csv")
        resp = self.client.post(reverse('batch_student_import', args=[self.batch.id]), {
            'file': uploaded_file,
            'duplicate_action': 'skip',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'cannot be earlier than Batch Start Date')
        self.assertFalse(Student.objects.filter(roll_number='INVALID-DATE-001').exists())

    def test_batch_student_import_permission_denied_for_other_location(self):
        self.client.login(username='eval_user', password='password123')
        # eval_user has access only to CLT, not COK
        resp = self.client.get(reverse('batch_student_import', args=[self.other_batch.id]))
        self.assertEqual(resp.status_code, 302)


class ProjectFormAndViewsTests(TestCase):
    def setUp(self):
        import datetime
        self.location = Location.objects.create(name='Kozhikode Center', code='CLT')
        self.user = User.objects.create_user(username='proj_eval', password='password123')
        self.profile = UserProfile.objects.create(user=self.user, role='EVALUATOR')
        self.profile.assigned_locations.add(self.location)

        self.batch = Batch.objects.create(
            name='Python Batch CLT',
            code='PY-CLT-01',
            location=self.location,
            created_by=self.user,
            schedule_type='DAILY',
            class_days='Monday',
            start_time=datetime.time(9, 30),
            end_time=datetime.time(13, 0),
            start_date=timezone.now().date()
        )
        self.student = Student.objects.create(
            batch=self.batch,
            roll_number='PY-001',
            name='Rohit Sharma',
            email='rohit@example.com'
        )

    def test_project_create_view_rendering_and_submission(self):
        self.client.login(username='proj_eval', password='password123')
        # Test GET
        resp_get = self.client.get(reverse('project_create'))
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Project Title')
        self.assertContains(resp_get, 'Assigned Student(s)')
        self.assertContains(resp_get, 'Technologies Used')
        self.assertContains(resp_get, 'Select All')

        # Test POST creation
        post_data = {
            'batch': self.batch.id,
            'students': [self.student.id],
            'title': 'AI Healthcare Triage System',
            'project_type': 'MAIN',
            'technologies': 'Python, Django, React, PostgreSQL',
            'description': 'An advanced triage web system with AI-driven symptom evaluation.',
            'status': 'IN_PROGRESS',
            'progress_percentage': '35',
            'start_date': timezone.now().date().strftime('%Y-%m-%d'),
            'target_completion_date': (timezone.now().date() + timezone.timedelta(days=30)).strftime('%Y-%m-%d'),
            'github_repo_url': 'https://github.com/example/ai-triage',
            'live_demo_url': 'https://ai-triage.example.com',
            'documentation_url': 'https://notion.so/ai-triage-docs',
        }
        resp_post = self.client.post(reverse('project_create'), post_data, follow=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertTrue(Project.objects.filter(title='AI Healthcare Triage System').exists())
        proj = Project.objects.get(title='AI Healthcare Triage System')
        self.assertEqual(proj.created_by, self.user)
        self.assertEqual(list(proj.students.all()), [self.student])
        self.assertEqual(proj.progress_percentage, 35)

        # Test Edit GET and POST
        resp_edit_get = self.client.get(reverse('project_edit', args=[proj.id]))
        self.assertEqual(resp_edit_get.status_code, 200)
        self.assertContains(resp_edit_get, 'Edit Project')

        post_edit_data = post_data.copy()
        post_edit_data['progress_percentage'] = '75'
        resp_edit_post = self.client.post(reverse('project_edit', args=[proj.id]), post_edit_data, follow=True)
        self.assertEqual(resp_edit_post.status_code, 200)
        proj.refresh_from_db()
        self.assertEqual(proj.progress_percentage, 75)

    def test_project_hub_rendering_and_filters(self):
        self.client.login(username='proj_eval', password='password123')
        # Create a test project
        proj = Project.objects.create(
            batch=self.batch,
            title='Autonomous Driving Platform',
            project_type='MAIN',
            technologies='Python, PyTorch, ROS',
            status='IN_PROGRESS',
            progress_percentage=45,
            created_by=self.user
        )
        proj.students.add(self.student)

        # 1. Test Project Hub GET
        resp = self.client.get(reverse('project_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Autonomous Driving Platform')
        self.assertContains(resp, 'PyTorch')
        self.assertContains(resp, 'Rohit Sharma')
        self.assertContains(resp, 'New Project')
        self.assertContains(resp, 'Table')
        self.assertContains(resp, 'Grid')

        # 2. Test status filter
        resp_filter = self.client.get(reverse('project_hub'), {'status': 'IN_PROGRESS'})
        self.assertEqual(resp_filter.status_code, 200)
        self.assertContains(resp_filter, 'Autonomous Driving Platform')

        # 3. Test empty filter
        resp_empty = self.client.get(reverse('project_hub'), {'status': 'COMPLETED'})
        self.assertEqual(resp_empty.status_code, 200)
        self.assertContains(resp_empty, 'No Projects Found')


class StudentBatchRollNumberAndRemovalTests(TestCase):
    def setUp(self):
        import datetime
        self.loc_clt = Location.objects.create(name='Kozhikode Center', code='CLT')
        self.loc_cok = Location.objects.create(name='Kochi Center', code='COK')

        self.eval_user = User.objects.create_user(username='eval_clt', password='password123')
        self.profile = UserProfile.objects.create(user=self.eval_user, role='EVALUATOR')
        self.profile.assigned_locations.add(self.loc_clt)

        self.other_user = User.objects.create_user(username='eval_cok', password='password123')
        self.other_profile = UserProfile.objects.create(user=self.other_user, role='EVALUATOR')
        self.other_profile.assigned_locations.add(self.loc_cok)

        self.batch = Batch.objects.create(
            name='Python Fullstack 2026',
            code='PFS-2026',
            location=self.loc_clt,
            created_by=self.eval_user,
            schedule_type='DAILY',
            class_days='Monday, Tuesday',
            start_time=datetime.time(9, 30),
            end_time=datetime.time(13, 0),
            start_date=timezone.now().date(),
            status='ACTIVE'
        )

        self.student_1 = Student.objects.create(
            batch=self.batch,
            roll_number='PFS-2026-001',
            name='Ananya Sen',
            email='ananya@example.com'
        )

    def test_generate_batch_student_roll_number_sequential(self):
        from .models import generate_batch_student_roll_number
        next_roll = generate_batch_student_roll_number(self.batch)
        self.assertEqual(next_roll, 'PFS-2026-002')

        # Auto-generation on Student.save() when roll_number is blank
        student_2 = Student(
            batch=self.batch,
            name='Bipin Raj',
            email='bipin@example.com'
        )
        student_2.save()
        self.assertEqual(student_2.roll_number, 'PFS-2026-002')

        # Next one should be PFS-2026-003
        next_roll_3 = generate_batch_student_roll_number(self.batch)
        self.assertEqual(next_roll_3, 'PFS-2026-003')

    def test_batch_next_roll_number_api(self):
        self.client.login(username='eval_clt', password='password123')
        resp = self.client.get(reverse('batch_next_roll_number_api', args=[self.batch.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['roll_number'], 'PFS-2026-002')
        self.assertEqual(data['batch_code'], 'PFS-2026')

        # Unauthorized evaluator
        self.client.login(username='eval_cok', password='password123')
        resp_unauth = self.client.get(reverse('batch_next_roll_number_api', args=[self.batch.id]))
        self.assertEqual(resp_unauth.status_code, 403)

    def test_student_delete_by_evaluator_redirects_to_batch_detail(self):
        self.client.login(username='eval_clt', password='password123')
        delete_url = reverse('student_delete', args=[self.student_1.id])
        
        # Test GET confirmation page
        resp_get = self.client.get(delete_url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Remove Student')
        self.assertContains(resp_get, 'Ananya Sen')
        self.assertContains(resp_get, 'PFS-2026-001')

        # Test POST deletion
        resp_post = self.client.post(delete_url, follow=True)
        self.assertEqual(resp_post.status_code, 200)
        # Should redirect back to batch_detail
        self.assertFalse(Student.objects.filter(id=self.student_1.id).exists())
        self.assertContains(resp_post, 'was removed from')
        self.assertContains(resp_post, 'successfully.')

    def test_student_delete_via_ajax_returns_json(self):
        self.client.login(username='eval_clt', password='password123')
        delete_url = reverse('student_delete', args=[self.student_1.id])
        resp = self.client.post(delete_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(Student.objects.filter(id=self.student_1.id).exists())

    def test_student_delete_permission_denied_for_unauthorized_evaluator(self):
        self.client.login(username='eval_cok', password='password123')
        delete_url = reverse('student_delete', args=[self.student_1.id])
        resp = self.client.post(delete_url)
        # Should be redirected with error, student NOT deleted
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Student.objects.filter(id=self.student_1.id).exists())

    def test_batch_detail_has_remove_student_button_and_modal(self):
        self.client.login(username='eval_clt', password='password123')
        resp = self.client.get(reverse('batch_detail', args=[self.batch.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Remove')
        self.assertContains(resp, 'openRemoveStudentModal')
        self.assertContains(resp, 'removeStudentModal')

    def test_import_auto_generates_roll_number_when_omitted(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='eval_clt', password='password123')

        csv_content = (
            "Roll Number,Full Name,Email,Phone,Enrollment Date,Status,Notes\n"
            f",Rohan Varma,rohan@example.com,+91 9898989898,{self.batch.start_date.strftime('%Y-%m-%d')},ACTIVE,No roll given\n"
        ).encode('utf-8')

        uploaded_file = SimpleUploadedFile("students_no_roll.csv", csv_content, content_type="text/csv")
        resp = self.client.post(reverse('batch_student_import', args=[self.batch.id]), {
            'file': uploaded_file,
            'duplicate_action': 'skip',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        rohan = Student.objects.get(name='Rohan Varma')
        # Roll number should be auto-assigned based on batch
        self.assertEqual(rohan.roll_number, 'PFS-2026-002')
