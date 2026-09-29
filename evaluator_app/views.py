import csv
import io
import json
import random
import re
from datetime import datetime, date, timedelta
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Location, UserProfile, Batch, Student, DailyEvaluation, Attendance, StudentTask,
    Project, ProjectUpdate, BatchScheduleException, generate_batch_student_roll_number,
    Syllabus, SyllabusTask, BatchSyllabus, BatchTaskSchedule, BatchGroup
)
from .forms import (
    BatchForm, StudentForm, DailyEvaluationForm, AttendanceForm,
    LocationForm, EvaluatorAssignmentForm, StudentTaskForm, QuickTaskAssignForm,
    ProjectForm, ProjectProgressUpdateForm, ProjectEvaluationForm, TaskEvaluationForm,
    BatchGroupForm
)
from .decorators import (
    admin_required, evaluator_required,
    get_user_batches, get_user_students,
    can_user_access_batch, can_user_access_location
)


# ==============================================================================
# AUTHENTICATION VIEWS
# ==============================================================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                next_url = request.GET.get('next') or 'dashboard'
                return redirect(next_url)
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
        
    return render(request, 'evaluator_app/auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')


def quick_login_view(request, role):
    credentials = {
        'admin': ('admin', 'admin123'),
        'eva': ('eva', 'eva123'),
        'eva_kochi': ('eva_kochi', 'kochi123'),
        'eva_wayanad': ('eva_wayanad', 'wayanad123'),
    }
    
    if role in credentials:
        username, password = credentials[role]
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Logged in as {user.username.upper()} ({role}).")
            return redirect('dashboard')
            
    messages.error(request, "Could not quick login. User credentials not initialized.")
    return redirect('login')


# ==============================================================================
# DASHBOARD
# ==============================================================================

@evaluator_required
def dashboard_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    accessible_batches = get_user_batches(user)
    
    # Auto-mark missing attendance for past days
    from .services import auto_mark_absent_for_past_days
    auto_mark_absent_for_past_days(accessible_batches)
    
    accessible_students = get_user_students(user)
    today = timezone.now().date()
    
    # Calculate key metrics
    total_batches = accessible_batches.count()
    total_students = accessible_students.count()
    active_students = accessible_students.filter(status='ACTIVE').count()
    
    # Today's evaluations & attendance stats
    today_evaluations_count = DailyEvaluation.objects.filter(
        batch__in=accessible_batches, date=today
    ).count()
    
    today_attendance = Attendance.objects.filter(
        batch__in=accessible_batches, date=today
    )
    today_present_count = today_attendance.filter(status__in=['PRESENT', 'LATE']).count()
    today_attendance_total = today_attendance.count()
    today_attendance_rate = round((today_present_count / today_attendance_total * 100), 1) if today_attendance_total > 0 else 0
    
    # Global / Scoped Average Evaluation Score
    all_evals = DailyEvaluation.objects.filter(batch__in=accessible_batches)
    avg_score_data = all_evals.aggregate(
        avg_total=Avg('total_score'),
        avg_pres=Avg('presentation_score'),
        avg_prob=Avg('problem_solving_score'),
        avg_comm=Avg('communication_score'),
        avg_punct=Avg('punctuality_score'),
        avg_tutor=Avg('tutor_interaction_score'),
        avg_study=Avg('tendency_to_study_score')
    )
    avg_score = round(avg_score_data['avg_total'] or 0, 1)
    
    # Tasks Tracking Metrics for Dashboard
    tasks_qs = StudentTask.objects.filter(batch__in=accessible_batches)
    total_tasks_count = tasks_qs.count()
    pending_tasks_count = tasks_qs.filter(status='PENDING').count()
    completed_tasks_count = tasks_qs.filter(status='COMPLETED').count()
    late_tasks_count = tasks_qs.filter(status='LATE').count()
    overdue_tasks_count = tasks_qs.filter(status='PENDING', due_date__lt=today).count()
    tasks_evaluated_count = tasks_qs.filter(is_evaluated=True).count()
    tasks_unevaluated_count = tasks_qs.filter(is_evaluated=False).count()
    
    # Recent tasks list for quick dashboard monitoring
    recent_tasks = tasks_qs.select_related('student', 'batch', 'assigned_by')[:50]
    
    # Quick task assignment form
    quick_task_form = QuickTaskAssignForm(user=user)
    
    # Recent evaluations feed
    recent_evaluations = all_evals.select_related('student', 'batch', 'evaluator')[:8]
    
    # Location summary breakdown (especially useful for Admin)
    locations_summary = []
    for loc in profile.get_accessible_locations():
        loc_batches = accessible_batches.filter(location=loc)
        loc_students = Student.objects.filter(batch__in=loc_batches)
        loc_evals = DailyEvaluation.objects.filter(batch__in=loc_batches)
        loc_avg = loc_evals.aggregate(Avg('total_score'))['total_score__avg']
        locations_summary.append({
            'location': loc,
            'batch_count': loc_batches.count(),
            'student_count': loc_students.count(),
            'avg_score': round(loc_avg, 1) if loc_avg else 0,
            'evaluators': loc.evaluators.select_related('user')
        })

    # Recent batches with details
    recent_batches = accessible_batches[:6]
    
    # Last 7 days evaluation activity chart data
    chart_dates = []
    chart_eval_counts = []
    chart_avg_scores = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_evals = DailyEvaluation.objects.filter(batch__in=accessible_batches, date=d)
        chart_dates.append(d.strftime('%b %d'))
        chart_eval_counts.append(d_evals.count())
        d_avg = d_evals.aggregate(Avg('total_score'))['total_score__avg']
        chart_avg_scores.append(round(d_avg or 0, 1))

    # Top performing students
    top_students = accessible_students.annotate(
        overall_avg=Avg('evaluations__total_score')
    ).filter(overall_avg__isnull=False).order_by('-overall_avg')[:5]

    # Low Attendance Students (< 50%) across accessible batches
    low_attendance_students = []
    for stu in accessible_students.select_related('batch', 'batch__location'):
        total_att = stu.attendance_records.count()
        if total_att > 0:
            pct = stu.attendance_percentage
            if pct < 50.0:
                present_num = stu.attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
                absent_num = stu.attendance_records.filter(status='ABSENT').count()
                low_attendance_students.append({
                    'student': stu,
                    'attendance_pct': pct,
                    'total_sessions': total_att,
                    'present_count': present_num,
                    'absent_count': absent_num,
                    'batch': stu.batch,
                })
    low_attendance_students.sort(key=lambda x: x['attendance_pct'])
    low_attendance_count = len(low_attendance_students)

    # Student Projects Metrics
    projects_qs = Project.objects.filter(batch__in=accessible_batches).prefetch_related('students', 'batch')
    total_projects_count = projects_qs.count()
    in_progress_projects_count = projects_qs.filter(status='IN_PROGRESS').count()
    completed_projects_count = projects_qs.filter(status='COMPLETED').count()
    review_projects_count = projects_qs.filter(status='UNDER_REVIEW').count()
    avg_project_progress = round(projects_qs.aggregate(Avg('progress_percentage'))['progress_percentage__avg'] or 0, 1) if total_projects_count > 0 else 0
    recent_projects = projects_qs.order_by('-updated_at')[:6]

    context = {
        'total_batches': total_batches,
        'total_students': total_students,
        'active_students': active_students,
        'today_evaluations_count': today_evaluations_count,
        'today_attendance_rate': today_attendance_rate,
        'avg_score': avg_score,
        'avg_score_data': avg_score_data,
        'recent_evaluations': recent_evaluations,
        'locations_summary': locations_summary,
        'recent_batches': recent_batches,
        'top_students': top_students,
        'chart_dates_json': json.dumps(chart_dates),
        'chart_eval_counts_json': json.dumps(chart_eval_counts),
        'chart_avg_scores_json': json.dumps(chart_avg_scores),
        # Task Metrics & Data
        'total_tasks_count': total_tasks_count,
        'pending_tasks_count': pending_tasks_count,
        'completed_tasks_count': completed_tasks_count,
        'late_tasks_count': late_tasks_count,
        'overdue_tasks_count': overdue_tasks_count,
        'tasks_evaluated_count': tasks_evaluated_count,
        'tasks_unevaluated_count': tasks_unevaluated_count,
        'recent_tasks': recent_tasks,
        'quick_task_form': quick_task_form,
        # Low Attendance Alert (<50%)
        'low_attendance_students': low_attendance_students,
        'low_attendance_count': low_attendance_count,
        # Project Metrics
        'total_projects_count': total_projects_count,
        'in_progress_projects_count': in_progress_projects_count,
        'completed_projects_count': completed_projects_count,
        'review_projects_count': review_projects_count,
        'avg_project_progress': avg_project_progress,
        'recent_projects': recent_projects,
    }
    return render(request, 'evaluator_app/dashboard.html', context)


# ==============================================================================
# BATCH MANAGEMENT
# ==============================================================================

@evaluator_required
def batch_group_list_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.is_admin:
        groups = BatchGroup.objects.all().prefetch_related('batches')
    else:
        # Evaluators see groups that contain at least one batch they have access to
        assigned_locations = profile.assigned_locations.filter(is_active=True)
        groups = BatchGroup.objects.filter(batches__location__in=assigned_locations).distinct().prefetch_related('batches')
        
    return render(request, 'evaluator_app/batches/batch_group_list.html', {
        'title': 'Merged Batch Groups',
        'groups': groups
    })

@admin_required
def batch_group_create_view(request):
    if request.method == 'POST':
        form = BatchGroupForm(request.POST, user=request.user)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()
            form.save_m2m()
            messages.success(request, f"Merged Batch Group '{group.name}' created successfully.")
            return redirect('batch_group_list')
    else:
        form = BatchGroupForm(user=request.user)
    return render(request, 'evaluator_app/batches/batch_group_form.html', {
        'title': 'Create Merged Batch Group',
        'form': form
    })

@admin_required
def batch_group_edit_view(request, group_id):
    group = get_object_or_404(BatchGroup, id=group_id)
    if request.method == 'POST':
        form = BatchGroupForm(request.POST, instance=group, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Merged Batch Group '{group.name}' updated successfully.")
            return redirect('batch_group_list')
    else:
        form = BatchGroupForm(instance=group, user=request.user)
    return render(request, 'evaluator_app/batches/batch_group_form.html', {
        'title': 'Edit Merged Batch Group',
        'form': form,
        'group': group
    })

@admin_required
def batch_group_delete_view(request, group_id):
    group = get_object_or_404(BatchGroup, id=group_id)
    if request.method == 'POST':
        group_name = group.name
        group.delete()
        messages.success(request, f"Merged Batch Group '{group_name}' deleted successfully.")
        return redirect('batch_group_list')
    messages.error(request, "Invalid method for deletion.")
    return redirect('batch_group_list')



@evaluator_required
def batch_list_view(request):
    user = request.user
    base_batches = get_user_batches(user)
    
    # Overview counts for filter pills and summary bar
    total_count = base_batches.count()
    daily_count = base_batches.filter(schedule_type='DAILY').count()
    weekly_count = base_batches.filter(schedule_type='WEEKLY').count()
    total_students_count = Student.objects.filter(batch__in=base_batches).count()

    batches = base_batches
    
    # Filter by Schedule Type
    schedule_filter = request.GET.get('schedule')
    if schedule_filter in ['DAILY', 'WEEKLY']:
        batches = batches.filter(schedule_type=schedule_filter)
        
    # Filter by Location
    location_id = request.GET.get('location')
    if location_id:
        batches = batches.filter(location_id=location_id)
        
    # Search query
    q = request.GET.get('q')
    if q:
        batches = batches.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q)
        )
        
    context = {
        'batches': batches,
        'selected_schedule': schedule_filter or '',
        'selected_location': location_id or '',
        'search_query': q or '',
        'total_count': total_count,
        'daily_count': daily_count,
        'weekly_count': weekly_count,
        'total_students_count': total_students_count,
    }
    return render(request, 'evaluator_app/batches/batch_list.html', context)


@evaluator_required
def batch_create_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        form = BatchForm(request.POST, user=user)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.created_by = user
            
            # Security check: verify evaluator can assign to this location
            if not profile.can_access_location(batch.location):
                messages.error(request, "Permission denied: You cannot create batches in this location.")
                return render(request, 'evaluator_app/batches/batch_form.html', {'form': form, 'title': 'Create New Batch'})
                
            batch.save()
            messages.success(request, f"Batch '{batch.name}' created successfully!")
            return redirect('batch_detail', batch_id=batch.id)
    else:
        form = BatchForm(user=user)
        
    return render(request, 'evaluator_app/batches/batch_form.html', {
        'form': form,
        'title': 'Create New Batch',
        'is_create': True
    })


@evaluator_required
def batch_detail_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    
    # Permission verification
    if not can_user_access_batch(user, batch):
        messages.error(request, "Access denied: You are not assigned to this batch's location.")
        return redirect('batch_list')
        
    students = batch.students.all()
    today = timezone.now().date()
    
    # Today's evaluations for this batch
    today_evaluations = DailyEvaluation.objects.filter(batch=batch, date=today)
    evaluated_student_ids = set(today_evaluations.values_list('student_id', flat=True))
    
    # Recent evaluations in this batch
    recent_evaluations = batch.evaluations.select_related('student', 'evaluator')[:10]
    
    # Batch statistics
    avg_score = batch.average_score
    attendance_rate = batch.attendance_percentage
    
    context = {
        'batch': batch,
        'students': students,
        'evaluated_student_ids': evaluated_student_ids,
        'today_eval_count': len(evaluated_student_ids),
        'pending_eval_count': max(0, students.count() - len(evaluated_student_ids)),
        'recent_evaluations': recent_evaluations,
        'avg_score': avg_score,
        'attendance_rate': attendance_rate,
        'today_date': today,
    }
    return render(request, 'evaluator_app/batches/batch_detail.html', context)


@evaluator_required
def batch_edit_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    
    if not can_user_access_batch(user, batch):
        messages.error(request, "Access denied: You cannot edit this batch.")
        return redirect('batch_list')
        
    if request.method == 'POST':
        form = BatchForm(request.POST, instance=batch, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Batch '{batch.name}' updated successfully!")
            return redirect('batch_detail', batch_id=batch.id)
    else:
        form = BatchForm(instance=batch, user=user)
        
    return render(request, 'evaluator_app/batches/batch_form.html', {
        'form': form,
        'batch': batch,
        'title': f'Edit Batch: {batch.name}',
        'is_create': False
    })


@admin_required
def batch_delete_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    
    if not can_user_access_batch(user, batch):
        messages.error(request, "Access denied.")
        return redirect('batch_list')
        
    if request.method == 'POST':
        name = batch.name
        batch.delete()
        messages.success(request, f"Batch '{name}' has been deleted.")
        return redirect('batch_list')
        
    return render(request, 'evaluator_app/batches/batch_confirm_delete.html', {'batch': batch})


# ==============================================================================
# STUDENT MANAGEMENT
# ==============================================================================

@evaluator_required
def student_add_view(request, batch_id=None):
    user = request.user
    if not batch_id:
        batch_id = request.GET.get('batch_id') or request.GET.get('batch')
    initial_batch = None
    if batch_id:
        initial_batch = get_object_or_404(Batch, id=batch_id)
        if not can_user_access_batch(user, initial_batch):
            messages.error(request, "Access denied to this batch.")
            return redirect('batch_list')
            
    if request.method == 'POST':
        form = StudentForm(request.POST, user=user, initial_batch=initial_batch)
        if form.is_valid():
            student = form.save(commit=False)
            if initial_batch:
                student.batch = initial_batch
            if not can_user_access_batch(user, student.batch):
                messages.error(request, "Permission denied for the selected batch.")
                return render(request, 'evaluator_app/students/student_form.html', {'form': form, 'initial_batch': initial_batch, 'title': 'Add Student'})
            student.save()
            messages.success(request, f"Student '{student.name}' added successfully to {student.batch.name}!")
            return redirect('batch_detail', batch_id=student.batch.id)
    else:
        form = StudentForm(user=user, initial_batch=initial_batch)
        
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.is_admin:
        batches_qs = Batch.objects.all()
    else:
        batches_qs = Batch.objects.filter(location__in=profile.assigned_locations.all())
    import json
    batch_start_dates = {
        str(b.id): b.start_date.strftime('%Y-%m-%d')
        for b in batches_qs if b.start_date
    }

    return render(request, 'evaluator_app/students/student_form.html', {
        'form': form,
        'initial_batch': initial_batch,
        'batch_start_dates_json': json.dumps(batch_start_dates),
        'title': f"Add Student to {initial_batch.name}" if initial_batch else 'Add New Student'
    })


@evaluator_required
def student_detail_view(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    
    if not can_user_access_batch(user, student.batch):
        messages.error(request, "Access denied to this student record.")
        return redirect('batch_list')
        
    evaluations = student.evaluations.all()
    
    # Calculate historical attendance points
    history_records = []
    batch = student.batch
    if batch and batch.start_date:
        DAYS_MAP = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        class_days_str = batch.class_days.lower()
        valid_weekdays = [v for k, v in DAYS_MAP.items() if k in class_days_str]
        
        today = timezone.now().date()
        check_date = batch.start_date
        
        past_dates = []
        while check_date <= today:
            if check_date.weekday() in valid_weekdays:
                past_dates.append(check_date)
            check_date += timedelta(days=1)
            
        past_dates = sorted(past_dates, reverse=True)[:30] # take last 30 class days
        
        # apply class exceptions
        actual_dates = []
        exceptions = BatchScheduleException.objects.filter(batch=batch, original_date__in=past_dates)
        ex_map = {ex.original_date: ex for ex in exceptions}
        for d in past_dates:
            ex = ex_map.get(d)
            if ex:
                if ex.rescheduled_date and ex.rescheduled_date <= today:
                    actual_dates.append(ex.rescheduled_date)
            else:
                actual_dates.append(d)
                
        actual_dates = sorted(actual_dates, reverse=True)[:30]
        
        existing_att = Attendance.objects.filter(student=student, date__in=actual_dates)
        att_map = {att.date: att.status for att in existing_att}
        
        for d in actual_dates:
            status = att_map.get(d, 'Not Marked/Absent')
            history_records.append({'date': d, 'status': status})
    else:
        # Fallback if no start_date
        history_records = [{'date': a.date, 'status': a.status} for a in student.attendance_records.all().order_by('-date')[:30]]

    # Calculate performance metrics averages
    eval_stats = evaluations.aggregate(
        avg_punct=Avg('punctuality_score'),
        avg_tutor_int=Avg('tutor_interaction_score'),
        avg_peer_int=Avg('classmate_interaction_score'),
        avg_study_ten=Avg('tendency_to_study_score'),
        avg_pres=Avg('presentation_score'),
        avg_prob=Avg('problem_solving_score'),
        avg_ppt=Avg('ppt_evaluation_score'),
        avg_comm=Avg('communication_score'),
        avg_sugg=Avg('suggestion_implementation_score'),
        avg_doubt=Avg('doubt_clearing_score'),
        avg_total=Avg('total_score'),
        avg_tasks_given=Avg('tasks_given'),
        avg_tasks_completed=Avg('tasks_completed'),
    )
    
    # Attendance breakdown
    att_present = student.attendance_records.filter(status='PRESENT').count()
    att_late = student.attendance_records.filter(status='LATE').count()
    att_absent = student.attendance_records.filter(status='ABSENT').count()
    att_excused = student.attendance_records.filter(status='EXCUSED').count()
    total_att = student.attendance_records.count()
    att_percentage = round(((att_present + att_late) / total_att * 100), 1) if total_att > 0 else 0
    
    # Score progression chart data
    prog_dates = []
    prog_scores = []
    for ev in evaluations.order_by('date')[:20]:
        prog_dates.append(ev.date.strftime('%d %b'))
        prog_scores.append(ev.total_score)
        
    # Multi-axis skill radar breakdown
    radar_labels = [
        'Behavior & Study',
        'Presentation',
        'Problem Solving',
        'PPT & Docs',
        'Communication',
        'Doubt & Feedback'
    ]
    
    behavior_avg = round(((eval_stats['avg_punct'] or 80) + (eval_stats['avg_study_ten'] or 80) + (eval_stats['avg_tutor_int'] or 80)) / 3, 1)
    doubt_feedback_avg = round(((eval_stats['avg_sugg'] or 80) + (eval_stats['avg_doubt'] or 80)) / 2, 1)
    
    radar_metrics = [
        behavior_avg,
        round(eval_stats['avg_pres'] or 75, 1),
        round(eval_stats['avg_prob'] or 75, 1),
        round(eval_stats['avg_ppt'] or 75, 1),
        round(eval_stats['avg_comm'] or 75, 1),
        doubt_feedback_avg,
    ]

    # Student tasks
    student_tasks_qs = student.tasks.all().select_related('assigned_by')
    tasks_pending_count = student_tasks_qs.filter(status='PENDING').count()
    tasks_completed_count = student_tasks_qs.filter(status__in=['COMPLETED', 'LATE']).count()
    tasks_late_count = student_tasks_qs.filter(status='LATE').count()
    tasks_overdue_count = student_tasks_qs.filter(status='PENDING', due_date__lt=timezone.now().date()).count()

    student_tasks = list(student_tasks_qs)
    task_dates = [t.assigned_date for t in student_tasks if t.assigned_date]
    attendances = Attendance.objects.filter(student=student, date__in=task_dates)
    attendance_map = {att.date: att.status for att in attendances}
    
    today = timezone.now().date()
    for task in student_tasks:
        if task.assigned_date:
            if task.assigned_date > today:
                task.attendance_status = 'UPCOMING'
            else:
                task.attendance_status = attendance_map.get(task.assigned_date, 'NOT MARKED')
        else:
            task.attendance_status = 'N/A'

    # Student projects
    student_projects = student.projects.all().prefetch_related('students', 'batch').order_by('-updated_at')
    projects_in_progress_count = student_projects.filter(status='IN_PROGRESS').count()
    projects_completed_count = student_projects.filter(status='COMPLETED').count()

    # Check if evaluated today
    has_evaluated_today = DailyEvaluation.objects.filter(student=student, date=timezone.now().date()).exists()

    context = {
        'student': student,
        'has_evaluated_today': has_evaluated_today,
        'evaluations': evaluations,
        'attendance_records': history_records,
        'eval_stats': eval_stats,
        'att_present': att_present,
        'att_late': att_late,
        'att_absent': att_absent,
        'att_excused': att_excused,
        'att_percentage': att_percentage,
        'total_att': total_att,
        'prog_dates_json': json.dumps(prog_dates),
        'prog_scores_json': json.dumps(prog_scores),
        'radar_labels_json': json.dumps(radar_labels),
        'radar_metrics_json': json.dumps(radar_metrics),
        # Student Tasks
        'student_tasks': student_tasks,
        'tasks_pending_count': tasks_pending_count,
        'tasks_completed_count': tasks_completed_count,
        'tasks_late_count': tasks_late_count,
        'tasks_overdue_count': tasks_overdue_count,
        # Student Projects
        'student_projects': student_projects,
        'projects_in_progress_count': projects_in_progress_count,
        'projects_completed_count': projects_completed_count,
    }
    return render(request, 'evaluator_app/students/student_detail.html', context)


@evaluator_required
def student_report_download_view(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if not can_user_access_batch(request.user, student.batch):
        messages.error(request, 'Permission denied.')
        return redirect('student_list')
        
    format_type = request.GET.get('format', 'pdf')
    
    attendance_records = student.attendance_records.all().order_by('-date')
    eval_stats = student.evaluations.aggregate(
        avg_pres=Avg('presentation_score'),
        avg_prob=Avg('problem_solving_score'),
        avg_comm=Avg('communication_score'),
        avg_punct=Avg('punctuality_score'),
        avg_tutor_int=Avg('tutor_interaction_score'),
        avg_peer_int=Avg('classmate_interaction_score'),
        avg_study_ten=Avg('tendency_to_study_score'),
        avg_ppt=Avg('ppt_evaluation_score'),
        avg_tasks_given=Avg('tasks_given'),
        avg_tasks_completed=Avg('tasks_completed'),
    )
    evaluations = student.evaluations.all().order_by('-date')
    tasks = student.tasks.all().order_by('-assigned_date')
    
    batch_students = student.batch.students.filter(status='ACTIVE')
    
    from .models import Attendance, StudentTask
    batch_att_total = Attendance.objects.filter(student__in=batch_students).count()
    batch_att_present = Attendance.objects.filter(student__in=batch_students, status__in=['PRESENT', 'LATE']).count()
    batch_avg_att = round((batch_att_present / batch_att_total * 100), 1) if batch_att_total else 0
    
    batch_task_total = StudentTask.objects.filter(student__in=batch_students).count()
    batch_task_completed = StudentTask.objects.filter(student__in=batch_students, status='COMPLETED').count()
    batch_avg_task = round((batch_task_completed / batch_task_total * 100), 1) if batch_task_total else 0
    
    batch_comparison = {
        'avg_attendance': batch_avg_att,
        'avg_task_completion': batch_avg_task
    }
    
    from .reports import generate_student_pdf_report, generate_student_docx_report, generate_student_excel_report
    
    if format_type == 'xlsx':
        output = generate_student_excel_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison)
        response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="Report_{student.roll_number}.xlsx"'
        return response
    elif format_type == 'docx':
        output = generate_student_docx_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison)
        response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename="Report_{student.roll_number}.docx"'
        return response
    else: # pdf
        output = generate_student_pdf_report(student, attendance_records, eval_stats, evaluations, tasks, batch_comparison)
        response = HttpResponse(output, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Report_{student.roll_number}.pdf"'
        return response

@evaluator_required
def student_edit_view(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    
    if not can_user_access_batch(user, student.batch):
        messages.error(request, "Access denied.")
        return redirect('batch_list')
        
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student, user=user, initial_batch=student.batch)
        if form.is_valid():
            form.save()
            messages.success(request, f"Student '{student.name}' updated successfully!")
            return redirect('student_detail', student_id=student.id)
    else:
        form = StudentForm(instance=student, user=user, initial_batch=student.batch)
        
    return render(request, 'evaluator_app/students/student_form.html', {
        'form': form,
        'student': student,
        'initial_batch': student.batch,
        'title': f'Edit Student: {student.name}'
    })


@evaluator_required
def student_delete_view(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    batch = student.batch
    batch_id = batch.id
    student_name = student.name
    student_roll = student.roll_number

    if not can_user_access_batch(user, batch):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)
        messages.error(request, "Access denied.")
        return redirect('batch_list')

    if request.method == 'POST':
        student.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f"Student '{student_name}' ({student_roll}) removed from '{batch.name}' successfully."
            })
        messages.success(request, f"Student '{student_name}' ({student_roll}) was removed from '{batch.name}' successfully.")
        return redirect('batch_detail', batch_id=batch_id)

    return render(request, 'evaluator_app/students/student_confirm_delete.html', {'student': student, 'batch': batch})


# ==============================================================================
# DAILY EVALUATION HUB
# ==============================================================================

@evaluator_required
def evaluation_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    
    batch_id = request.GET.get('batch_id')
    date_str = request.GET.get('date')
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')
    
    today = timezone.now().date()
    selected_date = today
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
            
    selected_batch = None
    if batch_id:
        selected_batch = accessible_batches.filter(id=batch_id).first()
    elif accessible_batches.exists():
        day_name = selected_date.strftime('%A')
        batches_for_day = [b for b in accessible_batches if day_name in b.class_days]
        if batches_for_day:
            selected_batch = batches_for_day[0]
        else:
            selected_batch = accessible_batches.first()
        
    students_data = []
    avg_score = 0.0
    if selected_batch:
        students = selected_batch.students.all().order_by('roll_number', 'name')
        evaluations_qs = DailyEvaluation.objects.filter(batch=selected_batch, date=selected_date)
        evaluations_dict = {ev.student_id: ev for ev in evaluations_qs}
        
        for stu in students:
            eval_record = evaluations_dict.get(stu.id)
            students_data.append({
                'student': stu,
                'evaluation': eval_record,
                'is_evaluated': eval_record is not None,
                'attendance_pct': stu.attendance_percentage,
                'pending_tasks_count': stu.tasks.filter(status='PENDING').count(),
            })

        avg_val = evaluations_qs.aggregate(avg=Avg('total_score'))['avg']
        if avg_val is not None:
            avg_score = round(avg_val, 1)
            
    evaluated_count = sum(1 for s in students_data if s['is_evaluated'])
    total_students_in_batch = len(students_data)
    pending_count = total_students_in_batch - evaluated_count
    completion_rate = round((evaluated_count / total_students_in_batch) * 100, 1) if total_students_in_batch > 0 else 0.0

    # Apply filters for display
    display_students = students_data
    if status_filter == 'pending':
        display_students = [s for s in display_students if not s['is_evaluated']]
    elif status_filter == 'evaluated':
        display_students = [s for s in display_students if s['is_evaluated']]

    if search_query:
        q_lower = search_query.lower()
        display_students = [
            s for s in display_students
            if q_lower in s['student'].name.lower()
            or q_lower in s['student'].roll_number.lower()
            or (s['student'].email and q_lower in s['student'].email.lower())
        ]

    from datetime import timedelta
    prev_date = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (selected_date + timedelta(days=1)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    is_today = (selected_date == today)

    context = {
        'accessible_batches': accessible_batches,
        'selected_batch': selected_batch,
        'selected_date': selected_date.strftime('%Y-%m-%d'),
        'selected_date_display': selected_date.strftime('%B %d, %Y'),
        'prev_date': prev_date,
        'next_date': next_date,
        'today_str': today_str,
        'is_today': is_today,
        'students_data': display_students,
        'all_students_count': total_students_in_batch,
        'evaluated_count': evaluated_count,
        'pending_count': pending_count,
        'total_students': total_students_in_batch,
        'completion_rate': completion_rate,
        'avg_score': avg_score,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'evaluator_app/evaluations/evaluation_hub.html', context)


@evaluator_required
def student_evaluate_view(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    
    if not can_user_access_batch(user, student.batch):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        
    date_str = request.GET.get('date') or request.POST.get('date')
    today = timezone.now().date()
    eval_date = today
    if date_str:
        try:
            eval_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            eval_date = today

    evaluation = DailyEvaluation.objects.filter(student=student, date=eval_date).first()

    is_admin = hasattr(user, 'profile') and user.profile.is_admin

    if evaluation and not is_admin:
        messages.error(request, "Evaluation already completed. Only administrators can edit existing evaluations.")
        return redirect(f"/evaluations/?batch_id={student.batch.id}&date={eval_date.strftime('%Y-%m-%d')}")

    if request.method == 'POST':
        data = request.POST
        topic = data.get('topic', 'Daily Practical & Concept Evaluation')
        
        # Behavioral
        punct = float(data.get('punctuality_score', 80))
        tutor_int = float(data.get('tutor_interaction_score', 80))
        peer_int = float(data.get('classmate_interaction_score', 80))
        study_ten = float(data.get('tendency_to_study_score', 80))
        
        # Tasks
        tasks_given = int(data.get('tasks_given', 5))
        tasks_completed = int(data.get('tasks_completed', 5))
        
        # Project / Task
        pres = float(data.get('presentation_score', 75))
        prob = float(data.get('problem_solving_score', 75))
        ppt_eval = float(data.get('ppt_evaluation_score', 75))
        ppt_slide_count = int(data.get('ppt_slide_count', 0) or 0)
        ppt_has_images = data.get('ppt_has_images') in ['true', 'on', '1', True]
        ppt_notes = data.get('ppt_explanation_notes', '')
        
        # Communication
        comm = float(data.get('communication_score', 75))
        sugg = float(data.get('suggestion_implementation_score', 80))
        doubt = float(data.get('doubt_clearing_score', 75))
        
        # Remarks
        strongest = data.get('strongest_areas', '')
        improvements = data.get('areas_for_improvement', '')
        interested = data.get('interested_areas', '')
        general_rem = data.get('general_remarks', '')

        if evaluation:
            evaluation.topic = topic
            evaluation.attendance_percentage = student.attendance_percentage
            evaluation.punctuality_score = punct
            evaluation.tutor_interaction_score = tutor_int
            evaluation.classmate_interaction_score = peer_int
            evaluation.tendency_to_study_score = study_ten
            evaluation.tasks_given = tasks_given
            evaluation.tasks_completed = tasks_completed
            evaluation.presentation_score = pres
            evaluation.problem_solving_score = prob
            evaluation.ppt_evaluation_score = ppt_eval
            evaluation.ppt_slide_count = ppt_slide_count
            evaluation.ppt_has_images = ppt_has_images
            evaluation.ppt_explanation_notes = ppt_notes
            evaluation.communication_score = comm
            evaluation.suggestion_implementation_score = sugg
            evaluation.doubt_clearing_score = doubt
            evaluation.strongest_areas = strongest
            evaluation.areas_for_improvement = improvements
            evaluation.interested_areas = interested
            evaluation.general_remarks = general_rem
            # Evaluator is NOT overwritten when an admin edits.
            evaluation.save()
        else:
            evaluation = DailyEvaluation.objects.create(
                student=student,
                batch=student.batch,
                evaluator=user,
                date=eval_date,
                topic=topic,
                attendance_percentage=student.attendance_percentage,
                punctuality_score=punct,
                tutor_interaction_score=tutor_int,
                classmate_interaction_score=peer_int,
                tendency_to_study_score=study_ten,
                tasks_given=tasks_given,
                tasks_completed=tasks_completed,
                presentation_score=pres,
                problem_solving_score=prob,
                ppt_evaluation_score=ppt_eval,
                ppt_slide_count=ppt_slide_count,
                ppt_has_images=ppt_has_images,
                ppt_explanation_notes=ppt_notes,
                communication_score=comm,
                suggestion_implementation_score=sugg,
                doubt_clearing_score=doubt,
                strongest_areas=strongest,
                areas_for_improvement=improvements,
                interested_areas=interested,
                general_remarks=general_rem,
            )

        # Handle optional new task created directly from evaluation
        new_task_title = data.get('new_task_title', '').strip()
        if new_task_title:
            new_task_due = data.get('new_task_due_date') or None
            new_task_prio = data.get('new_task_priority', 'NORMAL')
            new_task_desc = data.get('new_task_description', '')
            StudentTask.objects.create(
                student=student,
                batch=student.batch,
                assigned_by=user,
                daily_evaluation=evaluation,
                title=new_task_title,
                description=new_task_desc,
                assigned_date=eval_date,
                due_date=new_task_due,
                priority=new_task_prio,
                status='PENDING'
            )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({
                'success': True,
                'message': f"Evaluation for {student.name} saved successfully!",
                'total_score': evaluation.total_score,
                'grade': evaluation.grade,
                'eval_id': evaluation.id
            })

        messages.success(request, f"Daily evaluation for {student.name} recorded ({evaluation.total_score}% - Grade {evaluation.grade})")
        return redirect(f"/evaluations/?batch_id={student.batch.id}&date={eval_date.strftime('%Y-%m-%d')}")

    # GET Request: return JSON data for modal populating
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        # Fetch student's assigned tasks
        tasks_data = []
        for t in student.tasks.order_by('-assigned_date', '-created_at')[:8]:
            tasks_data.append({
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'assigned_date': t.assigned_date.strftime('%Y-%m-%d'),
                'assigned_date_display': t.assigned_date.strftime('%b %d, %Y'),
                'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
                'due_date_display': t.due_date.strftime('%b %d, %Y') if t.due_date else '—',
                'completed_at': t.completed_at.strftime('%Y-%m-%dT%H:%M') if t.completed_at else '',
                'completed_at_display': t.completed_at.strftime('%b %d, %Y - %I:%M %p') if t.completed_at else 'Pending',
                'status': t.status,
                'computed_status': t.computed_status,
                'priority': t.priority,
                'evaluator_remarks': t.evaluator_remarks,
            })

        return JsonResponse({
            'student_id': student.id,
            'student_name': student.name,
            'roll_number': student.roll_number,
            'batch_name': student.batch.name,
            'date': eval_date.strftime('%Y-%m-%d'),
            'attendance_percentage': student.attendance_percentage,
            'topic': evaluation.topic if evaluation else 'Daily Practical & Concept Evaluation',
            # Behavioral
            'punctuality_score': evaluation.punctuality_score if evaluation else 85,
            'tutor_interaction_score': evaluation.tutor_interaction_score if evaluation else 80,
            'classmate_interaction_score': evaluation.classmate_interaction_score if evaluation else 80,
            'tendency_to_study_score': evaluation.tendency_to_study_score if evaluation else 80,
            # Tasks
            'tasks_given': evaluation.tasks_given if evaluation else 5,
            'tasks_completed': evaluation.tasks_completed if evaluation else 5,
            # Project
            'presentation_score': evaluation.presentation_score if evaluation else 75,
            'problem_solving_score': evaluation.problem_solving_score if evaluation else 75,
            'ppt_evaluation_score': evaluation.ppt_evaluation_score if evaluation else 75,
            'ppt_slide_count': evaluation.ppt_slide_count if evaluation else 6,
            'ppt_has_images': evaluation.ppt_has_images if evaluation else True,
            'ppt_explanation_notes': evaluation.ppt_explanation_notes if evaluation else 'Well structured diagrams & screenshots',
            # Communication
            'communication_score': evaluation.communication_score if evaluation else 75,
            'suggestion_implementation_score': evaluation.suggestion_implementation_score if evaluation else 80,
            'doubt_clearing_score': evaluation.doubt_clearing_score if evaluation else 75,
            # Computed
            'total_score': evaluation.total_score if evaluation else 78.0,
            'grade': evaluation.grade if evaluation else 'B+',
            # Remarks
            'strongest_areas': evaluation.strongest_areas if evaluation else '',
            'areas_for_improvement': evaluation.areas_for_improvement if evaluation else '',
            'interested_areas': evaluation.interested_areas if evaluation else '',
            'general_remarks': evaluation.general_remarks if evaluation else '',
            'is_evaluated': evaluation is not None,
            'tasks': tasks_data,
        })

    # Fallback full page form
    form = DailyEvaluationForm(instance=evaluation)
    return render(request, 'evaluator_app/evaluations/evaluation_form.html', {
        'form': form,
        'student': student,
        'date': eval_date,
        'evaluation': evaluation
    })

@evaluator_required
def batch_bulk_evaluate_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('evaluation_hub')

    eval_date = timezone.now().date()
    if request.GET.get('date'):
        try:
            eval_date = datetime.strptime(request.GET.get('date'), '%Y-%m-%d').date()
        except ValueError:
            pass

    if request.method == 'POST':
        data = request.POST
        topic = data.get('topic', 'Daily Practical & Concept Evaluation')
        
        # Behavioral
        punct = float(data.get('punctuality_score', 80))
        tutor_int = float(data.get('tutor_interaction_score', 80))
        peer_int = float(data.get('classmate_interaction_score', 80))
        study_ten = float(data.get('tendency_to_study_score', 80))
        
        # Tasks
        tasks_given = int(data.get('tasks_given', 5))
        tasks_completed = int(data.get('tasks_completed', 5))
        
        # Project / Task
        pres = float(data.get('presentation_score', 75))
        prob = float(data.get('problem_solving_score', 75))
        ppt_eval = float(data.get('ppt_evaluation_score', 75))
        ppt_slide_count = int(data.get('ppt_slide_count', 0) or 0)
        ppt_has_images = data.get('ppt_has_images') in ['true', 'on', '1', True]
        ppt_notes = data.get('ppt_explanation_notes', '')
        
        # Communication
        comm = float(data.get('communication_score', 75))
        sugg = float(data.get('suggestion_implementation_score', 80))
        doubt = float(data.get('doubt_clearing_score', 75))
        
        # Remarks
        strongest = data.get('strongest_areas', '')
        improvements = data.get('areas_for_improvement', '')
        interested = data.get('interested_areas', '')
        general_rem = data.get('general_remarks', '')

        students = batch.students.filter(status='ACTIVE')
        created_count = 0
        updated_count = 0

        is_admin = hasattr(user, 'profile') and user.profile.is_admin

        for student in students:
            evaluation = DailyEvaluation.objects.filter(student=student, date=eval_date).first()
            if evaluation and not is_admin:
                continue # Skip if already evaluated and not admin

            if evaluation:
                evaluation.topic = topic
                evaluation.attendance_percentage = student.attendance_percentage
                evaluation.punctuality_score = punct
                evaluation.tutor_interaction_score = tutor_int
                evaluation.classmate_interaction_score = peer_int
                evaluation.tendency_to_study_score = study_ten
                evaluation.tasks_given = tasks_given
                evaluation.tasks_completed = tasks_completed
                evaluation.presentation_score = pres
                evaluation.problem_solving_score = prob
                evaluation.ppt_evaluation_score = ppt_eval
                evaluation.ppt_slide_count = ppt_slide_count
                evaluation.ppt_has_images = ppt_has_images
                evaluation.ppt_explanation_notes = ppt_notes
                evaluation.communication_score = comm
                evaluation.suggestion_implementation_score = sugg
                evaluation.doubt_clearing_score = doubt
                evaluation.strongest_areas = strongest
                evaluation.areas_for_improvement = improvements
                evaluation.interested_areas = interested
                evaluation.general_remarks = general_rem
                evaluation.save()
                updated_count += 1
            else:
                DailyEvaluation.objects.create(
                    student=student,
                    batch=batch,
                    evaluator=user,
                    date=eval_date,
                    topic=topic,
                    attendance_percentage=student.attendance_percentage,
                    punctuality_score=punct,
                    tutor_interaction_score=tutor_int,
                    classmate_interaction_score=peer_int,
                    tendency_to_study_score=study_ten,
                    tasks_given=tasks_given,
                    tasks_completed=tasks_completed,
                    presentation_score=pres,
                    problem_solving_score=prob,
                    ppt_evaluation_score=ppt_eval,
                    ppt_slide_count=ppt_slide_count,
                    ppt_has_images=ppt_has_images,
                    ppt_explanation_notes=ppt_notes,
                    communication_score=comm,
                    suggestion_implementation_score=sugg,
                    doubt_clearing_score=doubt,
                    strongest_areas=strongest,
                    areas_for_improvement=improvements,
                    interested_areas=interested,
                    general_remarks=general_rem,
                )
                created_count += 1

        messages.success(request, f"Successfully evaluated {created_count + updated_count} students in {batch.name} ({created_count} new, {updated_count} updated).")
        return redirect(f"/evaluations/?batch_id={batch.id}&date={eval_date.strftime('%Y-%m-%d')}")

    form = DailyEvaluationForm()
    return render(request, 'evaluator_app/evaluations/evaluation_form.html', {
        'form': form,
        'student': None,
        'batch': batch,
        'is_bulk': True,
        'date': eval_date
    })


# ==============================================================================
# STUDENT TASK MANAGEMENT & TRACKING
# ==============================================================================

@evaluator_required
def task_hub_sync_deadlines_view(request):
    from .models import Batch
    from .services import sync_student_tasks_for_batch
    for batch in Batch.objects.filter(status='ACTIVE'):
        sync_student_tasks_for_batch(batch)
    messages.success(request, "Task deadlines synchronized successfully across all active batches based on their schedules!")
    return redirect('task_hub')

@evaluator_required
def task_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    today = timezone.now().date()
    
    tasks_qs = StudentTask.objects.filter(batch__in=accessible_batches).select_related('student', 'batch', 'assigned_by')
    
    # Filter by Batch
    batch_id = request.GET.get('batch')
    if batch_id:
        tasks_qs = tasks_qs.filter(batch_id=batch_id)
        
    # Filter by Status
    status_filter = request.GET.get('status')
    if status_filter == 'PENDING':
        tasks_qs = tasks_qs.filter(status='PENDING')
    elif status_filter == 'COMPLETED':
        tasks_qs = tasks_qs.filter(status='COMPLETED')
    elif status_filter == 'LATE':
        tasks_qs = tasks_qs.filter(status='LATE')
    elif status_filter == 'OVERDUE':
        tasks_qs = tasks_qs.filter(status='PENDING', due_date__lt=today)
        
    # Filter by Search Query
    search_q = request.GET.get('q')
    if search_q:
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=search_q) |
            Q(student__name__icontains=search_q) |
            Q(student__roll_number__icontains=search_q) |
            Q(description__icontains=search_q)
        )
        
    unique_task_titles = tasks_qs.values_list('title', flat=True).distinct().order_by('title')
    unique_dates = tasks_qs.values_list('assigned_date', flat=True).distinct().order_by('-assigned_date')
    
    # Filter by Date
    date_filter = request.GET.get('date')
    if date_filter:
        tasks_qs = tasks_qs.filter(assigned_date=date_filter)

    # Filter by Task Title
    task_title_filter = request.GET.get('task_title')
    if task_title_filter:
        tasks_qs = tasks_qs.filter(title=task_title_filter)
        
    # Global Task Metrics for Filter Bar
    all_scoped_tasks = StudentTask.objects.filter(batch__in=accessible_batches)
    total_count = all_scoped_tasks.count()
    pending_count = all_scoped_tasks.filter(status='PENDING').count()
    completed_count = all_scoped_tasks.filter(status='COMPLETED').count()
    late_count = all_scoped_tasks.filter(status='LATE').count()
    overdue_count = all_scoped_tasks.filter(status='PENDING', due_date__lt=today).count()

    # Fetch accessible batch groups
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.is_admin:
        accessible_groups = BatchGroup.objects.all()
    else:
        accessible_groups = BatchGroup.objects.filter(
            batches__location__in=profile.assigned_locations.filter(is_active=True)
        ).distinct()

    quick_task_form = QuickTaskAssignForm(user=user)

    context = {
        'tasks': tasks_qs,
        'accessible_batches': accessible_batches,
        'accessible_groups': accessible_groups,
        'selected_batch': batch_id,
        'selected_status': status_filter or 'ALL',
        'search_query': search_q or '',
        'selected_date': date_filter or '',
        'selected_task_title': task_title_filter or '',
        'unique_task_titles': unique_task_titles,
        'unique_dates': unique_dates,
        'total_count': total_count,
        'pending_count': pending_count,
        'completed_count': completed_count,
        'late_count': late_count,
        'overdue_count': overdue_count,
        'quick_task_form': quick_task_form,
    }
    return render(request, 'evaluator_app/tasks/task_hub.html', context)


@evaluator_required
def task_create_view(request):
    user = request.user
    if request.method == 'POST':
        form = QuickTaskAssignForm(request.POST, request.FILES, user=user)
        if form.is_valid():
            target_type = form.cleaned_data.get('target_type', 'STUDENT')
            batch_ids = request.POST.getlist('batch_ids')
            student = form.cleaned_data.get('student')
            title = form.cleaned_data.get('title')
            desc = form.cleaned_data.get('description', '')
            incharge_name = form.cleaned_data.get('incharge_name', '')
            problem_document = request.FILES.get('problem_document')
            assigned_date = form.cleaned_data.get('assigned_date')
            due_date = form.cleaned_data.get('due_date')
            priority = form.cleaned_data.get('priority', 'NORMAL')
            evaluator_remarks = form.cleaned_data.get('evaluator_remarks', '')

            if not batch_ids:
                messages.error(request, "Please select at least one batch.")
                return redirect('task_hub')
            
            # Fetch all batches and verify access
            batches = Batch.objects.filter(id__in=batch_ids)
            for batch in batches:
                if not can_user_access_batch(user, batch):
                    messages.error(request, f"Permission denied for batch {batch.name}.")
                    return redirect('task_hub')
            
            # Override with syllabus module if provided
            module_id = request.POST.get('module_id')
            if module_id:
                syllabus_module = SyllabusTask.objects.filter(id=module_id).first()
                if syllabus_module:
                    title = syllabus_module.title
                    desc = syllabus_module.description
            
            if not title:
                messages.error(request, "Task title is required.")
                return redirect('task_hub')

            created_count = 0
            if target_type == 'BATCH':
                # Assign to all active students in all selected batches
                for batch in batches:
                    active_students = batch.students.filter(status='ACTIVE')
                    for stu in active_students:
                        task = StudentTask(
                            student=stu,
                            batch=batch,
                            assigned_by=user,
                            title=title,
                            description=desc,
                            incharge_name=incharge_name,
                            assigned_date=assigned_date,
                            due_date=due_date,
                            priority=priority,
                            evaluator_remarks=evaluator_remarks,
                            status='PENDING'
                        )
                        if problem_document:
                            task.problem_document = problem_document
                        task.save()
                        created_count += 1
                messages.success(request, f"Task '{title}' assigned to {created_count} active students across {len(batches)} batch(es)!")
            else:
                if len(batches) > 1:
                    messages.error(request, "Cannot assign to a specific student when multiple batches are selected. Select one batch or choose 'Entire Batch'.")
                    return redirect('task_hub')
                
                batch = batches.first()
                if not student:
                    messages.error(request, "Please select a student for assignment.")
                    return redirect('task_hub')
                
                task = StudentTask(
                    student=student,
                    batch=batch,
                    assigned_by=user,
                    title=title,
                    description=desc,
                    incharge_name=incharge_name,
                    assigned_date=assigned_date,
                    due_date=due_date,
                    priority=priority,
                    evaluator_remarks=evaluator_remarks,
                    status='PENDING'
                )
                if problem_document:
                    task.problem_document = problem_document
                task.save()
                messages.success(request, f"Task '{title}' assigned to {student.name} successfully!")

            next_url = request.POST.get('next') or 'task_hub'
            return redirect(next_url)
        else:
            print("FORM ERRORS:", form.errors)
            messages.error(request, "Error creating task. Please check the required fields.")

    return redirect('task_hub')


@evaluator_required
def task_update_status_view(request, task_id):
    user = request.user
    task = get_object_or_404(StudentTask, id=task_id)
    
    if not can_user_access_batch(user, task.batch):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('task_hub')
        
    if request.method == 'POST':
        new_status = request.POST.get('status', 'COMPLETED')
        completed_at_str = request.POST.get('completed_at')
        remarks = request.POST.get('evaluator_remarks', '')

        if new_status in ['COMPLETED', 'LATE']:
            if completed_at_str:
                try:
                    # Accepts 'YYYY-MM-DDTHH:MM' or 'YYYY-MM-DD HH:MM:SS'
                    clean_dt_str = completed_at_str.replace('T', ' ')
                    if len(clean_dt_str) == 16:
                        dt = datetime.strptime(clean_dt_str, '%Y-%m-%d %H:%M')
                    else:
                        dt = datetime.strptime(clean_dt_str, '%Y-%m-%d %H:%M:%S')
                    task.completed_at = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                except ValueError:
                    task.completed_at = timezone.now()
            else:
                task.completed_at = timezone.now()

            # Check if completed past due date
            if task.due_date and task.completed_at.date() > task.due_date:
                task.status = 'LATE'
            else:
                task.status = new_status
        else:
            task.status = new_status
            if new_status == 'PENDING':
                task.completed_at = None

        if remarks:
            task.evaluator_remarks = remarks
        task.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({
                'success': True,
                'message': f"Task '{task.title}' updated successfully!",
                'status': task.status,
                'status_display': task.get_status_display(),
                'completed_at_display': task.completed_at.strftime('%b %d, %Y - %I:%M %p') if task.completed_at else '—'
            })

        messages.success(request, f"Task '{task.title}' marked as {task.get_status_display()}!")
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'task_hub'
        return redirect(next_url)

    return redirect('task_hub')


@evaluator_required
def task_delete_view(request, task_id):
    user = request.user
    task = get_object_or_404(StudentTask, id=task_id)
    
    if not can_user_access_batch(user, task.batch):
        messages.error(request, "Permission denied.")
        return redirect('task_hub')

    task_title = task.title
    task.delete()
    messages.success(request, f"Task '{task_title}' was deleted.")
    next_url = request.META.get('HTTP_REFERER') or 'task_hub'
    return redirect(next_url)


@evaluator_required
@require_POST
def bulk_task_delete_view(request):
    user = request.user
    task_ids = request.POST.getlist('task_ids')
    
    if not task_ids:
        messages.error(request, "No tasks were selected for deletion.")
        return redirect('task_hub')
        
    accessible_batches = get_user_batches(user)
    
    # Filter tasks to ensure user can only delete tasks they have access to
    tasks_to_delete = StudentTask.objects.filter(id__in=task_ids, batch__in=accessible_batches)
    count = tasks_to_delete.count()
    
    if count == 0:
        messages.error(request, "No valid tasks found or permission denied.")
    else:
        tasks_to_delete.delete()
        messages.success(request, f"Successfully deleted {count} task(s).")
        
    next_url = request.META.get('HTTP_REFERER') or 'task_hub'
    return redirect(next_url)

@evaluator_required
def student_tasks_api(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    
    if not can_user_access_batch(user, student.batch):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    tasks_data = []
    for t in student.tasks.order_by('-assigned_date', '-created_at'):
        tasks_data.append({
            'id': t.id,
            'title': t.title,
            'description': t.description,
            'assigned_date': t.assigned_date.strftime('%Y-%m-%d'),
            'assigned_date_display': t.assigned_date.strftime('%b %d, %Y'),
            'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
            'due_date_display': t.due_date.strftime('%b %d, %Y') if t.due_date else '—',
            'completed_at': t.completed_at.strftime('%Y-%m-%dT%H:%M') if t.completed_at else '',
            'completed_at_display': t.completed_at.strftime('%b %d, %Y - %I:%M %p') if t.completed_at else 'Pending',
            'status': t.status,
            'computed_status': t.computed_status,
            'priority': t.priority,
            'evaluator_remarks': t.evaluator_remarks,
            'is_evaluated': t.is_evaluated,
            'score': t.score if t.score is not None else 0.0,
            'grade': t.grade,
            'evaluation_status': t.evaluation_status,
            'evaluation_status_display': t.get_evaluation_status_display() if t.is_evaluated else 'Pending Evaluation',
            'evaluator_feedback': t.evaluator_feedback,
        })

    return JsonResponse({'success': True, 'tasks': tasks_data})

@require_POST
@evaluator_required
def update_payment_status_api(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    
    if not can_user_access_batch(user, student.batch):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        
    is_admin = user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'ADMIN')
    
    # If currently paid, only admin can change it
    if student.payment_status == 'PAID' and not is_admin:
        return JsonResponse({'success': False, 'message': 'Only an admin can change the payment status once it is marked as Paid.'}, status=403)
        
    try:
        import json
        data = json.loads(request.body)
        new_status = data.get('payment_status')
        if new_status in ['PAID', 'UNPAID']:
            student.payment_status = new_status
            student.save(update_fields=['payment_status'])
            return JsonResponse({'success': True, 'message': 'Payment status updated successfully.'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid payment status.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ==============================================================================
# STUDENT TASK EVALUATION SECTION
# ==============================================================================

@evaluator_required
def task_evaluation_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    today = timezone.now().date()

    # Base queryset scoped to user's accessible batches
    base_tasks_qs = StudentTask.objects.filter(batch__in=accessible_batches).select_related('student', 'batch', 'assigned_by', 'evaluated_by')

    tasks_qs = base_tasks_qs

    # Filter by Batch (Batch-wise search/filter)
    batch_id = request.GET.get('batch')
    if batch_id:
        tasks_qs = tasks_qs.filter(batch_id=batch_id)

    # Filter by Student (Direct student ID filter)
    student_id = request.GET.get('student')
    if student_id:
        tasks_qs = tasks_qs.filter(student_id=student_id)

    # Search Query (Student name, Roll number, Task Title, Description, Feedback)
    search_q = request.GET.get('q', '').strip()
    if search_q:
        tasks_qs = tasks_qs.filter(
            Q(student__name__icontains=search_q) |
            Q(student__roll_number__icontains=search_q) |
            Q(title__icontains=search_q) |
            Q(description__icontains=search_q) |
            Q(evaluator_feedback__icontains=search_q) |
            Q(evaluator_remarks__icontains=search_q)
        )

    # Spotlight: Latest assigned tasks (most recently assigned tasks matching current batch & search)
    latest_assigned_tasks = tasks_qs.order_by('-assigned_date', '-created_at')[:6]

    # Filter by Evaluation Status
    eval_status_filter = request.GET.get('eval_status', 'ALL')
    if eval_status_filter == 'UNEVALUATED':
        tasks_qs = tasks_qs.filter(is_evaluated=False)
    elif eval_status_filter == 'EVALUATED':
        tasks_qs = tasks_qs.filter(is_evaluated=True)
    elif eval_status_filter == 'EXCELLENT':
        tasks_qs = tasks_qs.filter(evaluation_status='EXCELLENT')
    elif eval_status_filter == 'PASSED':
        tasks_qs = tasks_qs.filter(evaluation_status='PASSED')
    elif eval_status_filter == 'NEEDS_REVISION':
        tasks_qs = tasks_qs.filter(evaluation_status='NEEDS_REVISION')
    elif eval_status_filter == 'FAILED':
        tasks_qs = tasks_qs.filter(evaluation_status='FAILED')

    # Filter by Completion Status
    completion_filter = request.GET.get('status')
    if completion_filter == 'PENDING':
        tasks_qs = tasks_qs.filter(status='PENDING')
    elif completion_filter == 'COMPLETED':
        tasks_qs = tasks_qs.filter(status='COMPLETED')
    elif completion_filter == 'LATE':
        tasks_qs = tasks_qs.filter(status='LATE')
    elif completion_filter == 'OVERDUE':
        tasks_qs = tasks_qs.filter(status='PENDING', due_date__lt=today)

    # Date preset filter
    date_filter = request.GET.get('date_filter', 'ALL')
    if date_filter == 'TODAY':
        tasks_qs = tasks_qs.filter(assigned_date=today)
    elif date_filter == 'WEEK':
        week_ago = today - timedelta(days=7)
        tasks_qs = tasks_qs.filter(assigned_date__gte=week_ago)
    elif date_filter == 'MONTH':
        month_ago = today - timedelta(days=30)
        tasks_qs = tasks_qs.filter(assigned_date__gte=month_ago)

    # Sorting
    sort_by = request.GET.get('sort', 'latest_assigned')
    if sort_by == 'latest_assigned':
        tasks_qs = tasks_qs.order_by('-assigned_date', '-created_at')
    elif sort_by == 'oldest_assigned':
        tasks_qs = tasks_qs.order_by('assigned_date', 'created_at')
    elif sort_by == 'highest_score':
        tasks_qs = tasks_qs.order_by('-score', '-assigned_date')
    elif sort_by == 'lowest_score':
        tasks_qs = tasks_qs.order_by('score', '-assigned_date')
    elif sort_by == 'due_soon':
        tasks_qs = tasks_qs.order_by('due_date', '-assigned_date')
    else:
        tasks_qs = tasks_qs.order_by('-assigned_date', '-created_at')

    # Compute key evaluation metrics
    all_scoped = base_tasks_qs
    total_count = all_scoped.count()
    evaluated_count = all_scoped.filter(is_evaluated=True).count()
    pending_eval_count = all_scoped.filter(is_evaluated=False).count()
    needs_revision_count = all_scoped.filter(evaluation_status='NEEDS_REVISION').count()
    avg_score_res = all_scoped.filter(is_evaluated=True).aggregate(Avg('score'))['score__avg']
    avg_score = round(avg_score_res, 1) if avg_score_res is not None else 0.0
    eval_rate = round((evaluated_count / total_count * 100), 1) if total_count > 0 else 0.0

    eval_form = TaskEvaluationForm()

    context = {
        'tasks': tasks_qs,
        'latest_assigned_tasks': latest_assigned_tasks,
        'accessible_batches': accessible_batches,
        'selected_batch': batch_id or '',
        'selected_student': student_id or '',
        'search_query': search_q,
        'eval_status_filter': eval_status_filter,
        'completion_filter': completion_filter or 'ALL',
        'date_filter': date_filter,
        'sort_by': sort_by,
        'total_count': total_count,
        'evaluated_count': evaluated_count,
        'pending_eval_count': pending_eval_count,
        'needs_revision_count': needs_revision_count,
        'avg_score': avg_score,
        'eval_rate': eval_rate,
        'eval_form': eval_form,
    }
    return render(request, 'evaluator_app/tasks/task_evaluation_hub.html', context)


@evaluator_required
def task_evaluate_view(request, task_id):
    user = request.user
    task = get_object_or_404(StudentTask.objects.select_related('student', 'batch', 'assigned_by', 'evaluated_by'), id=task_id)

    if not can_user_access_batch(user, task.batch):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied for this task's batch.")
        return redirect('task_evaluation_hub')

    if request.method == 'POST':
        form = TaskEvaluationForm(request.POST, request.FILES, instance=task)
        if form.is_valid():
            evaluated_task = form.save(commit=False)

            # Check if rubric scores provided or score entered
            code_q = form.cleaned_data.get('code_quality_score') or 0
            prob_s = form.cleaned_data.get('problem_solving_score') or 0
            time_s = form.cleaned_data.get('timeliness_score') or 0
            pres_s = form.cleaned_data.get('presentation_score') or 0

            if code_q or prob_s or time_s or pres_s:
                evaluated_task.calculate_total_score()
            elif evaluated_task.score:
                s_val = float(evaluated_task.score)
                if s_val >= 90: evaluated_task.grade = 'A+'
                elif s_val >= 80: evaluated_task.grade = 'A'
                elif s_val >= 70: evaluated_task.grade = 'B+'
                elif s_val >= 60: evaluated_task.grade = 'B'
                elif s_val >= 50: evaluated_task.grade = 'C'
                else: evaluated_task.grade = 'NI'
            else:
                evaluated_task.score = 0.0
                evaluated_task.grade = 'NI'

            # Auto-set evaluation status if still UNEVALUATED
            if evaluated_task.evaluation_status == 'UNEVALUATED':
                if (evaluated_task.score or 0) >= 80:
                    evaluated_task.evaluation_status = 'EXCELLENT'
                elif (evaluated_task.score or 0) >= 50:
                    evaluated_task.evaluation_status = 'PASSED'
                else:
                    evaluated_task.evaluation_status = 'NEEDS_REVISION'

            # Update completion status if requested
            task_status_post = request.POST.get('status')
            if task_status_post in ['COMPLETED', 'LATE', 'PENDING']:
                evaluated_task.status = task_status_post
                if task_status_post in ['COMPLETED', 'LATE'] and not evaluated_task.completed_at:
                    evaluated_task.completed_at = timezone.now()

            evaluated_task.is_evaluated = True
            evaluated_task.evaluated_by = user
            evaluated_task.evaluated_at = timezone.now()
            evaluated_task.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'success': True,
                    'message': f"Evaluation for task '{task.title}' saved successfully!",
                    'task_id': evaluated_task.id,
                    'score': evaluated_task.score,
                    'grade': evaluated_task.grade,
                    'evaluation_status': evaluated_task.evaluation_status,
                    'evaluation_status_display': evaluated_task.get_evaluation_status_display(),
                    'status': evaluated_task.status,
                    'status_display': evaluated_task.get_status_display(),
                    'is_evaluated': evaluated_task.is_evaluated,
                    'evaluated_by': user.get_full_name() or user.username,
                    'evaluated_at_display': evaluated_task.evaluated_at.strftime('%b %d, %Y - %I:%M %p')
                })

            messages.success(request, f"Task evaluation saved for {task.student.name}: {evaluated_task.score}% (Grade {evaluated_task.grade})")
            next_url = request.POST.get('next') or 'task_evaluation_hub'
            return redirect(next_url)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, "Error saving evaluation. Please check your inputs.")

    # GET Request: Return JSON for modal dialog
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'success': True,
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'student_id': task.student.id,
            'student_name': task.student.name,
            'student_roll': task.student.roll_number,
            'student_initials': task.student.initials,
            'student_avatar_color': task.student.avatar_color,
            'batch_id': task.batch.id,
            'batch_name': task.batch.name,
            'batch_code': task.batch.code,
            'assigned_date': task.assigned_date.strftime('%Y-%m-%d'),
            'assigned_date_display': task.assigned_date.strftime('%b %d, %Y'),
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            'due_date_display': task.due_date.strftime('%b %d, %Y') if task.due_date else '—',
            'completed_at': task.completed_at.strftime('%Y-%m-%dT%H:%M') if task.completed_at else '',
            'completed_at_display': task.completed_at.strftime('%b %d, %Y - %I:%M %p') if task.completed_at else 'Not completed yet',
            'status': task.status,
            'status_display': task.get_status_display(),
            'priority': task.priority,
            'priority_display': task.get_priority_display(),
            'evaluator_remarks': task.evaluator_remarks,
            # Evaluation specifics
            'is_evaluated': task.is_evaluated,
            'score': task.score if task.score is not None else 0.0,
            'grade': task.grade or 'B+',
            'code_quality_score': task.code_quality_score or 80.0,
            'problem_solving_score': task.problem_solving_score or 80.0,
            'timeliness_score': task.timeliness_score or 80.0,
            'presentation_score': task.presentation_score or 75.0,
            'evaluation_status': task.evaluation_status if task.is_evaluated else 'PASSED',
            'evaluation_status_display': task.get_evaluation_status_display() if task.is_evaluated else 'Accepted / Passed',
            'evaluator_feedback': task.evaluator_feedback or '',
            'strengths': task.strengths or '',
            'areas_for_improvement': task.areas_for_improvement or '',
            'submission_url': task.submission_url or '',
            'evaluated_by_name': (task.evaluated_by.get_full_name() or task.evaluated_by.username) if task.evaluated_by else '',
            'evaluated_at_display': task.evaluated_at.strftime('%b %d, %Y - %I:%M %p') if task.evaluated_at else '',
        })

    form = TaskEvaluationForm(instance=task)
    return render(request, 'evaluator_app/tasks/task_evaluate_page.html', {
        'form': form,
        'task': task
    })




@evaluator_required
def evaluation_history_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    evaluations = DailyEvaluation.objects.filter(batch__in=accessible_batches).select_related('student', 'batch', 'evaluator')

    # Filters
    batch_id = request.GET.get('batch')
    if batch_id:
        evaluations = evaluations.filter(batch_id=batch_id)
        
    date_filter = request.GET.get('date')
    if date_filter:
        evaluations = evaluations.filter(date=date_filter)
        
    grade_filter = request.GET.get('grade')
    if grade_filter:
        evaluations = evaluations.filter(grade=grade_filter)
        
    search_q = request.GET.get('q')
    if search_q:
        evaluations = evaluations.filter(
            Q(student__name__icontains=search_q) | Q(student__roll_number__icontains=search_q) | Q(topic__icontains=search_q)
        )

    context = {
        'evaluations': evaluations[:100],
        'accessible_batches': accessible_batches,
        'selected_batch': batch_id,
        'selected_date': date_filter,
        'selected_grade': grade_filter,
        'search_query': search_q or '',
    }
    return render(request, 'evaluator_app/evaluations/evaluation_history.html', context)


# ==============================================================================
# ATTENDANCE & SCHEDULE HUB
# ==============================================================================

@evaluator_required
def batch_reschedule_class_view(request):
    if request.method == 'POST':
        batch_id = request.POST.get('batch_id')
        original_date_str = request.POST.get('original_date')
        rescheduled_date_str = request.POST.get('rescheduled_date')
        reason = request.POST.get('reason', '')
        
        try:
            batch = Batch.objects.get(id=batch_id)
            orig_date = datetime.strptime(original_date_str, '%Y-%m-%d').date()
            resched_date = datetime.strptime(rescheduled_date_str, '%Y-%m-%d').date() if rescheduled_date_str else None
            
            # Check if exception already exists for this original date
            exc, created = BatchScheduleException.objects.get_or_create(
                batch=batch, 
                original_date=orig_date,
                defaults={
                    'rescheduled_date': resched_date,
                    'reason': reason,
                    'created_by': request.user
                }
            )
            
            if not created:
                exc.rescheduled_date = resched_date
                exc.reason = reason
                exc.created_by = request.user
                exc.save()
                
            messages.success(request, f"Class on {orig_date} successfully rescheduled.")
        except Exception as e:
            messages.error(request, f"Failed to reschedule class: {str(e)}")
            
        # Redirect back to attendance hub at the original date so they can see the banner
        return redirect(f"/attendance/?batch_id={batch_id}&date={original_date_str}")
    return redirect('attendance_hub')

@evaluator_required
def attendance_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    
    # Auto-mark missing attendance for past days
    from .services import auto_mark_absent_for_past_days
    auto_mark_absent_for_past_days(accessible_batches)
    
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'ADMIN')
    
    batch_id = request.GET.get('batch_id')
    group_id = request.GET.get('group_id')
    selection = request.GET.get('selection')
    
    if selection and not batch_id and not group_id:
        if selection.startswith('b_'):
            batch_id = selection[2:]
        elif selection.startswith('g_'):
            group_id = selection[2:]
            
    date_str = request.GET.get('date')
    
    today = timezone.now().date()
    selected_date = today
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today

    # Fetch accessible batch groups
    if is_admin:
        accessible_groups = BatchGroup.objects.all()
    else:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        accessible_groups = BatchGroup.objects.filter(
            batches__location__in=profile.assigned_locations.filter(is_active=True)
        ).distinct()
            
    selected_batch = None
    selected_group = None
    
    if group_id:
        selected_group = accessible_groups.filter(id=group_id).first()
    elif batch_id:
        selected_batch = accessible_batches.filter(id=batch_id).first()
    elif accessible_batches.exists():
        day_name = selected_date.strftime('%A')
        batches_for_day = [b for b in accessible_batches if day_name in b.class_days]
        if batches_for_day:
            selected_batch = batches_for_day[0]
        else:
            selected_batch = accessible_batches.first()

    # Check if attendance is already recorded for this batch & date
    is_already_marked = False
    is_class_day = True
    selected_date_day_name = selected_date.strftime('%A')
    reschedule_exception = None
    makeup_exception = None
    
    if selected_group:
        # For a merged group, we check if attendance is marked for ANY batch in the group.
        # Ideally, it's marked for all.
        is_already_marked = Attendance.objects.filter(batch__in=selected_group.batches.all(), date=selected_date).exists()
        
        # Check if today is a scheduled class day for the group (if any batch has it)
        is_class_day = False
        for b in selected_group.batches.all():
            if b.days_list and selected_date_day_name in b.days_list:
                is_class_day = True
                break
                
        # For simplicity, exceptions aren't fully aggregated for groups, we just rely on is_class_day
    elif selected_batch:
        is_already_marked = Attendance.objects.filter(batch=selected_batch, date=selected_date).exists()
        
        # Check if today is a scheduled class day
        if selected_batch.days_list:
            is_class_day = selected_date_day_name in selected_batch.days_list
            
        # Check if this regular class day was cancelled/rescheduled
        reschedule_exception = BatchScheduleException.objects.filter(batch=selected_batch, original_date=selected_date).first()
        if reschedule_exception:
            is_class_day = False
            
        # Check if today is a makeup class for another cancelled day
        makeup_exception = BatchScheduleException.objects.filter(batch=selected_batch, rescheduled_date=selected_date).first()
        if makeup_exception:
            is_class_day = True

    can_edit_attendance = (is_admin or not is_already_marked) and is_class_day

    if request.method == 'POST' and (selected_batch or selected_group):
        # Enforce lock: Non-admins cannot overwrite or change saved attendance
        if not can_edit_attendance:
            messages.error(
                request,
                "🔒 Attendance for this date has already been marked and saved. Once saved, it cannot be changed. Only administrators have permission to modify finalized attendance."
            )
            redirect_url = f"/attendance/?date={selected_date.strftime('%Y-%m-%d')}"
            if selected_group:
                redirect_url += f"&group_id={selected_group.id}"
            else:
                redirect_url += f"&batch_id={selected_batch.id}"
            return redirect(redirect_url)

        # Save attendance submission
        for key, value in request.POST.items():
            if key.startswith('status_'):
                student_id = key.replace('status_', '')
                if selected_group:
                    student = get_object_or_404(Student, id=student_id, batch__in=selected_group.batches.all())
                else:
                    student = get_object_or_404(Student, id=student_id, batch=selected_batch)
                remarks = request.POST.get(f'remarks_{student_id}', '')
                
                Attendance.objects.update_or_create(
                    student=student,
                    date=selected_date,
                    defaults={
                        'batch': student.batch,
                        'status': value,
                        'remarks': remarks,
                        'marked_by': user
                    }
                )
        
        target_name = selected_group.name if selected_group else selected_batch.name
        if is_already_marked and is_admin:
            messages.success(request, f"✏️ Admin Update: Attendance for {target_name} on {selected_date.strftime('%d %b %Y')} was updated successfully.")
        else:
            messages.success(request, f"Attendance for {target_name} on {selected_date.strftime('%d %b %Y')} saved successfully!")
            
        redirect_url = f"/attendance/?date={selected_date.strftime('%Y-%m-%d')}"
        if selected_group:
            redirect_url += f"&group_id={selected_group.id}"
        else:
            redirect_url += f"&batch_id={selected_batch.id}"
        return redirect(redirect_url)

    students_data = []
    if selected_group:
        students = Student.objects.filter(batch__in=selected_group.batches.all()).select_related('batch')
        att_dict = {
            att.student_id: att for att in Attendance.objects.filter(batch__in=selected_group.batches.all(), date=selected_date)
        }
        for stu in students:
            rec = att_dict.get(stu.id)
            stu_pct = stu.attendance_percentage
            has_records = stu.attendance_records.exists()
            is_low_att = has_records and stu_pct < 50.0
            students_data.append({
                'student': stu,
                'status': rec.status if rec else 'PRESENT',
                'remarks': rec.remarks if rec else '',
                'is_marked': rec is not None,
                'cum_attendance_pct': stu_pct,
                'is_low_attendance': is_low_att,
            })
    elif selected_batch:
        students = selected_batch.students.all()
        att_dict = {
            att.student_id: att for att in Attendance.objects.filter(batch=selected_batch, date=selected_date)
        }
        for stu in students:
            rec = att_dict.get(stu.id)
            stu_pct = stu.attendance_percentage
            has_records = stu.attendance_records.exists()
            is_low_att = has_records and stu_pct < 50.0
            students_data.append({
                'student': stu,
                'status': rec.status if rec else 'PRESENT',
                'remarks': rec.remarks if rec else '',
                'is_marked': rec is not None,
                'cum_attendance_pct': stu_pct,
                'is_low_attendance': is_low_att,
            })

    present_count = sum(1 for s in students_data if s['status'] == 'PRESENT')
    late_count = sum(1 for s in students_data if s['status'] == 'LATE')
    absent_count = sum(1 for s in students_data if s['status'] == 'ABSENT')
    excused_count = sum(1 for s in students_data if s['status'] == 'EXCUSED')
    total_count = len(students_data)
    present_rate = round(((present_count + late_count) / total_count * 100), 1) if total_count > 0 else 0

    # Low Attendance Students (< 50%) across all accessible batches
    low_attendance_students = []
    all_scoped_students = Student.objects.filter(batch__in=accessible_batches).select_related('batch', 'batch__location')
    for stu in all_scoped_students:
        total_att = stu.attendance_records.count()
        if total_att > 0:
            pct = stu.attendance_percentage
            if pct < 50.0:
                present_num = stu.attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
                absent_num = stu.attendance_records.filter(status='ABSENT').count()
                low_attendance_students.append({
                    'student': stu,
                    'attendance_pct': pct,
                    'total_sessions': total_att,
                    'present_count': present_num,
                    'absent_count': absent_num,
                    'batch': stu.batch,
                })
    low_attendance_students.sort(key=lambda x: x['attendance_pct'])
    
    # Calculate min_date for the date picker based on batch/group start_date
    min_date = None
    if selected_group:
        group_start_dates = [b.start_date for b in selected_group.batches.all() if b.start_date]
        if group_start_dates:
            min_date = min(group_start_dates)
    elif selected_batch and selected_batch.start_date:
        min_date = selected_batch.start_date

    context = {
        'min_date': min_date.strftime('%Y-%m-%d') if min_date else None,
        'accessible_batches': accessible_batches,
        'accessible_groups': accessible_groups,
        'selected_batch': selected_batch,
        'selected_group': selected_group,
        'selected_date': selected_date.strftime('%Y-%m-%d'),
        'selected_date_display': selected_date.strftime('%B %d, %Y'),
        'students_data': students_data,
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'excused_count': excused_count,
        'total_count': total_count,
        'present_rate': present_rate,
        'is_already_marked': is_already_marked,
        'is_class_day': is_class_day,
        'selected_date_day_name': selected_date_day_name,
        'reschedule_exception': reschedule_exception,
        'makeup_exception': makeup_exception,
        'can_edit_attendance': can_edit_attendance,
        'is_admin': is_admin,
        'low_attendance_students': low_attendance_students,
        'low_attendance_count': len(low_attendance_students),
    }
    return render(request, 'evaluator_app/attendance/attendance_hub.html', context)


@evaluator_required
def attendance_register_view(request, batch_id=None, group_id=None):
    user = request.user
    
    batch = None
    group = None
    students = None
    batch_days = []
    exceptions = []
    
    if group_id:
        group = get_object_or_404(BatchGroup, id=group_id)
        batches = group.batches.all()
        # Ensure user can access at least one batch in the group
        has_access = any(can_user_access_batch(user, b) for b in batches)
        if not has_access and not user.is_superuser:
            messages.error(request, "Access denied.")
            return redirect('batch_list')
        students = Student.objects.filter(batch__in=batches)
        
        # Combine days and exceptions
        for b in batches:
            if b.days_list:
                batch_days.extend(b.days_list)
            exceptions.extend(list(BatchScheduleException.objects.filter(batch=b)))
        batch_days = list(set(batch_days))
    else:
        batch = get_object_or_404(Batch, id=batch_id)
        if not can_user_access_batch(user, batch):
            messages.error(request, "Access denied.")
            return redirect('batch_list')
        students = batch.students.all()
        batch_days = batch.days_list
        exceptions = list(BatchScheduleException.objects.filter(batch=batch))
        
    today = timezone.now().date()
    
    earliest_start = min([b.start_date for b in group.batches.all()]) if group else batch.start_date
    if hasattr(earliest_start, 'date'):
        earliest_start = earliest_start.date()
        
    dates = []
    current_date = earliest_start
    
    # Pre-fetch exceptions for performance
    cancelled_dates = set(e.original_date for e in exceptions)
    makeup_dates = set(e.rescheduled_date for e in exceptions if e.rescheduled_date)
    
    # Generate all active class days from start date to today
    while current_date <= today:
        is_regular = (not batch_days or current_date.strftime('%A') in batch_days)
        is_cancelled = current_date in cancelled_dates
        is_makeup = current_date in makeup_dates
        
        if (is_regular and not is_cancelled) or is_makeup:
            dates.append(current_date)
            
        current_date += timedelta(days=1)
    # Pre-fetch attendance records for these dates
    if group:
        attendance_records = Attendance.objects.filter(batch__in=group.batches.all(), date__in=dates)
    else:
        attendance_records = Attendance.objects.filter(batch=batch, date__in=dates)
        
    att_map = {(a.student_id, a.date): a.status for a in attendance_records}
    
    matrix = []
    for stu in students:
        row_statuses = []
        present_in_period = 0
        for d in dates:
            stat = att_map.get((stu.id, d), 'NOT_MARKED')
            row_statuses.append({'date': d, 'status': stat})
            if stat in ['PRESENT', 'LATE']:
                present_in_period += 1
                
        pct = round((present_in_period / len(dates)) * 100, 1) if dates else 0
        matrix.append({
            'student': stu,
            'statuses': row_statuses,
            'present_count': present_in_period,
            'period_percentage': pct
        })

    context = {
        'batch': batch,
        'group': group,
        'dates': dates,
        'matrix': matrix,
        'makeup_dates': makeup_dates,
    }
    return render(request, 'evaluator_app/attendance/attendance_register.html', context)


# ==============================================================================
# EXPORT REPORTS
# ==============================================================================

@evaluator_required
def export_batch_csv_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        return HttpResponseForbidden("Access denied")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.code}_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Roll Number', 'Student Name', 'Email', 'Phone', 'Attendance %',
        'Average Score', 'Grade', 'Total Evals',
        'Strongest Areas', 'Areas For Improvement', 'Interested Areas', 'Latest Feedback'
    ])

    for stu in batch.students.all():
        latest = stu.latest_evaluation
        writer.writerow([
            stu.roll_number,
            stu.name,
            stu.email,
            stu.phone,
            f"{stu.attendance_percentage}%",
            f"{stu.average_score}%",
            latest.grade if latest else 'N/A',
            stu.total_evaluations_count,
            latest.strongest_areas if latest else '',
            latest.areas_for_improvement if latest else '',
            latest.interested_areas if latest else '',
            latest.general_remarks if latest else ''
        ])

    return response


@evaluator_required
def export_student_attendance_csv_view(request, student_id):
    user = request.user
    student = get_object_or_404(Student, id=student_id)
    if not can_user_access_batch(user, student.batch):
        return HttpResponseForbidden("Access denied")

    import openpyxl
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Student Attendance"
    ws.append([
        'Batch Name', 'Start Date', 'Roll Number', 'Student Name', 
        'Date', 'Day', 'Status', 'Remarks'
    ])

    batch_name = student.batch.name
    start_date = student.batch.start_date.strftime('%d-%b-%Y') if student.batch.start_date else 'N/A'
    roll_no = student.roll_number
    stu_name = student.name

    attendance_records = student.attendance_records.all().order_by('date')
    for record in attendance_records:
        ws.append([
            batch_name,
            start_date,
            roll_no,
            stu_name,
            record.date.strftime('%d %b %Y'),
            record.date.strftime('%A'),
            record.get_status_display(),
            record.remarks or ''
        ])

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = 16

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{student.roll_number}_attendance.xlsx"'
    wb.save(response)

    return response


@evaluator_required
def export_batch_attendance_csv_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        return HttpResponseForbidden("Access denied")

    month_str = request.GET.get('month')
    year_str = request.GET.get('year')
    
    if not year_str:
        year_str = str(timezone.now().year)
        
    year = int(year_str)
    
    attendance_qs = Attendance.objects.filter(batch=batch, date__year=year)
    
    if month_str:
        month = int(month_str)
        attendance_qs = attendance_qs.filter(date__month=month)
        filename = f"{batch.code}_attendance_{year}_{month:02d}.xlsx"
    else:
        filename = f"{batch.code}_attendance_{year}.xlsx"
        
    # Get unique dates in this period
    dates = list(attendance_qs.values_list('date', flat=True).distinct().order_by('date'))
    
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Batch Attendance"
    
    # Header row
    header = ['Batch Name', 'Start Date', 'Roll Number', 'Student Name'] + [d.strftime('%d-%b-%Y') for d in dates]
    ws.append(header)

    students = batch.students.all().order_by('roll_number')
    
    # Pre-fetch attendance mapped by student and date
    att_map = {(a.student_id, a.date): a.get_status_display() for a in attendance_qs}

    for stu in students:
        row = [
            batch.name, 
            batch.start_date.strftime('%d-%b-%Y') if batch.start_date else 'N/A',
            stu.roll_number, 
            stu.name
        ]
        for d in dates:
            row.append(att_map.get((stu.id, d), '-'))
        ws.append(row)

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = 16

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)

    return response


@evaluator_required
def download_student_template_view(request, batch_id, file_format):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        return HttpResponseForbidden("Access denied")

    start_date_str = batch.start_date.strftime('%Y-%m-%d') if batch.start_date else timezone.now().date().strftime('%Y-%m-%d')
    headers = ['Roll Number', 'Full Name', 'Email', 'Phone', 'Enrollment Date', 'Status', 'Notes']
    sample_rows = [
        ['STU-001', 'Rahul Sharma', 'rahul@example.com', '+91 9876543210', start_date_str, 'ACTIVE', 'Python & Web Development'],
        ['STU-002', 'Ananya Nair', 'ananya@example.com', '+91 9876543211', start_date_str, 'ACTIVE', 'Full Stack Candidate'],
    ]

    if file_format.lower() == 'xlsx':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Students Template"

        # Instruction row
        ws.merge_cells('A1:G1')
        ws['A1'] = f"Note: Enrollment Date cannot be earlier than Batch Start Date ({start_date_str}). Required columns: Roll Number, Full Name."
        ws['A1'].font = Font(name='Segoe UI', size=10, italic=True, color='555555')
        ws['A1'].alignment = Alignment(horizontal='left', vertical='center')

        # Header row on row 2
        header_fill = PatternFill(start_color='1E1B4B', end_color='1E1B4B', fill_type='solid')
        header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
        thin_border = Border(
            left=Side(style='thin', color='D1D5DB'),
            right=Side(style='thin', color='D1D5DB'),
            top=Side(style='thin', color='D1D5DB'),
            bottom=Side(style='thin', color='D1D5DB')
        )

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='left', vertical='center')
            cell.border = thin_border

        # Sample rows on row 3 and 4
        for r_idx, row_data in enumerate(sample_rows, 3):
            for c_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = Font(name='Segoe UI', size=10)
                cell.alignment = Alignment(horizontal='left', vertical='center')
                cell.border = thin_border

        # Auto-size columns
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row > 1 and cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="students_template_{batch.code}.xlsx"'
        return response

    else:
        # CSV download
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="students_template_{batch.code}.csv"'
        writer = csv.writer(response)
        writer.writerow(headers)
        for row in sample_rows:
            writer.writerow(row)
        return response


@evaluator_required
def batch_student_import_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, "Access denied to this batch.")
        return redirect('batch_list')

    AVATAR_COLORS = ['#4F46E5', '#06B6D4', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#3B82F6', '#14B8A6']
    import_results = None

    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        duplicate_action = request.POST.get('duplicate_action', 'skip')  # 'skip' or 'update'

        if not uploaded_file:
            messages.error(request, "Please select an Excel (.xlsx) or CSV (.csv) file to upload.")
            return render(request, 'evaluator_app/batches/student_import.html', {'batch': batch})

        filename = uploaded_file.name.lower()
        if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
            messages.error(request, "Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")
            return render(request, 'evaluator_app/batches/student_import.html', {'batch': batch})

        raw_rows = []
        try:
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                import openpyxl
                wb = openpyxl.load_workbook(uploaded_file, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    if any(c is not None and str(c).strip() != '' for c in row):
                        raw_rows.append(list(row))
            else:
                content = uploaded_file.read()
                text = None
                for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                    try:
                        text = content.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    text = content.decode('utf-8', errors='replace')

                reader = csv.reader(io.StringIO(text))
                for row in reader:
                    if any(str(c).strip() != '' for c in row):
                        raw_rows.append(row)
        except Exception as e:
            messages.error(request, f"Failed to read uploaded file: {str(e)}")
            return render(request, 'evaluator_app/batches/student_import.html', {'batch': batch})

        if not raw_rows:
            messages.error(request, "The uploaded file contains no data rows.")
            return render(request, 'evaluator_app/batches/student_import.html', {'batch': batch})

        def norm(s):
            return re.sub(r'[^a-z0-9]', '', str(s).strip().lower()) if s is not None else ''

        header_idx = -1
        col_map = {}
        for idx, row in enumerate(raw_rows[:5]):
            normalized_row = [norm(c) for c in row]
            has_roll = any(c in ['rollnumber', 'rollno', 'roll', 'studentid', 'id', 'studentrollnumber'] for c in normalized_row)
            has_name = any(c in ['name', 'fullname', 'studentname', 'student'] for c in normalized_row)
            if has_roll or has_name:
                header_idx = idx
                for c_i, c_val in enumerate(normalized_row):
                    if c_val in ['rollnumber', 'rollno', 'roll', 'studentid', 'id', 'studentrollnumber']:
                        col_map['roll_number'] = c_i
                    elif c_val in ['name', 'fullname', 'studentname', 'student']:
                        col_map['name'] = c_i
                    elif c_val in ['email', 'emailaddress', 'mail']:
                        col_map['email'] = c_i
                    elif c_val in ['phone', 'phonenumber', 'mobile', 'contact', 'whatsapp']:
                        col_map['phone'] = c_i
                    elif c_val in ['enrollmentdate', 'joindate', 'admissiondate', 'joiningdate', 'date']:
                        col_map['join_date'] = c_i
                    elif c_val in ['status']:
                        col_map['status'] = c_i
                    elif c_val in ['notes', 'remarks', 'comment', 'comments', 'background']:
                        col_map['notes'] = c_i
                break

        data_rows = raw_rows[header_idx + 1:] if header_idx != -1 else raw_rows
        if 'roll_number' not in col_map:
            col_map['roll_number'] = 0
        if 'name' not in col_map:
            col_map['name'] = 1
        if 'email' not in col_map and len(raw_rows[0]) > 2:
            col_map['email'] = 2
        if 'phone' not in col_map and len(raw_rows[0]) > 3:
            col_map['phone'] = 3
        if 'join_date' not in col_map and len(raw_rows[0]) > 4:
            col_map['join_date'] = 4

        success_students = []
        updated_students = []
        skipped_rows = []
        error_rows = []

        batch_start_d = batch.start_date.date() if hasattr(batch.start_date, 'hour') else batch.start_date

        for row_num, row in enumerate(data_rows, start=(header_idx + 2 if header_idx != -1 else 1)):
            def get_val(key):
                idx = col_map.get(key)
                if idx is not None and idx < len(row):
                    val = row[idx]
                    return str(val).strip() if val is not None else ''
                return ''

            roll_number = get_val('roll_number')
            if not roll_number:
                roll_number = generate_batch_student_roll_number(batch)

            name = get_val('name')
            email = get_val('email')
            phone = get_val('phone')
            status_val = get_val('status').upper() or 'ACTIVE'
            if status_val not in ['ACTIVE', 'INACTIVE', 'COMPLETED', 'DROPPED']:
                status_val = 'ACTIVE'
            notes = get_val('notes')

            if not name:
                error_rows.append({
                    'row': row_num,
                    'roll_number': roll_number or '—',
                    'name': name or '—',
                    'reason': "Missing required field (Student Full Name is blank)."
                })
                continue

            # Parse join_date
            join_date = None
            date_raw = None
            if 'join_date' in col_map and col_map['join_date'] < len(row):
                date_raw = row[col_map['join_date']]

            if date_raw is not None and str(date_raw).strip() != '':
                if hasattr(date_raw, 'hour'):
                    join_date = date_raw.date()
                elif isinstance(date_raw, date):
                    join_date = date_raw
                else:
                    date_str = str(date_raw).strip()
                    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%d %b, %Y', '%d %b %Y']:
                        try:
                            join_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            pass
                    if not join_date:
                        join_date = batch_start_d
            else:
                join_date = batch_start_d

            # Enforce batch start date constraint (auto-correct if earlier)
            if batch_start_d and join_date < batch_start_d:
                join_date = batch_start_d

            # Check existing roll number
            existing_student = Student.objects.filter(roll_number__iexact=roll_number).first()
            if existing_student:
                if existing_student.batch_id == batch.id:
                    if duplicate_action == 'update':
                        existing_student.name = name
                        if email: existing_student.email = email
                        if phone: existing_student.phone = phone
                        existing_student.join_date = join_date
                        existing_student.status = status_val
                        if notes: existing_student.notes = notes
                        updated_students.append(existing_student)
                    else:
                        skipped_rows.append({
                            'row': row_num,
                            'roll_number': roll_number,
                            'name': name,
                            'reason': "Already enrolled in this batch (Skipped duplicate)."
                        })
                else:
                    error_rows.append({
                        'row': row_num,
                        'roll_number': roll_number,
                        'name': name,
                        'reason': f"Roll number is already assigned to another batch ({existing_student.batch.name})."
                    })
                continue

            new_stu = Student(
                batch=batch,
                roll_number=roll_number,
                name=name,
                email=email,
                phone=phone,
                join_date=join_date,
                status=status_val,
                notes=notes,
                avatar_color=random.choice(AVATAR_COLORS)
            )
            success_students.append(new_stu)

        with transaction.atomic():
            if success_students:
                Student.objects.bulk_create(success_students)
            if updated_students:
                for stu in updated_students:
                    stu.save()

        import_results = {
            'created_count': len(success_students),
            'updated_count': len(updated_students),
            'skipped_count': len(skipped_rows),
            'error_count': len(error_rows),
            'skipped_rows': skipped_rows,
            'error_rows': error_rows,
        }

        if success_students or updated_students:
            msg = f"Successfully imported {len(success_students)} student(s)"
            if updated_students:
                msg += f" and updated {len(updated_students)} student(s)"
            messages.success(request, msg + f" in batch '{batch.name}'!")
        elif error_rows:
            messages.error(request, f"Import stopped with {len(error_rows)} error(s). Please review details below.")
        elif skipped_rows:
            messages.warning(request, f"All {len(skipped_rows)} row(s) were skipped as duplicates.")

    return render(request, 'evaluator_app/batches/student_import.html', {
        'batch': batch,
        'results': import_results,
    })



# ==============================================================================
# ADMIN HUB (Locations & Evaluators Management)
# ==============================================================================

@admin_required
def admin_locations_view(request):
    locations = Location.objects.all().prefetch_related('batches', 'evaluators')
    
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            loc = form.save()
            messages.success(request, f"Location '{loc.name}' created successfully!")
            return redirect('admin_locations')
    else:
        form = LocationForm()
        
    return render(request, 'evaluator_app/admin/locations.html', {
        'locations': locations,
        'form': form
    })


@admin_required
def admin_evaluators_view(request):
    evaluators = UserProfile.objects.select_related('user').prefetch_related('assigned_locations').all()
    all_locations = Location.objects.filter(is_active=True)
    
    return render(request, 'evaluator_app/admin/evaluators.html', {
        'evaluators': evaluators,
        'all_locations': all_locations
    })


@admin_required
def admin_assign_evaluator_view(request, profile_id):
    profile = get_object_or_404(UserProfile, id=profile_id)
    
    if request.method == 'POST':
        form = EvaluatorAssignmentForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated assignment for {profile.user.username} successfully!")
            return redirect('admin_evaluators')
    else:
        form = EvaluatorAssignmentForm(instance=profile)
        
    return render(request, 'evaluator_app/admin/evaluator_assignment_form.html', {
        'form': form,
        'profile': profile
    })


@admin_required
def admin_create_evaluator_view(request):
    all_locations = Location.objects.filter(is_active=True)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password')
        designation = request.POST.get('designation', 'Evaluator')
        phone = request.POST.get('phone', '')
        role = request.POST.get('role', 'EVALUATOR')
        selected_location_ids = request.POST.getlist('locations')

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return redirect('admin_evaluators')

        user = User.objects.create_user(username=username, email=email, password=password)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.designation = designation
        profile.phone = phone
        profile.save()
        
        if selected_location_ids:
            profile.assigned_locations.set(selected_location_ids)
            
        messages.success(request, f"Evaluator account '{username}' created and assigned successfully!")
        return redirect('admin_evaluators')

    return render(request, 'evaluator_app/admin/evaluator_create_form.html', {
        'all_locations': all_locations
    })


# ==============================================================================
# STUDENT PROJECT MANAGEMENT & EVALUATION
# ==============================================================================

@evaluator_required
def project_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user)
    projects_qs = Project.objects.filter(batch__in=accessible_batches).prefetch_related('students', 'batch', 'created_by')

    # Status Tab Filter
    status_filter = request.GET.get('status', 'ALL')
    if status_filter != 'ALL' and status_filter in ['PLANNING', 'IN_PROGRESS', 'UNDER_REVIEW', 'COMPLETED', 'ON_HOLD']:
        projects_qs = projects_qs.filter(status=status_filter)

    # Project Type Filter
    type_filter = request.GET.get('type')
    if type_filter in ['MAIN', 'MINI', 'ASSIGNMENT', 'PRACTICE', 'CLIENT']:
        projects_qs = projects_qs.filter(project_type=type_filter)

    # Batch Filter
    batch_id = request.GET.get('batch')
    if batch_id:
        projects_qs = projects_qs.filter(batch_id=batch_id)

    # Student Filter
    student_id = request.GET.get('student')
    if student_id:
        projects_qs = projects_qs.filter(students__id=student_id)

    # Search Query
    q = request.GET.get('q', '').strip()
    if q:
        projects_qs = projects_qs.filter(
            Q(title__icontains=q) |
            Q(technologies__icontains=q) |
            Q(description__icontains=q) |
            Q(students__name__icontains=q) |
            Q(students__roll_number__icontains=q)
        ).distinct()

    # Calculate High-Level Metrics (Across all accessible batches)
    all_projects = Project.objects.filter(batch__in=accessible_batches)
    total_projects = all_projects.count()
    in_progress_count = all_projects.filter(status='IN_PROGRESS').count()
    under_review_count = all_projects.filter(status='UNDER_REVIEW').count()
    completed_count = all_projects.filter(status='COMPLETED').count()
    planning_count = all_projects.filter(status='PLANNING').count()
    on_hold_count = all_projects.filter(status='ON_HOLD').count()
    avg_progress = round(all_projects.aggregate(Avg('progress_percentage'))['progress_percentage__avg'] or 0, 1) if total_projects > 0 else 0

    # Extract Popular Technology Tags
    tech_counter = {}
    for p in all_projects:
        for tech in p.tech_list:
            tech_clean = tech.strip()
            if tech_clean:
                tech_counter[tech_clean] = tech_counter.get(tech_clean, 0) + 1
    top_technologies = sorted(tech_counter.items(), key=lambda x: x[1], reverse=True)[:10]

    # Quick create form
    create_form = ProjectForm(user=user)

    context = {
        'projects': projects_qs,
        'accessible_batches': accessible_batches,
        'selected_status': status_filter,
        'selected_type': type_filter or '',
        'selected_batch': batch_id or '',
        'selected_student': student_id or '',
        'search_query': q,
        # KPI Stats
        'total_projects': total_projects,
        'in_progress_count': in_progress_count,
        'under_review_count': under_review_count,
        'completed_count': completed_count,
        'planning_count': planning_count,
        'on_hold_count': on_hold_count,
        'avg_progress': avg_progress,
        'top_technologies': top_technologies,
        'create_form': create_form,
    }
    return render(request, 'evaluator_app/projects/project_hub.html', context)


@evaluator_required
def project_create_view(request):
    user = request.user
    batch_id = request.GET.get('batch_id')
    student_id = request.GET.get('student_id')

    initial_batch = None
    initial_student = None

    if batch_id:
        initial_batch = get_object_or_404(Batch, id=batch_id)
        if not can_user_access_batch(user, initial_batch):
            messages.error(request, "Permission denied for this batch.")
            return redirect('project_hub')

    if student_id:
        initial_student = get_object_or_404(Student, id=student_id)
        if not can_user_access_batch(user, initial_student.batch):
            messages.error(request, "Permission denied for this student.")
            return redirect('project_hub')
        if not initial_batch:
            initial_batch = initial_student.batch

    accessible_batches = get_user_batches(user)
    batch_students_map = {}
    for b in accessible_batches.prefetch_related('students'):
        batch_students_map[str(b.id)] = [
            {
                'id': s.id,
                'name': s.name,
                'roll_number': s.roll_number,
                'label': f"{s.name} ({s.roll_number})"
            }
            for s in b.students.filter(status='ACTIVE')
        ]

    if request.method == 'POST':
        form = ProjectForm(request.POST, user=user)
        if form.is_valid():
            batch_ids = request.POST.getlist('batch_ids')
            if not batch_ids:
                messages.error(request, "Please select at least one batch.")
                return redirect('project_create')

            # Fetch all batches and verify access
            batches = Batch.objects.filter(id__in=batch_ids)
            for batch in batches:
                if not can_user_access_batch(user, batch):
                    messages.error(request, f"Permission denied for batch {batch.name}.")
                    return redirect('project_create')

            assign_to_whole_batch = form.cleaned_data.get('assign_to_whole_batch')
            selected_students = form.cleaned_data.get('students', [])

            created_projects = []
            for batch in batches:
                project = form.save(commit=False)
                project.pk = None
                project.batch = batch
                project.created_by = user
                project.save()

                if assign_to_whole_batch:
                    project.students.set(batch.students.filter(status='ACTIVE'))
                else:
                    batch_students = [s for s in selected_students if s.batch_id == batch.id]
                    project.students.set(batch_students)

                ProjectUpdate.objects.create(
                    project=project,
                    author=user,
                    progress_percentage=project.progress_percentage,
                    status_at_update=project.get_status_display(),
                    notes=f"Project initiated with status '{project.get_status_display()}' and {project.progress_percentage}% initial progress."
                )
                created_projects.append(project)

            if len(created_projects) == 1:
                messages.success(request, f"Project '{created_projects[0].title}' created successfully!")
                return redirect('project_detail', project_id=created_projects[0].id)
            else:
                messages.success(request, f"Project '{created_projects[0].title}' created successfully across {len(batches)} batches!")
                return redirect('project_hub')
        else:
            messages.error(request, "Error creating project. Please correct the highlighted fields.")
    else:
        form = ProjectForm(user=user, initial_batch=initial_batch, initial_student=initial_student)

    return render(request, 'evaluator_app/projects/project_form.html', {
        'form': form,
        'title': 'Create New Student Project',
        'is_edit': False,
        'batch_students_json': json.dumps(batch_students_map),
    })


@evaluator_required
def project_detail_view(request, project_id):
    user = request.user
    project = get_object_or_404(Project.objects.prefetch_related('students', 'batch', 'updates', 'updates__author'), id=project_id)

    if not can_user_access_batch(user, project.batch):
        messages.error(request, "Permission denied for this project.")
        return redirect('project_hub')

    # Progress and Evaluation forms
    progress_form = ProjectProgressUpdateForm(instance=project)
    eval_form = ProjectEvaluationForm(instance=project)

    # Calculate days timeline
    today = timezone.now().date()
    days_elapsed = (today - project.start_date).days if project.start_date else 0
    days_remaining = None
    if project.target_completion_date:
        days_remaining = (project.target_completion_date - today).days

    updates = project.updates.all()

    context = {
        'project': project,
        'progress_form': progress_form,
        'eval_form': eval_form,
        'updates': updates,
        'days_elapsed': max(0, days_elapsed),
        'days_remaining': days_remaining,
    }
    return render(request, 'evaluator_app/projects/project_detail.html', context)


@evaluator_required
def project_edit_view(request, project_id):
    user = request.user
    project = get_object_or_404(Project, id=project_id)

    if not can_user_access_batch(user, project.batch):
        messages.error(request, "Permission denied.")
        return redirect('project_hub')

    accessible_batches = get_user_batches(user)
    batch_students_map = {}
    for b in accessible_batches.prefetch_related('students'):
        batch_students_map[str(b.id)] = [
            {
                'id': s.id,
                'name': s.name,
                'roll_number': s.roll_number,
                'label': f"{s.name} ({s.roll_number})"
            }
            for s in b.students.filter(status='ACTIVE')
        ]

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Project '{project.title}' updated successfully!")
            return redirect('project_detail', project_id=project.id)
        else:
            messages.error(request, "Please check the form for errors.")
    else:
        form = ProjectForm(instance=project, user=user)

    return render(request, 'evaluator_app/projects/project_form.html', {
        'form': form,
        'project': project,
        'title': f'Edit Project: {project.title}',
        'is_edit': True,
        'batch_students_json': json.dumps(batch_students_map),
    })


@evaluator_required
def batch_students_api(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
    
    students = batch.students.filter(status='ACTIVE').order_by('name')
    data = [
        {
            'id': s.id,
            'name': s.name,
            'roll_number': s.roll_number,
            'label': f"{s.name} ({s.roll_number})"
        }
        for s in students
    ]
    return JsonResponse({'success': True, 'batch_id': batch.id, 'students': data})


@evaluator_required
def batch_next_roll_number_api(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    next_roll = generate_batch_student_roll_number(batch)
    return JsonResponse({
        'success': True,
        'batch_id': batch.id,
        'batch_code': batch.code,
        'next_roll_number': next_roll,
        'roll_number': next_roll,
    })


@admin_required
def project_delete_view(request, project_id):
    user = request.user
    project = get_object_or_404(Project, id=project_id)

    if not can_user_access_batch(user, project.batch):
        messages.error(request, "Permission denied.")
        return redirect('project_hub')

    if request.method == 'POST':
        title = project.title
        project.delete()
        messages.success(request, f"Project '{title}' was permanently deleted.")
        return redirect('project_hub')

    return render(request, 'evaluator_app/projects/project_confirm_delete.html', {
        'project': project
    })


@evaluator_required
def project_update_progress_view(request, project_id):
    user = request.user
    project = get_object_or_404(Project, id=project_id)

    if not can_user_access_batch(user, project.batch):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('project_hub')

    if request.method == 'POST':
        form = ProjectProgressUpdateForm(request.POST, instance=project)
        if form.is_valid():
            updated_project = form.save()
            milestone_notes = form.cleaned_data.get('milestone_notes', '').strip()

            # Record milestone update if notes provided or progress changed
            if milestone_notes:
                ProjectUpdate.objects.create(
                    project=updated_project,
                    author=user,
                    progress_percentage=updated_project.progress_percentage,
                    status_at_update=updated_project.get_status_display(),
                    notes=milestone_notes
                )

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'success': True,
                    'message': f"Project progress updated to {updated_project.progress_percentage}%!",
                    'progress_percentage': updated_project.progress_percentage,
                    'status': updated_project.status,
                    'status_display': updated_project.get_status_display(),
                })

            messages.success(request, f"Progress for '{project.title}' updated to {updated_project.progress_percentage}% ({updated_project.get_status_display()})!")
            return redirect('project_detail', project_id=project.id)
        else:
            messages.error(request, "Could not update progress. Please check your inputs.")

    return redirect('project_detail', project_id=project.id)


@evaluator_required
def project_evaluate_view(request, project_id):
    user = request.user
    project = get_object_or_404(Project, id=project_id)

    if not can_user_access_batch(user, project.batch):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('project_hub')

    if request.method == 'POST':
        form = ProjectEvaluationForm(request.POST, instance=project)
        if form.is_valid():
            evaluated_project = form.save(commit=False)
            evaluated_project.calculate_total_score()
            evaluated_project.save()

            # Log evaluation milestone in project updates
            ProjectUpdate.objects.create(
                project=evaluated_project,
                author=user,
                progress_percentage=evaluated_project.progress_percentage,
                status_at_update=evaluated_project.get_status_display(),
                notes=f"Evaluated by {user.get_full_name() or user.username}: Overall Score {evaluated_project.total_score}% (Grade: {evaluated_project.grade})."
            )

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'success': True,
                    'message': f"Project evaluated successfully with total score {evaluated_project.total_score}% ({evaluated_project.grade})!",
                    'total_score': evaluated_project.total_score,
                    'grade': evaluated_project.grade,
                })

            messages.success(request, f"Project '{project.title}' evaluated: {evaluated_project.total_score}% (Grade {evaluated_project.grade})!")
            return redirect('project_detail', project_id=project.id)
        else:
            messages.error(request, "Invalid evaluation inputs. Please verify all score values (0-100).")

    return redirect('project_detail', project_id=project.id)


# ==============================================================================
# SYLLABUS MANAGEMENT VIEWS
# ==============================================================================

@evaluator_required
def syllabus_list_view(request):
    user = request.user
    syllabi = Syllabus.objects.all().prefetch_related('tasks', 'batch_assignments')
    return render(request, 'evaluator_app/syllabus/syllabus_list.html', {
        'syllabi': syllabi,
    })


@evaluator_required
def syllabus_create_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can create a Syllabus.')
        return redirect('syllabus_list')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        total_modules = request.POST.get('total_modules', '1').strip()
        if not total_modules.isdigit() or int(total_modules) < 1:
            total_modules = 1
        else:
            total_modules = int(total_modules)

        if not name:
            messages.error(request, 'Syllabus name is required.')
        else:
            syllabus = Syllabus.objects.create(
                name=name,
                description=description,
                total_modules=total_modules,
                created_by=user
            )
            messages.success(request, f"Syllabus '{syllabus.name}' created with {total_modules} module(s)!")
            return redirect('syllabus_detail', syllabus_id=syllabus.id)
    return render(request, 'evaluator_app/syllabus/syllabus_form.html', {})


@evaluator_required
def syllabus_detail_view(request, syllabus_id):
    user = request.user
    syllabus = get_object_or_404(Syllabus, id=syllabus_id)
    tasks = syllabus.tasks.order_by('order')
    all_evaluators = User.objects.filter(profile__isnull=False).order_by('username')
    batch_assignments = syllabus.batch_assignments.select_related('batch', 'batch__location')
    accessible_batches = get_user_batches(user)
    # Exclude batches already assigned to this syllabus
    assigned_batch_ids = batch_assignments.values_list('batch_id', flat=True)
    unassigned_batches = accessible_batches.exclude(id__in=assigned_batch_ids)

    # Fetch accessible batch groups
    profile, _ = UserProfile.objects.get_or_create(user=user)
    is_admin = user.is_superuser or profile.role == 'ADMIN'
    if is_admin:
        accessible_groups = BatchGroup.objects.all()
    else:
        accessible_groups = BatchGroup.objects.filter(
            batches__location__in=profile.assigned_locations.filter(is_active=True)
        ).distinct()

    return render(request, 'evaluator_app/syllabus/syllabus_detail.html', {
        'syllabus': syllabus,
        'tasks': tasks,
        'all_evaluators': all_evaluators,
        'batch_assignments': batch_assignments,
        'unassigned_batches': unassigned_batches,
        'accessible_groups': accessible_groups,
        'all_syllabi': Syllabus.objects.all(),
    })


@evaluator_required
def syllabus_task_add_view(request, syllabus_id):
    from .services import generate_batch_schedule
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can add tasks to a Syllabus.')
        return redirect('syllabus_detail', syllabus_id=syllabus_id)

    syllabus = get_object_or_404(Syllabus, id=syllabus_id)
    if request.method == 'POST':
        if syllabus.tasks.count() >= syllabus.total_modules:
            messages.error(request, f"Cannot add more modules. The limit of {syllabus.total_modules} modules has been reached.")
            return redirect('syllabus_detail', syllabus_id=syllabus_id)

        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        assigner_id = request.POST.get('default_assigner', '')
        assigner_name = request.POST.get('default_assigner_name', '').strip()
        
        # Determine next order number
        last_task = syllabus.tasks.order_by('-order').first()
        order = (last_task.order + 1) if last_task else 1
        
        if not title:
            messages.error(request, 'Module name is required.')
        else:
            assigner = None
            if assigner_id and assigner_id != 'UNREGISTERED':
                assigner = User.objects.filter(id=assigner_id).first()
                assigner_name = '' # Clear it if a registered user is selected
                
            SyllabusTask.objects.create(
                syllabus=syllabus,
                order=order,
                title=title,
                description=description,
                default_assigner=assigner,
                default_assigner_name=assigner_name if not assigner else ''
            )
            # Auto-regenerate schedule for ALL batches already using this syllabus
            for ba in syllabus.batch_assignments.all():
                generate_batch_schedule(ba)
            messages.success(request, f'Module "{title}" added and schedules updated for all assigned batches.')
        return redirect('syllabus_detail', syllabus_id=syllabus_id)
    return redirect('syllabus_detail', syllabus_id=syllabus_id)


@evaluator_required
def syllabus_task_edit_view(request, syllabus_id, task_id):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can edit syllabus tasks.')
        return redirect('syllabus_detail', syllabus_id=syllabus_id)

    syllabus = get_object_or_404(Syllabus, id=syllabus_id)
    task = get_object_or_404(SyllabusTask, id=task_id, syllabus=syllabus)
    if request.method == 'POST':
        from .services import generate_batch_schedule
        task.title = request.POST.get('title', task.title).strip()
        task.description = request.POST.get('description', task.description).strip()
        
        assigner_id = request.POST.get('default_assigner', '')
        assigner_name = request.POST.get('default_assigner_name', '').strip()
        
        if assigner_id and assigner_id != 'UNREGISTERED':
            task.default_assigner = User.objects.filter(id=assigner_id).first()
            task.default_assigner_name = ''
        elif assigner_id == 'UNREGISTERED':
            task.default_assigner = None
            task.default_assigner_name = assigner_name
        else:
            task.default_assigner = None
            task.default_assigner_name = ''
            
        task.save()
        # Regenerate schedules for all assigned batches
        for ba in syllabus.batch_assignments.all():
            generate_batch_schedule(ba)
        messages.success(request, f'Task "{task.title}" updated and schedules refreshed.')
    return redirect('syllabus_detail', syllabus_id=syllabus_id)


@evaluator_required
def syllabus_task_delete_view(request, syllabus_id, task_id):
    from .services import generate_batch_schedule
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can delete syllabus tasks.')
        return redirect('syllabus_detail', syllabus_id=syllabus_id)

    syllabus = get_object_or_404(Syllabus, id=syllabus_id)
    task = get_object_or_404(SyllabusTask, id=task_id, syllabus=syllabus)
    task.delete()
    # Regenerate schedules for all assigned batches
    for ba in syllabus.batch_assignments.all():
        generate_batch_schedule(ba)
    messages.success(request, 'Task removed and schedules updated for all assigned batches.')
    return redirect('syllabus_detail', syllabus_id=syllabus_id)


@evaluator_required
def syllabus_delete_view(request, syllabus_id):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can delete a Syllabus.')
        return redirect('syllabus_list')
    syllabus = get_object_or_404(Syllabus, id=syllabus_id)
    if request.method == 'POST':
        syllabus.delete()
        messages.success(request, 'Syllabus deleted.')
        return redirect('syllabus_list')
    return render(request, 'evaluator_app/syllabus/syllabus_confirm_delete.html', {'syllabus': syllabus})


@evaluator_required
def syllabus_assign_batches_view(request, syllabus_id):
    from .services import generate_batch_schedule
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can assign a Syllabus to batches.')
        return redirect('syllabus_detail', syllabus_id=syllabus_id)

    if request.method == 'POST':
        syllabus = get_object_or_404(Syllabus, id=syllabus_id)
        batch_ids = request.POST.getlist('batch_ids')
        
        if not batch_ids:
            messages.error(request, 'Please select at least one batch.')
            return redirect('syllabus_detail', syllabus_id=syllabus_id)

        assigned_count = 0
        for b_id in batch_ids:
            batch = Batch.objects.filter(id=b_id).first()
            if batch and can_user_access_batch(user, batch):
                batch_syllabus, created = BatchSyllabus.objects.update_or_create(
                    batch=batch,
                    defaults={'syllabus': syllabus, 'start_date': batch.start_date, 'assigned_by': user}
                )
                generate_batch_schedule(batch_syllabus)
                assigned_count += 1
                
        if assigned_count > 0:
            messages.success(request, f"Syllabus '{syllabus.name}' assigned to {assigned_count} batch(es) and schedules generated!")
        else:
            messages.warning(request, "No batches were assigned. Please check permissions.")
            
    return redirect('syllabus_detail', syllabus_id=syllabus_id)


@evaluator_required
def batch_syllabus_assign_view(request, batch_id):
    from .services import generate_batch_schedule
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('batch_list')

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_admin:
        messages.error(request, 'Only admins can assign a Syllabus to a batch.')
        return redirect('batch_detail', batch_id=batch_id)

    if request.method == 'POST':
        syllabus_id = request.POST.get('syllabus_id')

        syllabus = get_object_or_404(Syllabus, id=syllabus_id)
        batch_syllabus, created = BatchSyllabus.objects.update_or_create(
            batch=batch,
            defaults={'syllabus': syllabus, 'start_date': batch.start_date, 'assigned_by': user}
        )
        generate_batch_schedule(batch_syllabus)
        messages.success(request, f"Syllabus '{syllabus.name}' assigned to {batch.name} and schedule generated!")
        return redirect('batch_schedule_view', batch_id=batch_id)
    return redirect('batch_detail', batch_id=batch_id)


@evaluator_required
def batch_schedule_view(request, batch_id):
    from .services import generate_batch_schedule
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('batch_list')

    batch_syllabus = getattr(batch, 'syllabus_assignment', None)
    schedules = BatchTaskSchedule.objects.filter(batch=batch).select_related('syllabus_task').order_by('date')
    all_syllabi = Syllabus.objects.all()
    syllabus_tasks = batch_syllabus.syllabus.tasks.order_by('order') if batch_syllabus else []
    all_evaluators = User.objects.filter(profile__isnull=False).order_by('username')

    return render(request, 'evaluator_app/syllabus/batch_schedule.html', {
        'batch': batch,
        'batch_syllabus': batch_syllabus,
        'schedules': schedules,
        'all_syllabi': all_syllabi,
        'syllabus_tasks': syllabus_tasks,
        'all_evaluators': all_evaluators,
    })


@evaluator_required
def batch_schedule_reschedule_view(request, batch_id):
    from .services import generate_batch_schedule
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('batch_list')

    if request.method == 'POST':
        date_str = request.POST.get('date')
        syllabus_task_id = request.POST.get('syllabus_task_id', '')
        custom_title = request.POST.get('custom_task_title', '').strip()
        custom_desc = request.POST.get('custom_task_description', '').strip()

        try:
            sched_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date.')
            return redirect('batch_schedule_view', batch_id=batch_id)

        incharge_id = request.POST.get('incharge_id', '')
        status = request.POST.get('status', 'PENDING')

        syllabus_task = None
        incharge_user = None
        
        if syllabus_task_id:
            syllabus_task = SyllabusTask.objects.filter(id=syllabus_task_id).first()
            if syllabus_task and syllabus_task.default_assigner:
                incharge_user = syllabus_task.default_assigner
        else:
            if incharge_id:
                incharge_user = User.objects.filter(id=incharge_id).first()

        BatchTaskSchedule.objects.update_or_create(
            batch=batch,
            date=sched_date,
            defaults={
                'syllabus_task': syllabus_task,
                'custom_task_title': custom_title if not syllabus_task else '',
                'custom_task_description': custom_desc if not syllabus_task else '',
                'is_rescheduled': True,
                'incharge': incharge_user,
                'status': status,
            }
        )
        messages.success(request, f'Task rescheduled for {sched_date.strftime("%b %d, %Y")}.')
    return redirect('batch_schedule_view', batch_id=batch_id)


@evaluator_required
def batch_schedule_toggle_status_view(request, schedule_id):
    if request.method == 'POST':
        schedule = get_object_or_404(BatchTaskSchedule, id=schedule_id)
        if can_user_access_batch(request.user, schedule.batch):
            new_status = request.POST.get('status')
            if new_status in ['PENDING', 'COMPLETED']:
                schedule.status = new_status
                schedule.save()
                
                # Update all corresponding student tasks
                title = schedule.syllabus_task.title if schedule.syllabus_task else schedule.custom_task_title
                from .models import StudentTask
                student_tasks = StudentTask.objects.filter(batch=schedule.batch, title=title)
                
                if new_status == 'COMPLETED':
                    student_tasks.update(status='COMPLETED', completed_at=timezone.now())
                else:
                    student_tasks.update(status='PENDING', completed_at=None)

                messages.success(request, f"Task status updated to {new_status}")
    return redirect(request.META.get('HTTP_REFERER', 'batch_list'))

@evaluator_required
def ajax_get_batch_syllabus_modules(request):
    batch_id = request.GET.get('batch_id')
    if not batch_id:
        return JsonResponse({'error': 'batch_id required'}, status=400)
    
    batch = Batch.objects.filter(id=batch_id).first()
    if not batch or not can_user_access_batch(request.user, batch):
        return JsonResponse({'error': 'invalid batch or permission denied'}, status=403)
        
    schedules = BatchTaskSchedule.objects.filter(batch=batch, syllabus_task__isnull=False).select_related('syllabus_task').order_by('date')
    
    modules = []
    for sched in schedules:
        modules.append({
            'schedule_id': sched.id,
            'module_id': sched.syllabus_task.id,
            'title': sched.syllabus_task.title,
            'description': sched.syllabus_task.description,
            'order': sched.syllabus_task.order,
            'date': sched.date.strftime('%Y-%m-%d')
        })
        
    return JsonResponse({'modules': modules})


@evaluator_required
def batch_syllabus_download_csv_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('batch_list')

    # Get Batch Syllabus and Schedule
    batch_syllabus = getattr(batch, 'syllabus_assignment', None)
    schedules = BatchTaskSchedule.objects.filter(batch=batch).select_related('syllabus_task').order_by('date')
    
    in_charge = "N/A"
    if batch_syllabus and batch_syllabus.assigned_by:
        in_charge = batch_syllabus.assigned_by.get_full_name() or batch_syllabus.assigned_by.username

    total_students = batch.students.filter(status='ACTIVE').count()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="syllabus_schedule_{batch.name}_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Batch Name', 'Total No. of Students', 'Module', 'Date', 'Day', 'In-Charge', 'Remarks'])

    for sched in schedules:
        if sched.syllabus_task:
            module_name = sched.syllabus_task.title
        elif sched.custom_task_title:
            module_name = sched.custom_task_title
        else:
            module_name = "N/A"

        date_str = sched.date.strftime("%d %b %Y")
        day_str = sched.date.strftime("%A")
        remarks = "Rescheduled" if sched.is_rescheduled else ""

        writer.writerow([
            batch.name,
            total_students,
            module_name,
            date_str,
            day_str,
            in_charge,
            remarks
        ])

    return response


@evaluator_required
def export_batch_tasks_csv_view(request, batch_id):
    user = request.user
    batch = get_object_or_404(Batch, id=batch_id)
    if not can_user_access_batch(user, batch):
        messages.error(request, 'Permission denied.')
        return redirect('batch_list')

    # Get all distinct tasks assigned to students in this batch
    tasks = StudentTask.objects.filter(student__batch=batch).select_related('assigned_by', 'student').order_by('-assigned_date')
    
    # We want a unique list of tasks by title and assigned date (or just all tasks)
    # The user asked for "Task Title, Description, Priority, Module/Syllabus, Assigned Date, and Target Completion Date"
    # We will just list all individual student tasks, or group them if they are identical.
    # Grouping them is better for a "Batch Task List".
    
    # Let's get unique tasks by attributes
    unique_tasks = []
    seen = set()
    for t in tasks:
        key = (t.title, t.assigned_date, t.due_date)
        if key not in seen:
            seen.add(key)
            unique_tasks.append(t)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="task_list_{batch.name}_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Task Title', 'Description', 'Priority', 'Module/Syllabus', 'Assigned Date', 'Target Completion Date', 'Assigned By'])

    for t in unique_tasks:
        writer.writerow([
            t.title,
            t.description,
            t.get_priority_display(),
            "Yes" if getattr(t, 'is_syllabus_task', False) else "No",
            t.assigned_date.strftime("%d %b %Y") if t.assigned_date else 'N/A',
            t.due_date.strftime("%d %b %Y") if t.due_date else 'N/A',
            t.assigned_by.get_full_name() or t.assigned_by.username if t.assigned_by else 'N/A'
        ])

    return response


@evaluator_required
def reports_hub_view(request):
    user = request.user
    accessible_batches = get_user_batches(user).order_by('-created_at')
    accessible_students = get_user_students(user).order_by('name')

    context = {
        'batches': accessible_batches,
        'students': accessible_students,
    }
    return render(request, 'evaluator_app/reports/reports_hub.html', context)
