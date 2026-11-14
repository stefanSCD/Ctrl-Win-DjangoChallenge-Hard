from django.db import models


class Person(models.Model):
    class Rank(models.TextChoices):
        PRIVATE = 'Private'
        SERGEANT = 'Sergeant'
        LIEUTENANT = 'Lieutenant'
        GENERAL = 'General'

    MAX_HEALTH = 100

    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=200)
    age = models.PositiveSmallIntegerField()
    key = models.CharField(max_length=100, null=True, blank=True)
    rank = models.CharField(max_length=20, choices=Rank, null=True, blank=True)
    health = models.PositiveSmallIntegerField(default=MAX_HEALTH)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Job(models.Model):
    class Kind(models.TextChoices):
        PEOPLE = 'people'
        DRAFT = 'draft'
        FIGHTS = 'fights'

    class Status(models.TextChoices):
        PENDING = 'pending'
        RUNNING = 'running'
        DONE = 'done'
        FAILED = 'failed'

    kind = models.CharField(max_length=10, choices=Kind)
    batch = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', 'batch']
        constraints = [
            models.UniqueConstraint(fields=['kind', 'batch'], name='unique_job_kind_batch'),
        ]

    def __str__(self):
        return f'{self.kind}[{self.batch}] {self.status}'


class Fight(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        RUNNING = 'running'
        DONE = 'done'

    id = models.PositiveIntegerField(primary_key=True)
    batch = models.PositiveSmallIntegerField(db_index=True)
    blue = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='blue_fights')
    red = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='red_fights')
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING, db_index=True)
    winner = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_fights'
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'Fight {self.id}: {self.blue} vs {self.red}'


class FightEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        APPLIED = 'applied'
        SKIPPED = 'skipped'

    fight = models.ForeignKey(Fight, on_delete=models.CASCADE, related_name='events')
    order = models.PositiveSmallIntegerField()
    attacker = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='attacks')
    defender = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='defenses')
    damage = models.PositiveSmallIntegerField()
    defender_health_after = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)

    class Meta:
        ordering = ['fight', 'order']
        constraints = [
            models.UniqueConstraint(fields=['fight', 'order'], name='unique_event_fight_order'),
        ]

    def __str__(self):
        return f'{self.fight_id}#{self.order}: {self.attacker_id} -> {self.defender_id} ({self.damage})'
