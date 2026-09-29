from django.urls import path
from django.views.generic.base import RedirectView
from . import views
from . import documents

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('quick-login/<str:role>/', views.quick_login_view, name='quick_login'),

    # Dashboard
    path('', RedirectView.as_view(pattern_name='login', permanent=False), name='root_redirect'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Batches
    path('batches/', views.batch_list_view, name='batch_list'),
    path('batches/create/', views.batch_create_view, name='batch_create'),
    path('batches/<int:batch_id>/', views.batch_detail_view, name='batch_detail'),
    path('batches/<int:batch_id>/edit/', views.batch_edit_view, name='batch_edit'),
    path('batches/<int:batch_id>/delete/', views.batch_delete_view, name='batch_delete'),
    path('batches/<int:batch_id>/export/', views.export_batch_csv_view, name='batch_export_csv'),
    path('batches/<int:batch_id>/export-attendance/', views.export_batch_attendance_csv_view, name='export_batch_attendance'),
    path('batches/<int:batch_id>/import/', views.batch_student_import_view, name='batch_student_import'),
    path('batches/<int:batch_id>/sample-template/<str:file_format>/', views.download_student_template_view, name='download_student_template'),

    # Batch Groups (Merged Batches)
    path('batch-groups/', views.batch_group_list_view, name='batch_group_list'),
    path('batch-groups/create/', views.batch_group_create_view, name='batch_group_create'),
    path('batch-groups/<int:group_id>/edit/', views.batch_group_edit_view, name='batch_group_edit'),
    path('batch-groups/<int:group_id>/delete/', views.batch_group_delete_view, name='batch_group_delete'),

    # Students
    path('students/add/', views.student_add_view, name='student_add'),
    path('students/add/<int:batch_id>/', views.student_add_view, name='student_add_to_batch'),
    path('students/<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('students/<int:student_id>/report/', views.student_report_download_view, name='student_report_download'),
    path('students/<int:student_id>/edit/', views.student_edit_view, name='student_edit'),
    path('students/<int:student_id>/delete/', views.student_delete_view, name='student_delete'),
    path('students/<int:student_id>/export-attendance/', views.export_student_attendance_csv_view, name='export_student_attendance'),
    path('api/students/<int:student_id>/update-payment-status/', views.update_payment_status_api, name='update_payment_status_api'),

    # Daily Evaluation Hub
    path('evaluations/', views.evaluation_hub_view, name='evaluation_hub'),
    path('evaluations/student/<int:student_id>/', views.student_evaluate_view, name='student_evaluate'),
    path('evaluations/history/', views.evaluation_history_view, name='evaluation_history'),
    path('evaluations/batch/<int:batch_id>/bulk/', views.batch_bulk_evaluate_view, name='batch_bulk_evaluate'),

    # Student Task Management & Deliverables
    path('tasks/', views.task_hub_view, name='task_hub'),
    path('tasks/sync-deadlines/', views.task_hub_sync_deadlines_view, name='task_hub_sync_deadlines'),
    path('tasks/create/', views.task_create_view, name='task_create'),
    path('tasks/evaluations/', views.task_evaluation_hub_view, name='task_evaluation_hub'),
    path('tasks/<int:task_id>/evaluate/', views.task_evaluate_view, name='task_evaluate'),
    path('tasks/<int:task_id>/update-status/', views.task_update_status_view, name='task_update_status'),
    path('tasks/<int:task_id>/delete/', views.task_delete_view, name='task_delete'),
    path('tasks/bulk-delete/', views.bulk_task_delete_view, name='bulk_task_delete'),
    path('api/students/<int:student_id>/tasks/', views.student_tasks_api, name='student_tasks_api'),
    path('api/batches/<int:batch_id>/students/', views.batch_students_api, name='batch_students_api'),
    path('api/batches/<int:batch_id>/next-roll-number/', views.batch_next_roll_number_api, name='batch_next_roll_number_api'),
    path('ajax/batch-syllabus-modules/', views.ajax_get_batch_syllabus_modules, name='ajax_get_batch_syllabus_modules'),

    # Attendance Hub
    path('attendance/reschedule/', views.batch_reschedule_class_view, name='batch_reschedule_class'),
    path('attendance/', views.attendance_hub_view, name='attendance_hub'),
    path('attendance/register/<int:batch_id>/', views.attendance_register_view, name='attendance_register'),
    path('attendance/register/group/<int:group_id>/', views.attendance_register_view, name='attendance_register_group'),

    # Student Projects & Technology Tracking
    path('projects/', views.project_hub_view, name='project_hub'),
    path('projects/create/', views.project_create_view, name='project_create'),
    path('projects/<int:project_id>/', views.project_detail_view, name='project_detail'),
    path('projects/<int:project_id>/edit/', views.project_edit_view, name='project_edit'),
    path('projects/<int:project_id>/delete/', views.project_delete_view, name='project_delete'),
    path('projects/<int:project_id>/update-progress/', views.project_update_progress_view, name='project_update_progress'),
    path('projects/<int:project_id>/evaluate/', views.project_evaluate_view, name='project_evaluate'),

    # Admin Management
    path('admin-panel/locations/', views.admin_locations_view, name='admin_locations'),
    path('admin-panel/evaluators/', views.admin_evaluators_view, name='admin_evaluators'),
    path('admin-panel/evaluators/create/', views.admin_create_evaluator_view, name='admin_create_evaluator'),
    path('admin-panel/evaluators/<int:profile_id>/assign/', views.admin_assign_evaluator_view, name='admin_assign_evaluator'),

    # Syllabus Management
    path('syllabus/', views.syllabus_list_view, name='syllabus_list'),
    path('syllabus/create/', views.syllabus_create_view, name='syllabus_create'),
    path('syllabus/<int:syllabus_id>/', views.syllabus_detail_view, name='syllabus_detail'),
    path('syllabus/<int:syllabus_id>/delete/', views.syllabus_delete_view, name='syllabus_delete'),
    path('syllabus/<int:syllabus_id>/tasks/add/', views.syllabus_task_add_view, name='syllabus_task_add'),
    path('syllabus/<int:syllabus_id>/tasks/<int:task_id>/edit/', views.syllabus_task_edit_view, name='syllabus_task_edit'),
    path('syllabus/<int:syllabus_id>/tasks/<int:task_id>/delete/', views.syllabus_task_delete_view, name='syllabus_task_delete'),
    path('syllabus/<int:syllabus_id>/assign/', views.syllabus_assign_batches_view, name='syllabus_assign_batches'),

    # Batch Schedule / Syllabus Assignment
    path('batches/<int:batch_id>/schedule/', views.batch_schedule_view, name='batch_schedule_view'),
    path('batches/<int:batch_id>/schedule/assign-syllabus/', views.batch_syllabus_assign_view, name='batch_syllabus_assign'),
    path('batches/<int:batch_id>/schedule/reschedule/', views.batch_schedule_reschedule_view, name='batch_schedule_reschedule'),
    path('batches/schedule/<int:schedule_id>/toggle-status/', views.batch_schedule_toggle_status_view, name='batch_schedule_toggle_status'),
    path('batches/schedule/<int:schedule_id>/delete/', views.batch_schedule_delete_view, name='batch_schedule_delete'),
    path('batches/<int:batch_id>/schedule/download/', views.batch_syllabus_download_csv_view, name='batch_schedule_download'),
    path('batches/<int:batch_id>/export-tasks/', views.export_batch_tasks_csv_view, name='export_batch_tasks'),

    # Reports & Documents
    path('reports/', views.reports_hub_view, name='reports_hub'),
    path('documents/', documents.documents_hub_view, name='documents_hub'),
    path('documents/batch/<int:batch_id>/preview/', documents.documents_batch_preview_view, name='documents_batch_preview'),
    path('documents/batch/<int:batch_id>/download/', documents.documents_download_view, name='documents_download'),
]

