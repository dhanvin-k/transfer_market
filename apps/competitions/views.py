from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Competition, CompetitionBudget


def home(request):
    if not request.user.is_authenticated:
        return redirect('account_login')
    my_comps = list(Competition.objects.filter(
        participants=request.user
    ).order_by('-created_at')) + list(Competition.objects.filter(
        created_by=request.user
    ).exclude(participants=request.user).order_by('-created_at'))
    # dedupe preserving order
    seen = set()
    competitions = []
    for c in my_comps:
        if c.pk not in seen:
            seen.add(c.pk)
            competitions.append(c)
    return render(request, 'competitions/home.html', {'competitions': competitions})


@login_required
def competition_detail(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    budget = CompetitionBudget.objects.filter(competition=comp, user=request.user).first()
    from apps.squads.models import Squad
    my_squad = Squad.objects.filter(competition=comp, manager=request.user).first()
    return render(request, 'competitions/detail.html', {
        'competition': comp,
        'budget': budget,
        'my_squad': my_squad,
    })


@login_required
def create_competition(request):
    if request.method == 'POST':
        comp = Competition.objects.create(
            name=request.POST['name'],
            created_by=request.user,
            format=request.POST.get('format', 'league'),
            starting_budget=int(request.POST.get('starting_budget', 100_000_000)),
            min_player_rating=int(request.POST.get('min_player_rating', 75)),
            squad_size=int(request.POST.get('squad_size', 18)),
            min_bid_increment=int(request.POST.get('min_bid_increment', 500_000)),
            transfer_window_seconds=int(request.POST.get('transfer_window_seconds', 120)),
        )
        comp.participants.add(request.user)
        CompetitionBudget.objects.create(
            competition=comp, user=request.user, remaining_budget=comp.starting_budget
        )
        return redirect('competition_detail', competition_id=comp.pk)
    return render(request, 'competitions/create.html')


@login_required
def join_competition(request):
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        try:
            comp = Competition.objects.get(invite_code=code)
        except Competition.DoesNotExist:
            messages.error(request, f'No competition found with code "{code}".')
            return render(request, 'competitions/join.html')
        comp.participants.add(request.user)
        CompetitionBudget.objects.get_or_create(
            competition=comp, user=request.user,
            defaults={'remaining_budget': comp.starting_budget}
        )
        return redirect('competition_detail', competition_id=comp.pk)
    return render(request, 'competitions/join.html')


@login_required
@require_POST
def delete_competition(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    comp.delete()
    messages.success(request, f'"{comp.name}" has been deleted.')
    return redirect('home')


@login_required
@require_POST  
def leave_competition(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    if request.user == comp.created_by:
        messages.error(request, "You can't leave a competition you created. Delete it instead.")
        return redirect('competition_detail', competition_id=competition_id)
    comp.participants.remove(request.user)
    return redirect('home')
