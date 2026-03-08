from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
import itertools, random

from apps.competitions.models import Competition
from .models import Fixture, Result


@login_required
def fixture_list(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    fixtures = (Fixture.objects.filter(competition=comp)
                .select_related('home', 'away', 'result')
                .order_by('round_number', 'leg'))
    rounds = {}
    for f in fixtures:
        rounds.setdefault(f.round_number, []).append(f)
    participants = list(comp.participants.all())
    return render(request, 'fixtures/list.html', {
        'competition': comp,
        'rounds': rounds,
        'participants': participants,
    })


@login_required
@require_POST
def generate_fixtures(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    if comp.fixtures.exists():
        return JsonResponse({'error': 'Fixtures already generated.'}, status=400)

    participants = list(comp.participants.all())
    if len(participants) < 2:
        return JsonResponse({'error': 'Need at least 2 participants.'}, status=400)

    random.shuffle(participants)
    fixtures_to_create = []

    if comp.format in ('league', 'round_robin'):
        # Round-robin: everyone plays everyone
        rounds = _round_robin(participants)
        for rnum, pairings in enumerate(rounds, 1):
            for home, away in pairings:
                for leg in range(1, comp.legs_per_fixture + 1):
                    fixtures_to_create.append(Fixture(
                        competition=comp, home=home, away=away,
                        round_number=rnum, leg=leg, stage='league'
                    ))
    elif comp.format == 'knockout':
        # Single-elimination bracket
        _generate_knockout(comp, participants, fixtures_to_create)

    Fixture.objects.bulk_create(fixtures_to_create)
    return JsonResponse({'ok': True, 'count': len(fixtures_to_create)})


@login_required
@require_POST
def submit_result(request, fixture_id):
    fixture = get_object_or_404(Fixture, pk=fixture_id)
    comp = fixture.competition
    if request.user not in [fixture.home, fixture.away, comp.created_by]:
        return JsonResponse({'error': 'Not authorised.'}, status=403)

    try:
        hs = int(request.POST['home_score'])
        as_ = int(request.POST['away_score'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Invalid scores.'}, status=400)

    if fixture.is_completed:
        return JsonResponse({'error': 'Result already entered.'}, status=400)

    Result.objects.create(fixture=fixture, home_score=hs, away_score=as_, entered_by=request.user)
    return JsonResponse({'ok': True})


def _round_robin(players):
    """Return list-of-rounds using circle method."""
    n = len(players)
    if n % 2:
        players.append(None)  # bye
        n += 1
    rounds = []
    fixed = players[0]
    rotating = players[1:]
    for _ in range(n - 1):
        round_pairs = []
        circle = [fixed] + rotating
        for i in range(n // 2):
            h, a = circle[i], circle[n - 1 - i]
            if h is not None and a is not None:
                round_pairs.append((h, a))
        rounds.append(round_pairs)
        rotating = [rotating[-1]] + rotating[:-1]
    return rounds


def _generate_knockout(comp, participants, out):
    size = 1
    while size < len(participants):
        size *= 2
    byes = size - len(participants)
    seeded = participants + [None] * byes
    for i in range(0, size, 2):
        h, a = seeded[i], seeded[i + 1]
        if h and a:
            out.append(Fixture(competition=comp, home=h, away=a,
                               round_number=1, stage='r16'))
