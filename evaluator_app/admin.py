from django.contrib import admin
from .models import Location, UserProfile, Batch, Student, Attendance, DailyEvaluation, StudentTask, Project, ProjectUpdate, Syllabus, SyllabusTask, BatchSyllabus, BatchTaskSchedule

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'designation', 'phone']

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'location', 'schedule_type', 'status', 'start_date']

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'roll_number', 'batch', 'status', 'join_date']

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'batch', 'date', 'status', 'marked_by']

@admin.register(DailyEvaluation)
class DailyEvaluationAdmin(admin.ModelAdmin):
    list_display = ['student', 'batch', 'date', 'total_score', 'grade', 'evaluator']

@admin.register(StudentTask)
class StudentTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'student', 'batch', 'status', 'due_date']

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'batch', 'project_type', 'status', 'progress_percentage', 'total_score', 'grade']
    list_filter = ['status', 'project_type', 'batch']
    search_fields = ['title', 'technologies', 'description']

@admin.register(ProjectUpdate)
class ProjectUpdateAdmin(admin.ModelAdmin):
    list_display = ['project', 'progress_percentage', 'status_at_update', 'author', 'created_at']

@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ['name', 'total_modules', 'created_at']

@admin.register(SyllabusTask)
class SyllabusTaskAdmin(admin.ModelAdmin):
    list_display = ['syllabus', 'order', 'title']

@admin.register(BatchSyllabus)
class BatchSyllabusAdmin(admin.ModelAdmin):
    list_display = ['batch', 'syllabus', 'start_date']

@admin.register(BatchTaskSchedule)
class BatchTaskScheduleAdmin(admin.ModelAdmin):
    list_display = ['batch', 'date', 'syllabus_task', 'is_rescheduled']

