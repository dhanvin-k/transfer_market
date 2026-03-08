from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.competitions.models import Competition
from .models import Squad, SquadSlot


@login_required
def squad_view(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    request.session['active_competition_id'] = competition_id
    squads = (Squad.objects.filter(competition=comp)
              .select_related('manager')
              .prefetch_related('squadslot_set__player__club'))

    my_squad = squads.filter(manager=request.user).first()
    other_squads = squads.exclude(manager=request.user)

    return render(request, 'squads/view.html', {
        'competition': comp,
        'my_squad': my_squad,
        'other_squads': other_squads,
    })
