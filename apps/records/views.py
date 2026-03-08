from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.competitions.models import Competition
from .models import PlayerRecord, H2HRecord


@login_required
def leaderboard(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    participants = list(comp.participants.all())
    records = []
    for user in participants:
        rec, _ = PlayerRecord.objects.get_or_create(user=user)
        records.append(rec)
    records.sort(key=lambda r: (-r.points, -r.goal_difference, -r.goals_for))

    # H2H matrix
    h2h = {}
    for u in participants:
        h2h[u.pk] = {}
        for opp in participants:
            if u == opp:
                continue
            try:
                rec = H2HRecord.objects.get(player=u, opponent=opp)
                h2h[u.pk][opp.pk] = rec
            except H2HRecord.DoesNotExist:
                h2h[u.pk][opp.pk] = None

    return render(request, 'records/leaderboard.html', {
        'competition': comp,
        'records': records,
        'participants': participants,
        'h2h': h2h,
    })
