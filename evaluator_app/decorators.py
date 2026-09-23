from functools import wraps
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import Batch, Location, Student, UserProfile

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.is_admin:
            messages.error(request, "Access denied: Admin privileges required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def evaluator_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def get_user_batches(user):
    """Returns queryset of batches accessible to the user based on role and location."""
    if not user.is_authenticated:
        return Batch.objects.none()
    
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.is_admin:
        return Batch.objects.all().select_related('location', 'created_by')
    
    assigned_locations = profile.assigned_locations.all()
    return Batch.objects.filter(location__in=assigned_locations).select_related('location', 'created_by')


def get_user_students(user):
    """Returns queryset of students accessible to the user."""
    accessible_batches = get_user_batches(user)
    return Student.objects.filter(batch__in=accessible_batches).select_related('batch', 'batch__location')


def can_user_access_batch(user, batch):
    """Checks if the user has permission to access a specific batch."""
    if not user.is_authenticated:
        return False
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.can_access_batch(batch)


def can_user_access_location(user, location):
    """Checks if the user has permission to access a specific location."""
    if not user.is_authenticated:
        return False
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.can_access_location(location)
