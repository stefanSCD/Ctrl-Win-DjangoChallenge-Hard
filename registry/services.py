from celery import chain, group
from django.conf import settings
from django.db import transaction

from .models import Fight, FightEvent, Job, Person
from .tasks import apply_draft, download_draft, download_fights, import_people, simulate_fight


def reset_jobs(kind, batches):
    Job.objects.filter(kind=kind).delete()
    Job.objects.bulk_create([Job(kind=kind, batch=batch) for batch in batches])


def stage_done(kind):
    jobs = Job.objects.filter(kind=kind)
    return jobs.exists() and not jobs.exclude(status=Job.Status.DONE).exists()


def start_people_import():
    reset_jobs(Job.Kind.PEOPLE, [0])
    import_people.delay()


def start_draft():
    batches = settings.API_BATCHES
    reset_jobs(Job.Kind.DRAFT, batches)
    group(chain(download_draft.s(batch), apply_draft.s()) for batch in batches).apply_async()


def start_fights_download():
    batches = settings.API_BATCHES
    reset_jobs(Job.Kind.FIGHTS, batches)
    group(download_fights.s(batch) for batch in batches).apply_async()


def start_simulation():
    with transaction.atomic():
        pending = Fight.objects.select_for_update().filter(status=Fight.Status.PENDING)
        fight_ids = list(pending.values_list('id', flat=True))
        Fight.objects.filter(id__in=fight_ids).update(status=Fight.Status.RUNNING)
    transaction.on_commit(
        lambda: group(simulate_fight.s(fight_id) for fight_id in fight_ids).apply_async()
    )
    return len(fight_ids)


@transaction.atomic
def reset_health():
    Person.objects.update(health=Person.MAX_HEALTH)
    FightEvent.objects.update(defender_health_after=None, status=FightEvent.Status.PENDING)
    Fight.objects.update(status=Fight.Status.PENDING, winner=None)
