from django import forms
from django.contrib.auth.models import User
from .models import (
    Batch, Student, DailyEvaluation, Attendance, Location, UserProfile,
    StudentTask, Project, ProjectUpdate, generate_batch_student_roll_number,
    BatchGroup
)

from django.utils import timezone

WEEKDAY_CHOICES = [
    ('Monday', 'Monday'),
    ('Tuesday', 'Tuesday'),
    ('Wednesday', 'Wednesday'),
    ('Thursday', 'Thursday'),
    ('Friday', 'Friday'),
    ('Saturday', 'Saturday'),
    ('Sunday', 'Sunday'),
]

class BatchForm(forms.ModelForm):
    selected_days = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'day-checkbox'}),
        required=True,
        help_text="Select one or more days when classes are conducted"
    )

    class Meta:
        model = Batch
        fields = [
            'name', 'code', 'location', 'schedule_type', 'selected_days',
            'start_time', 'end_time', 'start_date', 'end_date', 'status', 'description'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Full Stack Python - Batch Alpha'}),
            'code': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. PY-CLT-01'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'schedule_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_schedule_type'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Batch objectives, syllabus details, or special notes...'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.is_admin = False
        
        if user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            self.is_admin = profile.is_admin
            if not profile.is_admin:
                self.fields['location'].queryset = profile.assigned_locations.filter(is_active=True)
        
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        
        if not self.instance.pk:
            # New batch creation
            if not self.is_admin:
                self.fields['start_date'].widget.attrs['min'] = today_str
            self.fields['start_date'].initial = today_str
        else:
            # Editing an existing batch
            if not self.is_admin:
                self.fields['start_date'].disabled = True

        # Populate initial selected_days from model instance if editing
        if self.instance and self.instance.pk and self.instance.class_days:
            self.fields['selected_days'].initial = self.instance.days_list
        elif not self.is_bound:
            # Default to weekdays
            self.fields['selected_days'].initial = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        today = timezone.now().date()
        
        if self.is_admin:
            # Admins can select any date (past or future)
            return start_date
            
        # Enforce that starting date cannot be a past date (on new batch creation or when modified to past)
        if not self.instance.pk or (self.instance.pk and self.instance.start_date != start_date):
            if start_date and start_date < today:
                raise forms.ValidationError("Starting date cannot be in the past. Please select today or an upcoming date.")
        return start_date

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        days = cleaned_data.get('selected_days')

        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', "Ending time must be later than starting time.")

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', "End date cannot be earlier than start date.")

        if not days:
            self.add_error('selected_days', "Please select at least one day for the class schedule.")

        return cleaned_data

    def save(self, commit=True):
        batch = super().save(commit=False)
        days = self.cleaned_data.get('selected_days', [])
        batch.class_days = ", ".join(days)
        if commit:
            batch.save()
        return batch


class BatchGroupForm(forms.ModelForm):
    class Meta:
        model = BatchGroup
        fields = ['name', 'batches']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Combined Thursday Class'}),
            'batches': forms.CheckboxSelectMultiple(attrs={'class': 'batch-checkbox-list'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.is_admin:
                self.fields['batches'].queryset = Batch.objects.filter(
                    location__in=profile.assigned_locations.filter(is_active=True),
                    status='ACTIVE'
                )
            else:
                self.fields['batches'].queryset = Batch.objects.filter(status='ACTIVE')


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['batch', 'roll_number', 'name', 'email', 'phone', 'student_class', 'academic_year', 'join_date', 'status', 'payment_status', 'notes']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'roll_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. STU-2026-001'}),
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'student@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+91 9876543210'}),
            'student_class': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Class 10 / CS / Bio'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 2026-2027'}),
            'join_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payment_status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Academic background, strengths, special interests...'}),
        }

    def __init__(self, *args, user=None, initial_batch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_batch = initial_batch
        if user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.is_admin:
                self.fields['batch'].queryset = Batch.objects.filter(location__in=profile.assigned_locations.all())
        if initial_batch:
            self.fields['batch'].initial = initial_batch
            self.fields['batch'].widget = forms.HiddenInput()
            self.fields['batch'].required = False
            if initial_batch.start_date:
                self.fields['join_date'].initial = initial_batch.start_date

        self.fields['join_date'].required = False

        # Target batch determination
        target_batch = initial_batch or getattr(self.instance, 'batch', None)

        # Make roll_number optional on input so it defaults automatically if omitted
        self.fields['roll_number'].required = False

        # Auto-generate default unique roll number based on batch for new students
        if not self.instance.pk:
            if target_batch:
                self.initial['roll_number'] = generate_batch_student_roll_number(target_batch)
            elif not self.initial.get('roll_number'):
                # If there's an accessible batch, use the first one for initial preview
                first_batch = self.fields['batch'].queryset.first() if hasattr(self.fields['batch'], 'queryset') and self.fields['batch'].queryset.exists() else None
                if first_batch:
                    self.initial['roll_number'] = generate_batch_student_roll_number(first_batch)

        # Enforce that enrollment date cannot be earlier than the batch start date
        if target_batch and target_batch.start_date:
            min_date_str = target_batch.start_date.strftime('%Y-%m-%d')
            self.fields['join_date'].widget.attrs['min'] = min_date_str
            # Default to batch start date if not provided (e.g. for new students)
            if not self.initial.get('join_date'):
                self.initial['join_date'] = target_batch.start_date
            else:
                initial_val = self.initial.get('join_date')
                if hasattr(initial_val, 'date'):
                    initial_val = initial_val.date()
                if initial_val < target_batch.start_date:
                    self.initial['join_date'] = target_batch.start_date

    def clean_join_date(self):
        join_date = self.cleaned_data.get('join_date')
        batch = self.cleaned_data.get('batch') or self.initial_batch
        
        # If no date was provided, default to batch start date or today
        if not join_date:
            if batch and batch.start_date:
                join_date = batch.start_date.date() if hasattr(batch.start_date, 'hour') else batch.start_date
            else:
                join_date = timezone.now().date()
        return join_date

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if not batch and self.initial_batch:
            return self.initial_batch
        return batch

    def clean_roll_number(self):
        roll = self.cleaned_data.get('roll_number', '').strip()
        batch = self.cleaned_data.get('batch') or self.initial_batch or getattr(self.instance, 'batch', None)

        # If blank, auto-generate default based on batch
        if not roll:
            if batch:
                roll = generate_batch_student_roll_number(batch)
            else:
                roll = f"STU-{timezone.now().strftime('%y%m%d%H%M')}"

        # Ensure uniqueness across the student database
        qs = Student.objects.filter(roll_number__iexact=roll)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Roll Number '{roll}' is already in use by another student. Please enter a unique roll number.")

        return roll

    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch') or self.initial_batch or getattr(self.instance, 'batch', None)
        join_date = cleaned_data.get('join_date')
        if batch and batch.start_date and join_date:
            j_date = join_date.date() if hasattr(join_date, 'hour') else join_date
            b_date = batch.start_date.date() if hasattr(batch.start_date, 'hour') else batch.start_date
            if j_date < b_date:
                self.add_error(
                    'join_date',
                    f"Enrollment Date cannot be earlier than the Batch Start Date ({b_date.strftime('%d %b, %Y')})."
                )
        return cleaned_data


class DailyEvaluationForm(forms.ModelForm):
    class Meta:
        model = DailyEvaluation
        fields = [
            'date', 'topic', 'project_and_practical_task_given',
            # Behavioral & Daily Engagement
            'punctuality_score', 'tutor_interaction_score',
            'classmate_interaction_score', 'tendency_to_study_score',
            'tasks_given', 'tasks_completed',
            # Project & Presentation
            'presentation_score', 'problem_solving_score',
            'ppt_evaluation_score', 'ppt_slide_count', 'ppt_has_images', 'ppt_explanation_notes', 'document_upload',
            # Communication & Mentorship
            'communication_score', 'suggestion_implementation_score', 'doubt_clearing_score',
            # Remarks & Profile Insights
            'strongest_areas', 'areas_for_improvement', 'interested_areas', 'general_remarks'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'topic': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Django Full Stack Architecture & Project Presentation'}),
            'project_and_practical_task_given': forms.CheckboxInput(attrs={'class': 'form-checkbox', 'id': 'id_project_and_practical_task_given'}),
            
            # Scores
            'punctuality_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'tutor_interaction_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'classmate_interaction_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'tendency_to_study_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            
            # Tasks
            'tasks_given': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 50}),
            'tasks_completed': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 50}),
            
            # Project & Presentation
            'presentation_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'problem_solving_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'ppt_evaluation_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'ppt_slide_count': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'placeholder': 'Slide count'}),
            'ppt_has_images': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'ppt_explanation_notes': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Clean flowcharts, screenshots & explanations'}),
            'document_upload': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            
            # Communication
            'communication_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'suggestion_implementation_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'doubt_clearing_score': forms.NumberInput(attrs={'type': 'range', 'class': 'form-range score-input', 'min': 0, 'max': 100, 'step': '1'}),
            
            # Remarks
            'strongest_areas': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'e.g. Quick problem-solving logic, strong framework understanding, clean coding style...'}),
            'areas_for_improvement': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'e.g. Needs to speak louder during presentation, practice database index optimization...'}),
            'interested_areas': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'e.g. Backend API Development, DevOps CI/CD, UI/UX Design, Data Engineering...'}),
            'general_remarks': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'General mentor advice and feedback for the student...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['date'].widget.attrs['readonly'] = True
            self.fields['date'].help_text = "Evaluation date is fixed and cannot be changed once saved."



class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['date', 'status', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Optional note...'}),
        }


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'code', 'address', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Kozhikode'}),
            'code': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. CLT'}),
            'address': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Branch address, Building, Street'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Description...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }


class EvaluatorAssignmentForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['assigned_locations', 'designation', 'phone', 'role']
        widgets = {
            'assigned_locations': forms.CheckboxSelectMultiple(attrs={'class': 'checkbox-group'}),
            'designation': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Senior Technical Evaluator'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+91 9876543210'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }


from .models import StudentTask

class StudentTaskForm(forms.ModelForm):
    class Meta:
        model = StudentTask
        fields = [
            'student', 'title', 'description', 'assigned_date',
            'due_date', 'status', 'completed_at', 'priority', 'evaluator_remarks'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Build User Auth System with Django Sessions'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Detailed task requirements, deliverables, criteria...'}),
            'assigned_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'completed_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'evaluator_remarks': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Optional feedback on task execution...'}),
        }

    def __init__(self, *args, batch=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        if not self.instance.pk:
            self.fields['assigned_date'].initial = today_str
        
        if batch:
            self.fields['student'].queryset = batch.students.filter(status='ACTIVE')
        elif user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.is_admin:
                accessible_batches = Batch.objects.filter(location__in=profile.assigned_locations.all())
                self.fields['student'].queryset = Student.objects.filter(batch__in=accessible_batches, status='ACTIVE')


class QuickTaskAssignForm(forms.Form):
    ASSIGN_TARGET_CHOICES = [
        ('STUDENT', 'Specific Student'),
        ('BATCH', 'Entire Batch (All Active Students)'),
    ]

    target_type = forms.ChoiceField(choices=ASSIGN_TARGET_CHOICES, initial='STUDENT', widget=forms.RadioSelect)
    student = forms.ModelChoiceField(queryset=Student.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    batch = forms.ModelChoiceField(queryset=Batch.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    title = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Task Title (e.g. Django REST API CRUD)'}))
    description = forms.CharField(
        label='Task Description',
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Enter task description, requirements, instructions, or specific criteria for the student...'
        }),
        required=False
    )
    assigned_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}), initial=timezone.now)
    due_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}), required=False)
    priority = forms.ChoiceField(choices=StudentTask.PRIORITY_CHOICES, initial='NORMAL', widget=forms.Select(attrs={'class': 'form-select'}))
    evaluator_remarks = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Optional remarks or context...'}))
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        self.fields['assigned_date'].initial = today_str
        if user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.is_admin:
                self.fields['batch'].queryset = Batch.objects.all()
                self.fields['student'].queryset = Student.objects.filter(status='ACTIVE')
            else:
                accessible_batches = Batch.objects.filter(location__in=profile.assigned_locations.all())
                self.fields['batch'].queryset = accessible_batches
                self.fields['student'].queryset = Student.objects.filter(batch__in=accessible_batches, status='ACTIVE')


# ==============================================================================
# STUDENT PROJECT FORMS
# ==============================================================================

class ProjectForm(forms.ModelForm):
    assign_to_whole_batch = forms.BooleanField(
        required=False, 
        label="Assign to entire batch",
        help_text="If checked, this project will be assigned to all active students in the selected batch."
    )
    class Meta:
        model = Project
        fields = [
            'batch', 'students', 'title', 'project_type', 'technologies',
            'description', 'status', 'progress_percentage', 'start_date',
            'target_completion_date', 'github_repo_url', 'live_demo_url', 'documentation_url'
        ]
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select', 'id': 'id_project_batch', 'required': False}),
            'students': forms.SelectMultiple(attrs={'class': 'form-select', 'id': 'id_project_students', 'size': '5'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. AI-Powered Medical Diagnostic Portal'}),
            'project_type': forms.Select(attrs={'class': 'form-select'}),
            'technologies': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Python, Django, PostgreSQL, TailwindCSS, Chart.js, Docker, REST API'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Explain project purpose, key features, database design, architecture and goals...'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'progress_percentage': forms.NumberInput(attrs={
                'class': 'form-input',
                'type': 'number',
                'min': '0',
                'max': '100',
                'step': '5',
                'placeholder': '0 - 100%'
            }),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'github_repo_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://github.com/username/project-repo'}),
            'live_demo_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://myproject.vercel.app'}),
            'documentation_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://notion.so/docs or Google Drive Link'}),
        }
        help_texts = {
            'students': 'Hold Ctrl (or Cmd) to select multiple students for a team project.',
            'technologies': 'Enter technologies separated by commas.',
        }

    def __init__(self, *args, user=None, initial_batch=None, initial_student=None, **kwargs):
        super().__init__(*args, **kwargs)
        today_str = timezone.now().date().strftime('%Y-%m-%d')
        if not self.instance.pk:
            self.fields['start_date'].initial = today_str
            self.fields['batch'].required = False

        accessible_batches = Batch.objects.none()
        if user:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.is_admin:
                accessible_batches = Batch.objects.all()
            else:
                accessible_batches = Batch.objects.filter(location__in=profile.assigned_locations.all())
        elif self.instance.pk and self.instance.batch:
            accessible_batches = Batch.objects.filter(id=self.instance.batch.id)
        elif initial_batch:
            accessible_batches = Batch.objects.filter(id=initial_batch.id)

        self.fields['batch'].queryset = accessible_batches

        # Determine target batch to strictly scope students
        target_batch = None
        if self.data and 'batch' in self.data:
            try:
                target_batch_id = int(self.data.get('batch'))
                target_batch = accessible_batches.filter(id=target_batch_id).first()
            except (ValueError, TypeError):
                target_batch = None
        elif self.instance.pk and self.instance.batch:
            target_batch = self.instance.batch
        elif initial_batch:
            target_batch = initial_batch
        elif initial_student and initial_student.batch:
            target_batch = initial_student.batch
        elif accessible_batches.exists():
            target_batch = accessible_batches.first()

        if target_batch:
            self.fields['batch'].initial = target_batch.id
            self.fields['students'].queryset = target_batch.students.filter(status='ACTIVE')
        else:
            self.fields['students'].queryset = Student.objects.none()

        if initial_student:
            self.fields['students'].initial = [initial_student.id]

        self.fields['students'].required = False

    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        students = cleaned_data.get('students')
        assign_to_whole_batch = cleaned_data.get('assign_to_whole_batch')

        if assign_to_whole_batch and batch:
            cleaned_data['students'] = batch.students.filter(status='ACTIVE')
            students = cleaned_data['students']
            
        if not assign_to_whole_batch and not students:
            self.add_error('students', "You must select at least one student or check 'Assign to entire batch'.")

        if batch and students and not assign_to_whole_batch:
            for s in students:
                if s.batch_id != batch.id:
                    self.add_error('students', f"Student '{s.name}' ({s.roll_number}) does not belong to selected batch '{batch.name}'. Only students in the selected batch can be assigned.")
        return cleaned_data


class ProjectProgressUpdateForm(forms.ModelForm):
    milestone_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Add update notes (e.g. Completed JWT authentication and database schemas; started UI layout)...'
        }),
        help_text="Provide notes about current progress, accomplishments or blockers."
    )

    class Meta:
        model = Project
        fields = ['progress_percentage', 'status', 'github_repo_url', 'live_demo_url', 'documentation_url']
        widgets = {
            'progress_percentage': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 100, 'step': 5}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'github_repo_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://github.com/...'}),
            'live_demo_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://...'}),
            'documentation_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://...'}),
        }


class ProjectEvaluationForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'presentation_score', 'code_quality_score', 'ui_ux_score',
            'functionality_score', 'viva_score',
            'evaluator_feedback', 'strengths', 'areas_to_improve'
        ]
        widgets = {
            'presentation_score': forms.NumberInput(attrs={'class': 'form-input score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'code_quality_score': forms.NumberInput(attrs={'class': 'form-input score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'ui_ux_score': forms.NumberInput(attrs={'class': 'form-input score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'functionality_score': forms.NumberInput(attrs={'class': 'form-input score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'viva_score': forms.NumberInput(attrs={'class': 'form-input score-input', 'min': 0, 'max': 100, 'step': '1'}),
            'evaluator_feedback': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Comprehensive overall evaluator review & assessment notes...'
            }),
            'strengths': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Key strengths observed (e.g. Robust model relationships, responsive modern UI, clear presentation)...'
            }),
            'areas_to_improve': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Areas needing improvement (e.g. Add unit tests, enhance exception handling, refine CSS styles)...'
            }),
        }


# ==============================================================================
# STUDENT TASK EVALUATION FORM
# ==============================================================================

class TaskEvaluationForm(forms.ModelForm):
    class Meta:
        model = StudentTask
        fields = [
            'code_quality_score', 'problem_solving_score', 'timeliness_score',
            'presentation_score', 'score', 'evaluation_status', 'status',
            'submission_url', 'document_upload', 'evaluator_feedback', 'strengths', 'areas_for_improvement'
        ]
        widgets = {
            'code_quality_score': forms.NumberInput(attrs={
                'class': 'form-input score-input',
                'min': 0, 'max': 100, 'step': '1',
                'placeholder': '0 - 100'
            }),
            'problem_solving_score': forms.NumberInput(attrs={
                'class': 'form-input score-input',
                'min': 0, 'max': 100, 'step': '1',
                'placeholder': '0 - 100'
            }),
            'timeliness_score': forms.NumberInput(attrs={
                'class': 'form-input score-input',
                'min': 0, 'max': 100, 'step': '1',
                'placeholder': '0 - 100'
            }),
            'presentation_score': forms.NumberInput(attrs={
                'class': 'form-input score-input',
                'min': 0, 'max': 100, 'step': '1',
                'placeholder': '0 - 100'
            }),
            'score': forms.NumberInput(attrs={
                'class': 'form-input font-bold',
                'min': 0, 'max': 100, 'step': '0.1',
                'placeholder': 'Overall Score %'
            }),
            'evaluation_status': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'submission_url': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://github.com/... or PR link'
            }),
            'document_upload': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'evaluator_feedback': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Feedback, code review observations, test case validation, and mentor advice...'
            }),
            'strengths': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'e.g. Well-structured functions, good documentation, adhered to clean code...'
            }),
            'areas_for_improvement': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'e.g. Edge case handling, SQL query optimization, UI styling consistency...'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        score_fields = ['code_quality_score', 'problem_solving_score', 'timeliness_score', 'presentation_score', 'score']
        for field in score_fields:
            val = cleaned_data.get(field)
            if val is not None and (val < 0 or val > 100):
                self.add_error(field, f"{field.replace('_', ' ').title()} must be between 0 and 100.")
        return cleaned_data


