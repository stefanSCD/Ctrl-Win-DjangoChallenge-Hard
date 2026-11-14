from celery import Task, shared_task
from django.db.models import F

from . import api
from .models import Job, Person

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
        return args[0] if args else kwargs.get('batch', 0)

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
