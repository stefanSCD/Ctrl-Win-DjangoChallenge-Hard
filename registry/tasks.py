from celery import Task, shared_task
from django.db import OperationalError, transaction
from django.db.models import F, Sum
from django.db.models.functions import Greatest

from . import api
from .models import Fight, FightEvent, Job, Person

RETRY_POLICY = {
    'autoretry_for': api.RETRYABLE_ERRORS,
    'retry_backoff': 5,
    'retry_backoff_max': 120,
    'retry_jitter': True,
    'max_retries': 6,
}


class JobTask(Task):
    job_kind = None

    def job_batch(self, args, kwargs):
        value = args[0] if args else kwargs.get('batch', 0)
        return value['batch'] if isinstance(value, dict) else value

    def start_job(self, batch):
        Job.objects.filter(kind=self.job_kind, batch=batch).update(
            status=Job.Status.RUNNING, attempts=F('attempts') + 1, error=''
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        Job.objects.filter(kind=self.job_kind, batch=self.job_batch(args, kwargs)).update(
            status=Job.Status.FAILED, error=repr(exc)
        )


def finish_job(kind, batch):
    Job.objects.filter(kind=kind, batch=batch).update(status=Job.Status.DONE)


def upsert_people(rows, fields):
    Person.objects.bulk_create(
        [Person(**{field: row.get(field) for field in ('id', *fields)}) for row in rows],
        update_conflicts=True,
        unique_fields=['id'],
        update_fields=fields,
    )


@shared_task(bind=True, base=JobTask, job_kind=Job.Kind.PEOPLE, **RETRY_POLICY)
def import_people(self):
    self.start_job(0)
    rows = api.fetch_people()
    upsert_people(rows, ['name', 'age', 'key'])
    finish_job(Job.Kind.PEOPLE, 0)
    return len(rows)


@shared_task(bind=True, base=JobTask, job_kind=Job.Kind.DRAFT, **RETRY_POLICY)
def download_draft(self, batch):
    self.start_job(batch)
    return {'batch': batch, 'rows': api.fetch_draft(batch)}


@shared_task(bind=True, base=JobTask, job_kind=Job.Kind.DRAFT)
def apply_draft(self, result):
    upsert_people(result['rows'], ['name', 'age', 'key', 'rank', 'health'])
    finish_job(Job.Kind.DRAFT, result['batch'])
    return len(result['rows'])


@shared_task(bind=True, base=JobTask, job_kind=Job.Kind.FIGHTS, **RETRY_POLICY)
def download_fights(self, batch):
    self.start_job(batch)
    rows = api.fetch_fights(batch)
    fights = [
        Fight(id=row['fight_id'], batch=batch, blue_id=row['blue_soldier_id'], red_id=row['red_soldier_id'])
        for row in rows
    ]
    events = [
        FightEvent(
            fight_id=row['fight_id'],
            order=order,
            attacker_id=step['attacker'],
            defender_id=step['defender'],
            damage=step['damage'],
        )
        for row in rows
        for order, step in enumerate(row['steps'])
    ]
    with transaction.atomic():
        Fight.objects.bulk_create(
            fights, update_conflicts=True, unique_fields=['id'], update_fields=['batch', 'blue', 'red']
        )
        FightEvent.objects.bulk_create(events, ignore_conflicts=True)
    finish_job(Job.Kind.FIGHTS, batch)
    return len(fights)


def apply_event(event_id):
    with transaction.atomic():
        event = (
            FightEvent.objects.select_for_update()
            .filter(pk=event_id, status=FightEvent.Status.PENDING)
            .first()
        )
        if event is None:
            return not FightEvent.objects.filter(
                pk=event_id, status=FightEvent.Status.SKIPPED
            ).exists()
        fighters = (
            Person.objects.select_for_update()
            .filter(pk__in=[event.attacker_id, event.defender_id])
            .order_by('pk')
        )
        dead = {person.pk for person in fighters if person.health == 0}
        if dead:
            FightEvent.objects.filter(
                fight_id=event.fight_id, order__gte=event.order, status=FightEvent.Status.PENDING
            ).update(status=FightEvent.Status.SKIPPED)
            Fight.objects.filter(pk=event.fight_id).update(
                winner_id=stopped_winner(event.fight, event.order, dead)
            )
            return False
        defender = Person.objects.filter(pk=event.defender_id)
        defender.update(health=Greatest(F('health') - event.damage, 0))
        event.defender_health_after = defender.values_list('health', flat=True).get()
        event.status = FightEvent.Status.APPLIED
        event.save(update_fields=['defender_health_after', 'status'])
        return True


def damage_winner(fight):
    totals = dict(
        fight.events.filter(status=FightEvent.Status.APPLIED)
        .order_by()
        .values_list('attacker')
        .annotate(total=Sum('damage'))
    )
    blue, red = totals.get(fight.blue_id, 0), totals.get(fight.red_id, 0)
    if blue == red:
        return None
    return fight.blue_id if blue > red else fight.red_id


def killer(fight):
    last = fight.events.filter(status=FightEvent.Status.APPLIED).order_by('-order').first()
    return last.attacker_id if last and last.defender_health_after == 0 else None


def stopped_winner(fight, order, dead):
    alive = {fight.blue_id, fight.red_id} - dead
    if len(alive) == 1:
        return alive.pop()
    if order == 0:
        return None
    return killer(fight) or damage_winner(fight)


def finished_winner(fight):
    return killer(fight) or damage_winner(fight)


@shared_task(
    autoretry_for=(OperationalError,), retry_backoff=1, retry_jitter=True, max_retries=5
)
def simulate_fight(fight_id):
    fight = Fight.objects.get(pk=fight_id)
    if fight.status == Fight.Status.DONE:
        return fight.winner_id
    Fight.objects.filter(pk=fight_id).update(status=Fight.Status.RUNNING)
    pending = fight.events.filter(status=FightEvent.Status.PENDING).order_by('order')
    for event_id in pending.values_list('id', flat=True):
        if not apply_event(event_id):
            break
    if not fight.events.filter(status=FightEvent.Status.SKIPPED).exists():
        Fight.objects.filter(pk=fight_id).update(winner_id=finished_winner(fight))
    Fight.objects.filter(pk=fight_id).update(status=Fight.Status.DONE)
    return Fight.objects.values_list('winner_id', flat=True).get(pk=fight_id)
