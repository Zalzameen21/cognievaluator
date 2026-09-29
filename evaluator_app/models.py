import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Avg, Count, Q
from django.core.exceptions import ValidationError


class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text="e.g. CLT for Kozhikode, COK for Kochi, WND for Wayanad")
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_batches(self):
        return self.batches.count()

    @property
    def total_students(self):
        return Student.objects.filter(batch__location=self).count()


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('EVALUATOR', 'Evaluator'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='EVALUATOR')
    assigned_locations = models.ManyToManyField(Location, blank=True, related_name='evaluators')
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, default='Course Evaluator')
    avatar_color = models.CharField(max_length=20, default='#3B82F6')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'ADMIN' or self.user.is_superuser

    @property
    def is_evaluator(self):
        return self.role == 'EVALUATOR'

    def get_accessible_locations(self):
        if self.is_admin:
            return Location.objects.filter(is_active=True)
        return self.assigned_locations.filter(is_active=True)

    def can_access_location(self, location):
        if self.is_admin:
            return True
        return self.assigned_locations.filter(id=location.id).exists()

    def can_access_batch(self, batch):
        if self.is_admin:
            return True
        return self.assigned_locations.filter(id=batch.location_id).exists()


import datetime
from django.core.exceptions import ValidationError


class Batch(models.Model):
    SCHEDULE_CHOICES = [
        ('DAILY', 'Daily Class'),
        ('WEEKLY', 'Weekly Class'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('UPCOMING', 'Upcoming'),
    ]

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True, help_text="e.g. PY-CLT-01")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='batches')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_batches')
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_CHOICES, default='DAILY')
    class_days = models.CharField(
        max_length=255,
        default='Monday, Tuesday, Wednesday, Thursday, Friday',
        help_text="Days on which class is conducted (e.g. Monday, Wednesday, Friday or Saturday)"
    )
    start_time = models.TimeField(default=datetime.time(10, 0), help_text="Class starting time")
    end_time = models.TimeField(default=datetime.time(18, 0), help_text="Class ending time")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Batches'

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': "Class end time must be after start time."})

    def __str__(self):
        return f"{self.name} ({self.location.name} - {self.get_schedule_type_display()})"

    @property
    def timing(self):
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
        return "10:00 AM - 06:00 PM"

    @property
    def days_list(self):
        if not self.class_days:
            return []
        return [d.strip() for d in self.class_days.split(',') if d.strip()]

    @property
    def short_days_display(self):
        days = self.days_list
        if not days:
            return "No days specified"
        short_map = {
            'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
            'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat', 'Sunday': 'Sun'
        }
        short_names = [short_map.get(d, d[:3]) for d in days]
        if len(short_names) == 7:
            return "All Days (Mon-Sun)"
        elif short_names == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']:
            return "Mon - Fri"
        elif short_names == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']:
            return "Mon - Sat"
        elif short_names == ['Sat', 'Sun']:
            return "Weekends (Sat, Sun)"
        return ", ".join(short_names)

    @property
    def student_count(self):
        return self.students.count()

    @property
    def active_students_count(self):
        return self.students.filter(status='ACTIVE').count()

    @property
    def average_score(self):
        avg = self.evaluations.aggregate(avg_score=Avg('total_score'))['avg_score']
        return round(avg, 1) if avg else 0.0

    @property
    def attendance_percentage(self):
        total = self.attendance_records.count()
        if not total:
            return 0.0
        present_count = self.attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
        return round((present_count / total) * 100, 1)


class BatchGroup(models.Model):
    """
    Groups multiple batches together so evaluators can mark attendance and assign tasks
    to all constituent batches simultaneously.
    """
    name = models.CharField(max_length=150, help_text="e.g. Thursday Combined CSE/AD")
    batches = models.ManyToManyField(Batch, related_name='batch_groups', help_text="Select the batches to merge into this group")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_batch_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Batch Group (Merged)'
        verbose_name_plural = 'Batch Groups (Merged)'

    def __str__(self):
        return f"{self.name} ({self.batches.count()} batches)"

    @property
    def student_count(self):
        return sum(b.student_count for b in self.batches.all())


class BatchScheduleException(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='schedule_exceptions')
    original_date = models.DateField(help_text="The date of the class that is being cancelled/shifted")
    rescheduled_date = models.DateField(null=True, blank=True, help_text="The new date for the makeup class (leave blank if permanently cancelled)")
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ('batch', 'original_date')
        verbose_name = 'Batch Schedule Exception'
        verbose_name_plural = 'Batch Schedule Exceptions'

    def __str__(self):
        status = f"Moved to {self.rescheduled_date}" if self.rescheduled_date else "Cancelled"
        return f"{self.batch.name} on {self.original_date} ({status})"

def generate_batch_student_roll_number(batch):
    """
    Generates a unique, sequential roll number based on the assigned batch.
    Format: <BATCH_CODE>-<NNN> (e.g. PY-CLT-D1-001, PY-CLT-D1-002)
    Guaranteed to be unique across all students.
    """
    if not batch:
        return f"STU-{timezone.now().strftime('%y%m%d')}-001"

    if batch.code and batch.code.strip():
        prefix = re.sub(r'\s+', '-', batch.code.strip().upper())
    else:
        cleaned = re.sub(r'[^A-Za-z0-9]+', '-', batch.name.strip()).strip('-').upper()
        prefix = cleaned[:12] if cleaned else f"BATCH-{batch.id}"

    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.IGNORECASE)
    existing_rolls = Student.objects.filter(
        Q(batch=batch) | Q(roll_number__istartswith=f"{prefix}-")
    ).values_list('roll_number', flat=True)

    max_seq = 0
    for roll in existing_rolls:
        m = pattern.match(roll.strip())
        if m:
            try:
                seq = int(m.group(1))
                if seq > max_seq:
                    max_seq = seq
            except (ValueError, TypeError):
                pass

    if max_seq == 0:
        next_seq = batch.students.count() + 1
    else:
        next_seq = max_seq + 1

    candidate = f"{prefix}-{next_seq:03d}"
    while Student.objects.filter(roll_number__iexact=candidate).exists():
        next_seq += 1
        candidate = f"{prefix}-{next_seq:03d}"

    return candidate


class Student(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('COMPLETED', 'Completed'),
        ('DROPPED', 'Dropped'),
    ]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='students')
    roll_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar_color = models.CharField(max_length=20, default='#6366F1')
    join_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    payment_status = models.CharField(max_length=20, choices=[('PAID', 'Paid'), ('UNPAID', 'Unpaid')], default='UNPAID')
    student_class = models.CharField(max_length=100, blank=True, null=True, verbose_name="Class")
    academic_year = models.CharField(max_length=20, blank=True, null=True, verbose_name="Year")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.roll_number and self.batch_id:
            self.roll_number = generate_batch_student_roll_number(self.batch)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not self.roll_number and self.batch_id:
            self.roll_number = generate_batch_student_roll_number(self.batch)
        if self.batch_id and self.batch and self.batch.start_date and self.join_date:
            j_date = self.join_date.date() if hasattr(self.join_date, 'hour') else self.join_date
            b_date = self.batch.start_date.date() if hasattr(self.batch.start_date, 'hour') else self.batch.start_date
            if j_date < b_date:
                raise ValidationError({
                    'join_date': f"Enrollment Date ({j_date.strftime('%d %b, %Y')}) cannot be earlier than the Batch Start Date ({b_date.strftime('%d %b, %Y')})."
                })

    def __str__(self):
        return f"{self.name} ({self.roll_number})"

    @property
    def initials(self):
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        elif parts:
            return parts[0][:2].upper()
        return "ST"

    @property
    def average_score(self):
        avg = self.evaluations.aggregate(avg_score=Avg('total_score'))['avg_score']
        return round(avg, 1) if avg else 0.0

    @property
    def attendance_percentage(self):
        total = self.attendance_records.count()
        if not total:
            return 0.0
        present = self.attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
        return round((present / total) * 100, 1)

    @property
    def total_evaluations_count(self):
        return self.evaluations.count()

    @property
    def latest_evaluation(self):
        return self.evaluations.order_by('-date', '-created_at').first()

    @property
    def pending_tasks_count(self):
        return self.tasks.filter(status='PENDING').count()

    @property
    def completed_tasks_count(self):
        return self.tasks.filter(status__in=['COMPLETED', 'LATE']).count()

    @property
    def late_tasks_count(self):
        return self.tasks.filter(status='LATE').count()

    @property
    def total_tasks_count(self):
        return self.tasks.count()

    @property
    def total_projects_count(self):
        return self.projects.count()

    @property
    def completed_projects_count(self):
        return self.projects.filter(status='COMPLETED').count()

    @property
    def active_projects_count(self):
        return self.projects.filter(status__in=['IN_PROGRESS', 'PLANNING', 'UNDER_REVIEW']).count()


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('EXCUSED', 'Excused'),
    ]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PRESENT')
    remarks = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'date')
        ordering = ['-date', 'student__name']

    def __str__(self):
        return f"{self.student.name} - {self.date} ({self.status})"


class DailyEvaluation(models.Model):
    GRADE_CHOICES = [
        ('A+', 'A+ (Outstanding - 90-100)'),
        ('A', 'A (Excellent - 80-89)'),
        ('B+', 'B+ (Very Good - 70-79)'),
        ('B', 'B (Good - 60-69)'),
        ('C', 'C (Average - 50-59)'),
        ('NI', 'Needs Improvement (< 50)'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='evaluations')
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluations_given')
    date = models.DateField(default=timezone.now)
    topic = models.CharField(max_length=255, default='Daily Assignment & Practical Task')
    attendance_percentage = models.FloatField(default=0.0, help_text="Current attendance % at evaluation time")
    project_and_practical_task_given = models.BooleanField(default=True, help_text="Did the student receive a project/practical task today?")
    
    # 1. General & Behavioral Engagement (0-100)
    punctuality_score = models.FloatField(default=80.0, help_text="Punctuality & session discipline")
    tutor_interaction_score = models.FloatField(default=80.0, help_text="Interaction with tutor (responsiveness & engagement)")
    classmate_interaction_score = models.FloatField(default=80.0, help_text="Interaction with classmates & teamwork")
    tendency_to_study_score = models.FloatField(default=80.0, help_text="Tendency to study, curiosity & diligence")
    
    # Daily Tasks
    tasks_given = models.IntegerField(default=5, help_text="Total tasks/assignments given today")
    tasks_completed = models.IntegerField(default=5, help_text="Tasks completed by student today")
    
    # 2. Project / Task Based Assessment (0-100)
    presentation_score = models.FloatField(default=75.0, help_text="Presentation skill & way of presenting")
    problem_solving_score = models.FloatField(default=75.0, help_text="Understanding problems & implementing solutions")
    ppt_evaluation_score = models.FloatField(default=75.0, help_text="PPT / PDF evaluation (slides, images, clarity)")
    ppt_slide_count = models.IntegerField(default=6, blank=True, null=True, help_text="Number of slides/pages")
    ppt_has_images = models.BooleanField(default=True, help_text="Images/diagrams/screenshots included")
    ppt_explanation_notes = models.CharField(max_length=255, blank=True, help_text="Quality of explanations in slides")
    document_upload = models.FileField(upload_to='evaluations/documents/', blank=True, null=True, help_text="Upload PPT/PDF/Word/Image (optional)")

    # 3. Communication & Mentor Collaboration (0-100)
    communication_score = models.FloatField(default=75.0, help_text="Communication & articulation")
    suggestion_implementation_score = models.FloatField(default=80.0, help_text="Taking suggestions & implementing them")
    doubt_clearing_score = models.FloatField(default=75.0, help_text="Asking doubts & clearing them")

    # 4. Computed Overall Score & Grade
    total_score = models.FloatField(default=0.0, help_text="Overall weighted score out of 100")
    grade = models.CharField(max_length=10, choices=GRADE_CHOICES, default='B')

    # 5. Remarks & Profile Insights
    strongest_areas = models.TextField(blank=True, help_text="Strongest area of the student")
    areas_for_improvement = models.TextField(blank=True, help_text="Areas needing improvement")
    interested_areas = models.TextField(blank=True, help_text="Interested areas / career focus (e.g. Backend, Frontend, Cloud)")
    general_remarks = models.TextField(blank=True, help_text="General feedback and mentor advice")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'date')
        ordering = ['-date', '-created_at']

    @property
    def task_completion_percentage(self):
        if self.tasks_given and self.tasks_given > 0:
            return round(min(100.0, (self.tasks_completed / self.tasks_given) * 100), 1)
        return 100.0

    def save(self, *args, **kwargs):
        # Auto-compute current attendance percentage if not set
        if self.student and not self.attendance_percentage:
            self.attendance_percentage = self.student.attendance_percentage

        # Calculate composite weighted score (out of 100)
        task_pct = self.task_completion_percentage

        # Weights:
        # Punctuality: 8%
        # Tutor Interaction: 8%
        # Classmate Interaction: 8%
        # Tendency to study: 10%
        # Task Completion: 12%
        # Presentation: 12%
        # Problems & Solutions: 16%
        # PPT/PDF Review: 10%
        # Communication: 6%
        # Taking Suggestions: 5%
        # Asking Doubts: 5%
        # Total: 100%

        if self.project_and_practical_task_given:
            w_score = (
                (float(self.punctuality_score or 0) * 0.08) +
                (float(self.tutor_interaction_score or 0) * 0.08) +
                (float(self.classmate_interaction_score or 0) * 0.08) +
                (float(self.tendency_to_study_score or 0) * 0.10) +
                (float(task_pct) * 0.12) +
                (float(self.presentation_score or 0) * 0.12) +
                (float(self.problem_solving_score or 0) * 0.16) +
                (float(self.ppt_evaluation_score or 0) * 0.10) +
                (float(self.communication_score or 0) * 0.06) +
                (float(self.suggestion_implementation_score or 0) * 0.05) +
                (float(self.doubt_clearing_score or 0) * 0.05)
            )
        else:
            # Exclude task-based score and double the weights of behavioral/interaction fields (sum to 100%)
            w_score = (
                (float(self.punctuality_score or 0) * 0.16) +
                (float(self.tutor_interaction_score or 0) * 0.16) +
                (float(self.classmate_interaction_score or 0) * 0.16) +
                (float(self.tendency_to_study_score or 0) * 0.20) +
                (float(self.communication_score or 0) * 0.12) +
                (float(self.suggestion_implementation_score or 0) * 0.10) +
                (float(self.doubt_clearing_score or 0) * 0.10)
            )
        self.total_score = round(w_score, 1)

        if self.total_score >= 90:
            self.grade = 'A+'
        elif self.total_score >= 80:
            self.grade = 'A'
        elif self.total_score >= 70:
            self.grade = 'B+'
        elif self.total_score >= 60:
            self.grade = 'B'
        elif self.total_score >= 50:
            self.grade = 'C'
        else:
            self.grade = 'NI'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.name} - {self.date}: {self.total_score}% ({self.grade})"


class StudentTask(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('LATE', 'Completed Late'),
        ('OVERDUE', 'Overdue'),
    ]

    PRIORITY_CHOICES = [
        ('NORMAL', 'Normal'),
        ('HIGH', 'High Priority'),
        ('URGENT', 'Urgent'),
    ]

    EVALUATION_STATUS_CHOICES = [
        ('UNEVALUATED', 'Pending Evaluation'),
        ('EXCELLENT', 'Exceeded Expectations (A/A+)'),
        ('PASSED', 'Accepted / Passed'),
        ('NEEDS_REVISION', 'Needs Revision'),
        ('FAILED', 'Unsatisfactory / Re-do'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='tasks')
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='student_tasks')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_student_tasks')
    daily_evaluation = models.ForeignKey(DailyEvaluation, on_delete=models.SET_NULL, null=True, blank=True, related_name='linked_tasks')
    
    title = models.CharField(max_length=255, help_text="Title or description of the task assigned")
    description = models.TextField(blank=True, help_text="Detailed task instructions or requirements")
    incharge_name = models.CharField(max_length=150, blank=True, null=True, help_text="Name of the person in charge (registered or unregistered)")
    problem_document = models.FileField(upload_to='student_tasks/problems/', blank=True, null=True, help_text="Upload problem statement (PDF, Word, etc.)")
    assigned_date = models.DateField(default=timezone.now, help_text="The date that specific task is given")
    due_date = models.DateField(null=True, blank=True, help_text="Expected completion deadline date")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when the student completed the task")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    evaluator_remarks = models.CharField(max_length=255, blank=True, help_text="Remarks or feedback from evaluator")
    
    # Task Evaluation Fields
    is_evaluated = models.BooleanField(default=False, help_text="Indicates whether this task has been evaluated")
    evaluation_status = models.CharField(max_length=30, choices=EVALUATION_STATUS_CHOICES, default='UNEVALUATED')
    score = models.FloatField(default=0.0, blank=True, null=True, help_text="Overall task evaluation score (0-100)")
    grade = models.CharField(max_length=10, blank=True, choices=DailyEvaluation.GRADE_CHOICES, help_text="Grade: A+, A, B+, B, C, NI")
    code_quality_score = models.FloatField(default=0.0, blank=True, null=True, help_text="Code quality & structure score (0-100)")
    problem_solving_score = models.FloatField(default=0.0, blank=True, null=True, help_text="Problem solving & logic score (0-100)")
    timeliness_score = models.FloatField(default=0.0, blank=True, null=True, help_text="Timeliness & promptness score (0-100)")
    presentation_score = models.FloatField(default=0.0, blank=True, null=True, help_text="Presentation & documentation score (0-100)")
    evaluator_feedback = models.TextField(blank=True, help_text="Comprehensive feedback and guidance from evaluator")
    strengths = models.TextField(blank=True, help_text="Strengths observed in student execution")
    areas_for_improvement = models.TextField(blank=True, help_text="Areas needing improvement or revision")
    submission_url = models.URLField(blank=True, help_text="GitHub repository, PR, or deliverable link")
    document_upload = models.FileField(upload_to='student_tasks/documents/', blank=True, null=True, help_text="Upload PPT/PDF/Word/Image (optional)")
    submission_notes = models.TextField(blank=True, help_text="Student submission description or explanation")
    evaluated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='evaluated_student_tasks')
    evaluated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-assigned_date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.student.name} ({self.get_status_display()})"

    @property
    def is_overdue(self):
        if self.status in ['PENDING', 'OVERDUE'] and self.due_date:
            return self.due_date < timezone.now().date()
        return False

    @property
    def computed_status(self):
        if self.status == 'COMPLETED':
            if self.due_date and self.completed_at and self.completed_at.date() > self.due_date:
                return 'LATE'
            return 'COMPLETED'
        elif self.status == 'LATE':
            return 'LATE'
        elif self.is_overdue:
            return 'OVERDUE'
        return self.status

    def calculate_total_score(self):
        # Weighted calculation: Code Quality (35%), Problem Solving (35%), Timeliness (15%), Presentation (15%)
        rubric_scores = [
            (float(self.code_quality_score or 0) * 0.35),
            (float(self.problem_solving_score or 0) * 0.35),
            (float(self.timeliness_score or 0) * 0.15),
            (float(self.presentation_score or 0) * 0.15),
        ]
        calculated = round(sum(rubric_scores), 1)
        if calculated > 0:
            self.score = calculated
        elif self.score is None:
            self.score = 0.0

        score_val = float(self.score or 0)
        if score_val >= 90:
            self.grade = 'A+'
        elif score_val >= 80:
            self.grade = 'A'
        elif score_val >= 70:
            self.grade = 'B+'
        elif score_val >= 60:
            self.grade = 'B'
        elif score_val >= 50:
            self.grade = 'C'
        elif score_val > 0:
            self.grade = 'NI'
        else:
            self.grade = ''
        return self.score

    def mark_as_completed(self, completion_dt=None, remarks=''):
        dt = completion_dt or timezone.now()
        self.completed_at = dt
        if self.due_date and dt.date() > self.due_date:
            self.status = 'LATE'
        else:
            self.status = 'COMPLETED'
        if remarks:
            self.evaluator_remarks = remarks
        self.save()


# ==============================================================================
# STUDENT PROJECT MANAGEMENT & EVALUATION
# ==============================================================================

class Project(models.Model):
    PROJECT_TYPE_CHOICES = [
        ('MAIN', 'Main / Capstone Project'),
        ('MINI', 'Mini Project'),
        ('ASSIGNMENT', 'Project Assignment'),
        ('PRACTICE', 'Practice Project'),
        ('CLIENT', 'Live / Client Project'),
    ]

    STATUS_CHOICES = [
        ('PLANNING', 'Planning & Design'),
        ('IN_PROGRESS', 'In Progress / Development'),
        ('UNDER_REVIEW', 'Under Evaluator Review'),
        ('COMPLETED', 'Completed'),
        ('ON_HOLD', 'On Hold / Needs Revision'),
    ]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='projects')
    students = models.ManyToManyField(Student, related_name='projects', help_text="Select one or more students for individual or team projects")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_projects')
    
    title = models.CharField(max_length=255, help_text="Project title (e.g. E-Commerce Multi-Vendor Platform)")
    project_type = models.CharField(max_length=30, choices=PROJECT_TYPE_CHOICES, default='MAIN')
    technologies = models.CharField(
        max_length=500,
        default='Python, Django, PostgreSQL, HTML5, CSS3, JavaScript',
        help_text="Technologies, frameworks, databases, and tools used (comma-separated)"
    )
    description = models.TextField(blank=True, help_text="Project objectives, features, system architecture & scope")
    
    # Progress & Timeline
    progress_percentage = models.IntegerField(default=0, help_text="Development progress from 0% to 100%")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='IN_PROGRESS')
    start_date = models.DateField(default=timezone.now, help_text="Project start / kick-off date")
    target_completion_date = models.DateField(null=True, blank=True, help_text="Target delivery / deadline date")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when project was finalized / submitted")
    
    # Links & Deliverables
    github_repo_url = models.URLField(blank=True, help_text="GitHub or GitLab source repository URL")
    live_demo_url = models.URLField(blank=True, help_text="Live deployed application URL (e.g. Render, Vercel, AWS)")
    documentation_url = models.URLField(blank=True, help_text="Project documentation, presentation slides, or design link")
    
    # Evaluation & Rubric Scores (0 - 100)
    presentation_score = models.FloatField(default=0.0, help_text="Presentation & demo delivery score (0-100)")
    code_quality_score = models.FloatField(default=0.0, help_text="Code quality, architecture & modularity score (0-100)")
    ui_ux_score = models.FloatField(default=0.0, help_text="UI/UX design, responsiveness & aesthetic score (0-100)")
    functionality_score = models.FloatField(default=0.0, help_text="Feature completeness & functionality score (0-100)")
    viva_score = models.FloatField(default=0.0, help_text="Viva, Q&A and doubt clearing score (0-100)")
    total_score = models.FloatField(default=0.0, help_text="Weighted overall evaluation score out of 100")
    grade = models.CharField(max_length=10, blank=True, help_text="Grade: A+, A, B+, B, C, NI")
    
    # Qualitative Feedback
    evaluator_feedback = models.TextField(blank=True, help_text="Comprehensive evaluator review & assessment comments")
    strengths = models.TextField(blank=True, help_text="Key strengths observed in the project")
    areas_to_improve = models.TextField(blank=True, help_text="Areas needing enhancement or refactoring")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.batch.name})"

    @property
    def tech_list(self):
        if not self.technologies:
            return []
        return [t.strip() for t in self.technologies.split(',') if t.strip()]

    @property
    def is_overdue(self):
        if self.status not in ['COMPLETED'] and self.target_completion_date:
            return self.target_completion_date < timezone.now().date()
        return False

    @property
    def is_evaluated(self):
        return self.total_score > 0 or bool(self.grade)

    def calculate_total_score(self):
        # Weighted score: Functionality (30%), Code Quality (25%), Presentation (20%), UI/UX (15%), Viva (10%)
        scores = [
            (float(self.functionality_score or 0) * 0.30),
            (float(self.code_quality_score or 0) * 0.25),
            (float(self.presentation_score or 0) * 0.20),
            (float(self.ui_ux_score or 0) * 0.15),
            (float(self.viva_score or 0) * 0.10),
        ]
        total = round(sum(scores), 1)
        self.total_score = total
        if total >= 90:
            self.grade = 'A+'
        elif total >= 80:
            self.grade = 'A'
        elif total >= 70:
            self.grade = 'B+'
        elif total >= 60:
            self.grade = 'B'
        elif total >= 50:
            self.grade = 'C'
        elif total > 0:
            self.grade = 'NI'
        else:
            self.grade = ''
        return total

    def save(self, *args, **kwargs):
        # If progress is 100% and status is not ON_HOLD or PLANNING, mark completed
        if self.progress_percentage >= 100 and self.status not in ['COMPLETED', 'ON_HOLD']:
            self.status = 'COMPLETED'
            if not self.completed_at:
                self.completed_at = timezone.now()
        elif self.status == 'COMPLETED':
            if not self.completed_at:
                self.completed_at = timezone.now()
        
        # Calculate grade if any score is filled
        if any([self.presentation_score, self.code_quality_score, self.ui_ux_score, self.functionality_score, self.viva_score]):
            self.calculate_total_score()

        super().save(*args, **kwargs)


class ProjectUpdate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='updates')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='project_updates')
    progress_percentage = models.IntegerField(default=0)
    status_at_update = models.CharField(max_length=30, blank=True)
    notes = models.TextField(help_text="Milestone summary, changes made, blockers or evaluator remarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.title} - {self.progress_percentage}% ({self.created_at.strftime('%b %d, %Y')})"


# ==============================================================================
# SYLLABUS & SCHEDULING SYSTEM
# ==============================================================================

class Syllabus(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    total_modules = models.PositiveIntegerField(default=1, help_text="Total number of modules needed for this syllabus")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_syllabi')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class SyllabusTask(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='tasks')
    order = models.PositiveIntegerField(default=1, help_text="Task order/number in the syllabus")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_assigner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='default_syllabus_tasks')
    default_assigner_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of unregistered assigner if applicable")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['syllabus', 'order']
        unique_together = ('syllabus', 'order')

    def __str__(self):
        return f"{self.syllabus.name} - Task {self.order}: {self.title}"

class BatchSyllabus(models.Model):
    batch = models.OneToOneField(Batch, on_delete=models.CASCADE, related_name='syllabus_assignment')
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='batch_assignments')
    start_date = models.DateField(default=timezone.now, help_text="The date this syllabus started for this batch")
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.batch.name} -> {self.syllabus.name}"

class BatchTaskSchedule(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='task_schedules')
    date = models.DateField()
    syllabus_task = models.ForeignKey(SyllabusTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedules')
    custom_task_title = models.CharField(max_length=255, blank=True, help_text="Used if scheduled outside syllabus")
    custom_task_description = models.TextField(blank=True)
    is_rescheduled = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed')], default='PENDING')
    incharge = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='batch_task_schedules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['batch', 'date']
        unique_together = ('batch', 'date')

    def __str__(self):
        task_name = self.syllabus_task.title if self.syllabus_task else self.custom_task_title
        return f"{self.batch.name} - {self.date}: {task_name}"

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Student)
def student_post_save(sender, instance, created, **kwargs):
    if created and instance.batch:
        try:
            from .services import sync_student_tasks_for_batch
            sync_student_tasks_for_batch(instance.batch)
        except Exception:
            pass

