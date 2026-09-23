from django.utils import timezone
from .models import Location, UserProfile

def evaluator_context(request):
    context = {
        'current_year': timezone.now().year,
        'today_date': timezone.now().date(),
        'is_admin_user': False,
        'is_evaluator_user': False,
        'user_profile': None,
        'accessible_locations': [],
    }

    if request.user.is_authenticated:
        # Get or create UserProfile if missing
        profile, created = UserProfile.objects.get_or_create(
            user=request.user,
            defaults={
                'role': 'ADMIN' if request.user.is_superuser else 'EVALUATOR',
                'designation': 'Administrator' if request.user.is_superuser else 'Evaluator'
            }
        )
        context['user_profile'] = profile
        context['is_admin_user'] = profile.is_admin
        context['is_evaluator_user'] = profile.is_evaluator
        context['accessible_locations'] = profile.get_accessible_locations()

    return context
