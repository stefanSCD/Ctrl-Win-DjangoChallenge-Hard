from celery import Task, shared_task
from django.db import transaction
from django.db.models import F

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
