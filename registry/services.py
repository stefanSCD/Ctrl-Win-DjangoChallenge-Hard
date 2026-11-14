from celery import chain, group
from django.conf import settings

from .models import Job
from .tasks import apply_draft, download_draft, import_people


def reset_jobs(kind, batches):
    Job.objects.filter(kind=kind).delete()
    Job.objects.bulk_create([Job(kind=kind, batch=batch) for batch in batches])


def start_people_import():
    reset_jobs(Job.Kind.PEOPLE, [0])
    import_people.delay()


def start_draft():
    batches = settings.API_BATCHES
    reset_jobs(Job.Kind.DRAFT, batches)
    group(chain(download_draft.s(batch), apply_draft.s()) for batch in batches).apply_async()
