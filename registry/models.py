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
