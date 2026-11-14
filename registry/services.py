from .models import Job
from .tasks import import_people


def reset_jobs(kind, batches):
    Job.objects.filter(kind=kind).delete()
    Job.objects.bulk_create([Job(kind=kind, batch=batch) for batch in batches])


def start_people_import():
    reset_jobs(Job.Kind.PEOPLE, [0])
    import_people.delay()
