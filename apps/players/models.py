from django.db import models


class League(models.Model):
    ea_id = models.IntegerField(unique=True, default=0)
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Club(models.Model):
    ea_id = models.IntegerField(unique=True, default=0)
    name = models.CharField(max_length=100)
    league = models.ForeignKey(League, null=True, blank=True, on_delete=models.SET_NULL)
    logo_url = models.URLField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class EAFCPlayer(models.Model):
    POSITION_CHOICES = [
        ('GK', 'GK'), ('CB', 'CB'), ('LB', 'LB'), ('RB', 'RB'),
        ('LWB', 'LWB'), ('RWB', 'RWB'),
        ('CDM', 'CDM'), ('CM', 'CM'), ('CAM', 'CAM'),
        ('LM', 'LM'), ('RM', 'RM'),
        ('LW', 'LW'), ('RW', 'RW'),
        ('CF', 'CF'), ('ST', 'ST'),
    ]

    ea_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=100, db_index=True)
    full_name = models.CharField(max_length=150, blank=True)
    overall = models.PositiveSmallIntegerField(db_index=True)
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, db_index=True)
    alt_positions = models.CharField(max_length=100, blank=True, help_text='Comma-separated alt positions')
    club = models.ForeignKey(Club, null=True, blank=True, on_delete=models.SET_NULL)
    nationality = models.CharField(max_length=100, blank=True)
    nationality_id = models.IntegerField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)
    photo_url = models.URLField(blank=True)

    # ── Outfield stats ────────────────────────────────────
    pace = models.PositiveSmallIntegerField(default=0)
    shooting = models.PositiveSmallIntegerField(default=0)
    passing = models.PositiveSmallIntegerField(default=0)
    dribbling = models.PositiveSmallIntegerField(default=0)
    defending = models.PositiveSmallIntegerField(default=0)
    physicality = models.PositiveSmallIntegerField(default=0)

    # ── GK stats (null for outfield) ─────────────────────
    gk_diving = models.PositiveSmallIntegerField(null=True, blank=True)
    gk_handling = models.PositiveSmallIntegerField(null=True, blank=True)
    gk_kicking = models.PositiveSmallIntegerField(null=True, blank=True)
    gk_reflexes = models.PositiveSmallIntegerField(null=True, blank=True)
    gk_speed = models.PositiveSmallIntegerField(null=True, blank=True)
    gk_positioning = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Detailed sub-stats ───────────────────────────────
    acceleration = models.PositiveSmallIntegerField(default=0)
    sprint_speed = models.PositiveSmallIntegerField(default=0)
    positioning = models.PositiveSmallIntegerField(default=0)
    finishing = models.PositiveSmallIntegerField(default=0)
    shot_power = models.PositiveSmallIntegerField(default=0)
    long_shots = models.PositiveSmallIntegerField(default=0)
    volleys = models.PositiveSmallIntegerField(default=0)
    penalties = models.PositiveSmallIntegerField(default=0)
    vision = models.PositiveSmallIntegerField(default=0)
    crossing = models.PositiveSmallIntegerField(default=0)
    fk_accuracy = models.PositiveSmallIntegerField(default=0)
    short_passing = models.PositiveSmallIntegerField(default=0)
    long_passing = models.PositiveSmallIntegerField(default=0)
    curve = models.PositiveSmallIntegerField(default=0)
    agility = models.PositiveSmallIntegerField(default=0)
    balance = models.PositiveSmallIntegerField(default=0)
    reactions = models.PositiveSmallIntegerField(default=0)
    ball_control = models.PositiveSmallIntegerField(default=0)
    dribbling_sub = models.PositiveSmallIntegerField(default=0)
    composure = models.PositiveSmallIntegerField(default=0)
    interceptions = models.PositiveSmallIntegerField(default=0)
    heading_accuracy = models.PositiveSmallIntegerField(default=0)
    def_awareness = models.PositiveSmallIntegerField(default=0)
    standing_tackle = models.PositiveSmallIntegerField(default=0)
    sliding_tackle = models.PositiveSmallIntegerField(default=0)
    jumping = models.PositiveSmallIntegerField(default=0)
    stamina = models.PositiveSmallIntegerField(default=0)
    strength = models.PositiveSmallIntegerField(default=0)
    aggression = models.PositiveSmallIntegerField(default=0)

    # ── Meta ─────────────────────────────────────────────
    skill_moves = models.PositiveSmallIntegerField(default=2)
    weak_foot = models.PositiveSmallIntegerField(default=2)
    preferred_foot = models.CharField(max_length=20, blank=True)
    work_rate = models.CharField(max_length=100, blank=True)

    last_synced = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-overall', 'name']
        indexes = [
            models.Index(fields=['overall', 'position']),
            models.Index(fields=['club']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f'{self.name} ({self.overall} {self.position})'

    @property
    def is_gk(self):
        return self.position == 'GK'

    def stats_dict(self):
        if self.is_gk:
            return {
                'DIV': self.gk_diving or 0,
                'HAN': self.gk_handling or 0,
                'KIC': self.gk_kicking or 0,
                'REF': self.gk_reflexes or 0,
                'SPD': self.gk_speed or 0,
                'POS': self.gk_positioning or 0,
            }
        return {
            'PAC': self.pace,
            'SHO': self.shooting,
            'PAS': self.passing,
            'DRI': self.dribbling,
            'DEF': self.defending,
            'PHY': self.physicality,
        }

    @property
    def detailed_stats(self):
        return [
            ('Acceleration', self.acceleration), ('Sprint Speed', self.sprint_speed),
            ('Positioning', self.positioning), ('Finishing', self.finishing),
            ('Shot Power', self.shot_power), ('Long Shots', self.long_shots),
            ('Volleys', self.volleys), ('Penalties', self.penalties),
            ('Vision', self.vision), ('Crossing', self.crossing),
            ('FK Accuracy', self.fk_accuracy), ('Short Passing', self.short_passing),
            ('Long Passing', self.long_passing), ('Curve', self.curve),
            ('Dribbling', self.dribbling_sub), ('Agility', self.agility),
            ('Balance', self.balance), ('Reactions', self.reactions),
            ('Ball Control', self.ball_control), ('Composure', self.composure),
            ('Interceptions', self.interceptions), ('Heading', self.heading_accuracy),
            ('Def. Awareness', self.def_awareness), ('Standing Tackle', self.standing_tackle),
            ('Sliding Tackle', self.sliding_tackle), ('Jumping', self.jumping),
            ('Stamina', self.stamina), ('Strength', self.strength),
            ('Aggression', self.aggression),
        ]
