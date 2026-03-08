from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import EAFCPlayer, League, Club


@login_required
def player_search(request):
    qs = EAFCPlayer.objects.select_related('club', 'club__league')
    q = request.GET.get('q', '').strip()
    position = request.GET.get('position', '')
    league_id = request.GET.get('league', '')
    min_ovr = request.GET.get('min_ovr', 75)
    max_ovr = request.GET.get('max_ovr', 99)

    if q:
        qs = qs.filter(name__icontains=q)
    if position:
        qs = qs.filter(position=position)
    if league_id:
        qs = qs.filter(club__league_id=league_id)
    try:
        qs = qs.filter(overall__gte=int(min_ovr), overall__lte=int(max_ovr))
    except (ValueError, TypeError):
        pass

    qs = qs.order_by('-overall')[:60]
    leagues = League.objects.order_by('name')

    return render(request, 'players/search.html', {
        'players': qs,
        'leagues': leagues,
        'positions': EAFCPlayer.POSITION_CHOICES,
        'q': q,
        'selected_position': position,
        'selected_league': league_id,
        'min_ovr': min_ovr,
        'max_ovr': max_ovr,
    })


@login_required
def player_detail(request, pk):
    player = get_object_or_404(
        EAFCPlayer.objects.select_related('club', 'club__league'), pk=pk
    )
    return render(request, 'players/detail.html', {'player': player})


def player_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    players = EAFCPlayer.objects.filter(name__icontains=q).select_related('club')[:15]
    return JsonResponse({'results': [
        {'id': p.pk, 'name': p.name, 'overall': p.overall,
         'position': p.position, 'club': p.club.name if p.club else ''}
        for p in players
    ]})
