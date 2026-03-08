from .models import Competition


def active_competition(request):
    """
    Injects `competition` and `user_competitions` into every template context.
    - `competition`: the last competition the user navigated to (stored in session)
    - `user_competitions`: all competitions the user is in (for a switcher)
    """
    if not request.user.is_authenticated:
        return {}

    # Store competition_id in session whenever a competition page is visited
    comp_id = request.session.get('active_competition_id')
    competition = None

    if comp_id:
        try:
            competition = Competition.objects.get(
                pk=comp_id,
                participants=request.user
            )
        except Competition.DoesNotExist:
            # Stale session value - clear it
            request.session.pop('active_competition_id', None)

    # Also expose all user's competitions for a switcher dropdown
    user_competitions = Competition.objects.filter(
        participants=request.user
    ).order_by('-created_at')[:8]

    return {
        'competition': competition,
        'user_competitions': user_competitions,
    }
