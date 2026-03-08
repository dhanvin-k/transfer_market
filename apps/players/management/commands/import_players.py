"""
Management command to import EA FC players from a Kaggle CSV.

Supports two CSV formats:
  - sofifa / nyagami format  (sofifa_id, short_name, club_name, physic, ...)
  - flynn28 EAFC26 format    (ID, Name, Team, League, Nation, OVR, PAC, ...)

Usage:
    python manage.py import_players --file path/to/EAFC26-Men.csv
    python manage.py import_players --file path/to/EAFC26.csv --min-overall 75
    python manage.py import_players --file path/to/EAFC26-Men.csv --wipe
    python manage.py import_players --file path/to/EAFC26-Men.csv --gender M
"""

import csv
import os
import re
from django.core.management.base import BaseCommand, CommandError
from apps.players.models import League, Club, EAFCPlayer


# ── Column aliases ────────────────────────────────────────────────────────────
# Maps every column name variant we've seen → canonical internal key.
# Keys are lowercased + stripped before lookup.
COLUMN_ALIASES = {
    # ── Identity ──────────────────────────────────────────
    'id':                           'ea_id',
    'sofifa_id':                    'ea_id',
    'player_id':                    'ea_id',

    'name':                         'name',
    'short_name':                   'name',
    'player_name':                  'name',

    'long_name':                    'full_name',

    'gender':                       'gender',

    # ── Ratings ───────────────────────────────────────────
    'ovr':                          'overall',
    'overall':                      'overall',

    # ── Club / League / Nation ────────────────────────────
    'team':                         'club_name',
    'club':                         'club_name',
    'club_name':                    'club_name',

    'league':                       'league_name',
    'league_name':                  'league_name',
    'league_id':                    'league_id',

    'nation':                       'nationality',
    'nationality_name':             'nationality',
    'nationality':                  'nationality',
    'nation_id':                    'nationality_id',
    'nationality_id':               'nationality_id',

    # ── Bio ───────────────────────────────────────────────
    'age':                          'age',
    'height':                       'height_cm',
    'height_cm':                    'height_cm',
    'weight':                       'weight_kg',
    'weight_kg':                    'weight_kg',

    'url':                          'photo_url',
    'player_face_url':              'photo_url',
    'photo_url':                    'photo_url',

    # ── Position ──────────────────────────────────────────
    'position':                     'positions',
    'player_positions':             'positions',
    'alternative positions':        'alt_positions_raw',
    'alt_positions':                'alt_positions_raw',

    # ── Player meta ───────────────────────────────────────
    'weak foot':                    'weak_foot',
    'weak_foot':                    'weak_foot',
    'skill moves':                  'skill_moves',
    'skill_moves':                  'skill_moves',
    'preferred foot':               'preferred_foot',
    'preferred_foot':               'preferred_foot',
    'play style':                   'work_rate',   # closest equivalent
    'work_rate':                    'work_rate',

    # ── Base stats (flynn28 uses short uppercase) ─────────
    'pac':                          'pace',
    'pace':                         'pace',
    'sho':                          'shooting',
    'shooting':                     'shooting',
    'pas':                          'passing',
    'passing':                      'passing',
    'dri':                          'dribbling',
    'dribbling':                    'dribbling',
    'def':                          'defending',
    'defending':                    'defending',
    'phy':                          'physicality',
    'physic':                       'physicality',
    'physicality':                  'physicality',

    # ── GK stats ──────────────────────────────────────────
    'gk diving':                    'gk_diving',
    'gk_diving':                    'gk_diving',
    'goalkeeping_diving':           'gk_diving',
    'gk handling':                  'gk_handling',
    'gk_handling':                  'gk_handling',
    'goalkeeping_handling':         'gk_handling',
    'gk kicking':                   'gk_kicking',
    'gk_kicking':                   'gk_kicking',
    'goalkeeping_kicking':          'gk_kicking',
    'gk positioning':               'gk_positioning',
    'gk_positioning':               'gk_positioning',
    'goalkeeping_positioning':      'gk_positioning',
    'gk reflexes':                  'gk_reflexes',
    'gk_reflexes':                  'gk_reflexes',
    'goalkeeping_reflexes':         'gk_reflexes',
    'goalkeeping_speed':            'gk_speed',
    'gk_speed':                     'gk_speed',

    # ── Sub-stats (flynn28 uses Title Case with spaces) ───
    'acceleration':                 'acceleration',
    'movement_acceleration':        'acceleration',
    'sprint speed':                 'sprint_speed',
    'movement_sprint_speed':        'sprint_speed',
    'positioning':                  'positioning',
    'attacking_positioning':        'positioning',
    'finishing':                    'finishing',
    'attacking_finishing':          'finishing',
    'shot power':                   'shot_power',
    'power_shot_power':             'shot_power',
    'long shots':                   'long_shots',
    'power_long_shots':             'long_shots',
    'volleys':                      'volleys',
    'attacking_volleys':            'volleys',
    'penalties':                    'penalties',
    'mentality_penalties':          'penalties',
    'vision':                       'vision',
    'mentality_vision':             'vision',
    'crossing':                     'crossing',
    'attacking_crossing':           'crossing',
    'free kick accuracy':           'fk_accuracy',
    'skill_fk_accuracy':            'fk_accuracy',
    'short passing':                'short_passing',
    'attacking_short_passing':      'short_passing',
    'long passing':                 'long_passing',
    'skill_long_passing':           'long_passing',
    'curve':                        'curve',
    'skill_curve':                  'curve',
    'agility':                      'agility',
    'movement_agility':             'agility',
    'balance':                      'balance',
    'movement_balance':             'balance',
    'reactions':                    'reactions',
    'movement_reactions':           'reactions',
    'ball control':                 'ball_control',
    'skill_ball_control':           'ball_control',
    'composure':                    'composure',
    'mentality_composure':          'composure',
    'interceptions':                'interceptions',
    'defending_interceptions':      'interceptions',
    'heading accuracy':             'heading_accuracy',
    'attacking_heading_accuracy':   'heading_accuracy',
    'def awareness':                'def_awareness',
    'defending_marking_awareness':  'def_awareness',
    'standing tackle':              'standing_tackle',
    'defending_standing_tackle':    'standing_tackle',
    'sliding tackle':               'sliding_tackle',
    'defending_sliding_tackle':     'sliding_tackle',
    'jumping':                      'jumping',
    'power_jumping':                'jumping',
    'stamina':                      'stamina',
    'power_stamina':                'stamina',
    'strength':                     'strength',
    'power_strength':               'strength',
    'aggression':                   'aggression',
    'mentality_aggression':         'aggression',
}

POSITION_MAP = {
    'GKP': 'GK', 'GK': 'GK',
    'CB': 'CB', 'LCB': 'CB', 'RCB': 'CB',
    'LB': 'LB', 'LWB': 'LWB',
    'RB': 'RB', 'RWB': 'RWB',
    'CDM': 'CDM', 'CM': 'CM', 'CAM': 'CAM',
    'LM': 'LM', 'RM': 'RM',
    'LW': 'LW', 'RW': 'RW',
    'CF': 'CF', 'ST': 'ST', 'LS': 'ST', 'RS': 'ST', 'CSS': 'ST',
}

VALID_POSITIONS = {p for _, p in EAFCPlayer.POSITION_CHOICES}


def safe_int(val, default=0, max_val=None):
    """Convert any value to int safely, stripping units like cm/kg."""
    if val is None:
        return default
    s = str(val).strip()
    if s in ('', 'None', 'nan', 'N/A', '-'):
        return default
    # Strip units: "181cm" → "181", "75kg" → "75"
    s = re.sub(r'[^\d.-]', '', s)
    try:
        result = int(float(s)) if s else default
        if max_val is not None:
            result = min(result, max_val)
        return result
    except (ValueError, TypeError):
        return default


def safe_stat(val):
    """Parse a player stat value, clamped to 0-99 (fits PositiveSmallIntegerField)."""
    return max(0, min(99, safe_int(val, 0)))


def safe_smallint(val, default=0):
    """Parse any value that goes into a PositiveSmallIntegerField (max 32767)."""
    return max(0, min(32767, safe_int(val, default)))


def normalise_position(raw):
    """Take the first position token, normalise to a valid POSITION_CHOICES value."""
    # Handle separators: comma, pipe, slash, space
    first = re.split(r'[,|/\s]+', str(raw).strip())[0].strip().upper()
    mapped = POSITION_MAP.get(first, first)
    return mapped if mapped in VALID_POSITIONS else 'ST'


def parse_alt_positions(raw):
    """Return comma-joined normalised alt positions string."""
    tokens = re.split(r'[,|/\s]+', str(raw).strip())
    return ','.join(
        normalise_position(t) for t in tokens if t.strip()
    )


class Command(BaseCommand):
    help = 'Import EA FC players from Kaggle CSV (supports sofifa and flynn28 formats)'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Path to CSV file')
        parser.add_argument('--min-overall', type=int, default=0,
                            help='Skip players below this OVR (default: import all)')
        parser.add_argument('--gender', choices=['M', 'F', 'all'], default='M',
                            help='Filter by gender column if present: M, F, or all (default: M)')
        parser.add_argument('--wipe', action='store_true',
                            help='Delete all existing players before importing')
        parser.add_argument('--dry-run', action='store_true',
                            help='Parse and report only — do not write to DB')

    def handle(self, *args, **options):
        filepath = options['file']
        if not os.path.exists(filepath):
            raise CommandError(f'File not found: {filepath}')

        if options['wipe'] and not options['dry_run']:
            count, _ = EAFCPlayer.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Wiped {count} existing players.'))

        min_ovr   = options['min_overall']
        gender_f  = options['gender']   # 'M', 'F', or 'all'
        dry_run   = options['dry_run']

        self.stdout.write(f'\nOpening: {filepath}')

        # ── Step 1: detect columns ────────────────────────────────────────────
        with open(filepath, encoding='utf-8', errors='replace') as f:
            raw_cols = csv.DictReader(f).fieldnames or []

        col_map = {}   # raw column name → canonical key
        for raw in raw_cols:
            canonical = COLUMN_ALIASES.get(raw.lower().strip())
            if canonical:
                col_map[raw] = canonical

        self.stdout.write(f'Columns in file  : {len(raw_cols)}')
        self.stdout.write(f'Columns mapped   : {len(col_map)}')

        # Show any unmapped columns so you can add aliases if needed
        unmapped = [c for c in raw_cols if c not in col_map and c.strip()]
        if unmapped:
            self.stdout.write(f'Unmapped columns : {unmapped}')

        # Confirm we have the bare minimum
        mapped_vals = set(col_map.values())
        required = {'ea_id', 'name', 'overall', 'positions'}
        missing  = required - mapped_vals
        if missing:
            raise CommandError(
                f'Missing required columns: {missing}\n'
                f'File has: {raw_cols[:20]}'
            )

        has_gender = 'gender' in mapped_vals

        # ── Step 2: pre-load / create leagues & clubs ─────────────────────────
        self.stdout.write('\nPre-loading leagues and clubs …')
        league_cache = {}
        club_cache   = {}

        with open(filepath, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                r = {col_map[k]: v for k, v in row.items() if k in col_map}

                # Gender filter
                if has_gender and gender_f != 'all':
                    g = str(r.get('gender', 'M')).strip().upper()
                    if g != gender_f:
                        continue

                league_name = str(r.get('league_name', '')).strip()
                club_name   = str(r.get('club_name', '')).strip()

                if league_name and league_name not in league_cache:
                    league_id = safe_int(r.get('league_id', 0))
                    try:
                        lg = League.objects.get(name=league_name)
                    except League.DoesNotExist:
                        lg = League.objects.create(
                            name=league_name,
                            ea_id=league_id if league_id else League.objects.count() + 9000
                        )
                    league_cache[league_name] = lg

                if club_name and club_name not in club_cache:
                    club_id = safe_int(r.get('club_id', 0))
                    try:
                        cl = Club.objects.get(name=club_name)
                    except Club.DoesNotExist:
                        cl = Club.objects.create(
                            name=club_name,
                            ea_id=club_id if club_id else Club.objects.count() + 9000,
                            league=league_cache.get(league_name),
                        )
                    club_cache[club_name] = cl

        self.stdout.write(
            f'  → {len(league_cache)} leagues, {len(club_cache)} clubs ready.'
        )

        # ── Step 3: import players ────────────────────────────────────────────
        self.stdout.write('\nImporting players …')
        created = updated = skipped = 0
        seen_ids = set()

        with open(filepath, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                r = {col_map[k]: v for k, v in row.items() if k in col_map}

                # ── Gender filter ─────────────────────────────────────────────
                if has_gender and gender_f != 'all':
                    g = str(r.get('gender', 'M')).strip().upper()
                    if g != gender_f:
                        skipped += 1
                        continue

                # ── OVR filter ────────────────────────────────────────────────
                overall = safe_int(r.get('overall', 0))
                if overall < min_ovr:
                    skipped += 1
                    continue

                # ── ID dedup ──────────────────────────────────────────────────
                ea_id = safe_int(r.get('ea_id', 0))
                if not ea_id or ea_id in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(ea_id)

                # ── Position ──────────────────────────────────────────────────
                pos_raw = str(r.get('positions', '')).strip() or 'ST'
                position = normalise_position(pos_raw)

                alt_raw = str(r.get('alt_positions_raw', '')).strip()
                alt_positions = parse_alt_positions(alt_raw) if alt_raw else ''

                # ── Club ──────────────────────────────────────────────────────
                club_name = str(r.get('club_name', '')).strip()
                club = club_cache.get(club_name)

                # ── Build defaults dict ───────────────────────────────────────
                defaults = dict(
                    name=str(r.get('name', '')).strip()[:100] or f'Player {ea_id}',
                    full_name=str(r.get('full_name', '')).strip()[:150],
                    overall=safe_stat(overall) if overall <= 99 else min(99, overall),
                    position=position,
                    alt_positions=alt_positions[:100],
                    club=club,
                    nationality=str(r.get('nationality', '')).strip()[:100],
                    nationality_id=safe_int(r.get('nationality_id')) or None,
                    age=safe_smallint(r.get('age')) or None,
                    height_cm=safe_smallint(r.get('height_cm')) or None,
                    weight_kg=safe_smallint(r.get('weight_kg')) or None,
                    photo_url=str(r.get('photo_url', '')).strip()[:500],
                    # Base stats
                    pace=safe_stat(r.get('pace')),
                    shooting=safe_stat(r.get('shooting')),
                    passing=safe_stat(r.get('passing')),
                    dribbling=safe_stat(r.get('dribbling')),
                    defending=safe_stat(r.get('defending')),
                    physicality=safe_stat(r.get('physicality')),
                    # GK stats
                    gk_diving=safe_stat(r.get('gk_diving')) or None,
                    gk_handling=safe_stat(r.get('gk_handling')) or None,
                    gk_kicking=safe_stat(r.get('gk_kicking')) or None,
                    gk_reflexes=safe_stat(r.get('gk_reflexes')) or None,
                    gk_speed=safe_stat(r.get('gk_speed')) or None,
                    gk_positioning=safe_stat(r.get('gk_positioning')) or None,
                    # Sub-stats
                    acceleration=safe_stat(r.get('acceleration')),
                    sprint_speed=safe_stat(r.get('sprint_speed')),
                    positioning=safe_stat(r.get('positioning')),
                    finishing=safe_stat(r.get('finishing')),
                    shot_power=safe_stat(r.get('shot_power')),
                    long_shots=safe_stat(r.get('long_shots')),
                    volleys=safe_stat(r.get('volleys')),
                    penalties=safe_stat(r.get('penalties')),
                    vision=safe_stat(r.get('vision')),
                    crossing=safe_stat(r.get('crossing')),
                    fk_accuracy=safe_stat(r.get('fk_accuracy')),
                    short_passing=safe_stat(r.get('short_passing')),
                    long_passing=safe_stat(r.get('long_passing')),
                    curve=safe_stat(r.get('curve')),
                    agility=safe_stat(r.get('agility')),
                    balance=safe_stat(r.get('balance')),
                    reactions=safe_stat(r.get('reactions')),
                    ball_control=safe_stat(r.get('ball_control')),
                    dribbling_sub=safe_stat(r.get('dribbling')),  # 'Dribbling' col = dribbling sub-stat
                    composure=safe_stat(r.get('composure')),
                    interceptions=safe_stat(r.get('interceptions')),
                    heading_accuracy=safe_stat(r.get('heading_accuracy')),
                    def_awareness=safe_stat(r.get('def_awareness')),
                    standing_tackle=safe_stat(r.get('standing_tackle')),
                    sliding_tackle=safe_stat(r.get('sliding_tackle')),
                    jumping=safe_stat(r.get('jumping')),
                    stamina=safe_stat(r.get('stamina')),
                    strength=safe_stat(r.get('strength')),
                    aggression=safe_stat(r.get('aggression')),
                    # Meta
                    skill_moves=max(1, min(5, safe_int(r.get('skill_moves'), 2))),
                    weak_foot=max(1, min(5, safe_int(r.get('weak_foot'), 2))),
                    preferred_foot=str(r.get('preferred_foot', '')).strip()[:20],
                    work_rate=str(r.get('work_rate', '')).strip()[:100],
                )

                if dry_run:
                    created += 1
                    continue

                _, was_created = EAFCPlayer.objects.update_or_create(
                    ea_id=ea_id, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

                if (created + updated) % 1000 == 0:
                    self.stdout.write(f'  … {created + updated:,} processed')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nDry run — would import {created:,} players (skipped {skipped:,}). Nothing written.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Done!  Created: {created:,} | Updated: {updated:,} | Skipped: {skipped:,}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'  Total players in DB: {EAFCPlayer.objects.count():,}'
        ))