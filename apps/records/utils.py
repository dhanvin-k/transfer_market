from .models import PlayerRecord, H2HRecord


def update_records_from_result(result):
    """Called after every Result.save() to keep denormalized records in sync."""
    home = result.fixture.home
    away = result.fixture.away
    hs = result.home_score
    as_ = result.away_score

    # ── All-time records ──────────────────────────────────
    home_rec, _ = PlayerRecord.objects.get_or_create(user=home)
    away_rec, _ = PlayerRecord.objects.get_or_create(user=away)

    home_rec.played += 1
    away_rec.played += 1
    home_rec.goals_for += hs
    home_rec.goals_against += as_
    away_rec.goals_for += as_
    away_rec.goals_against += hs

    if hs > as_:
        home_rec.wins += 1
        away_rec.losses += 1
    elif hs < as_:
        away_rec.wins += 1
        home_rec.losses += 1
    else:
        home_rec.draws += 1
        away_rec.draws += 1

    home_rec.save()
    away_rec.save()

    # ── H2H records ───────────────────────────────────────
    h2h_home, _ = H2HRecord.objects.get_or_create(player=home, opponent=away)
    h2h_away, _ = H2HRecord.objects.get_or_create(player=away, opponent=home)

    h2h_home.goals_for += hs
    h2h_home.goals_against += as_
    h2h_away.goals_for += as_
    h2h_away.goals_against += hs

    if hs > as_:
        h2h_home.wins += 1
        h2h_away.losses += 1
    elif hs < as_:
        h2h_away.wins += 1
        h2h_home.losses += 1
    else:
        h2h_home.draws += 1
        h2h_away.draws += 1

    h2h_home.save()
    h2h_away.save()
