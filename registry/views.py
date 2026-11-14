from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import Fight, FightEvent, Job, Person


def simulate(request):
    if request.method == 'POST':
        count = services.start_simulation()
        messages.info(request, f'Simulation started for {count} fights.')
        return redirect('simulate')

    jobs = {
        kind.value: dict(
            Job.objects.filter(kind=kind).values_list('status').annotate(n=Count('id'))
        )
        for kind in Job.Kind
    }
    fights = Fight.objects.select_related('blue', 'red', 'winner').prefetch_related(
        Prefetch('events', queryset=FightEvent.objects.order_by('order'))
    )
    people = Person.objects.annotate(
        fights=Count('blue_fights', distinct=True) + Count('red_fights', distinct=True),
        wins=Count('won_fights', distinct=True),
    )
    fight_status = dict(Fight.objects.values_list('status').annotate(n=Count('id')))
    active = (
        Job.objects.filter(status__in=[Job.Status.PENDING, Job.Status.RUNNING]).exists()
        or fight_status.get(Fight.Status.RUNNING, 0) > 0
    )
    return render(request, 'registry/simulate.html', {
        'jobs': jobs,
        'jobs_failed': Job.objects.filter(status=Job.Status.FAILED),
        'fights': fights,
        'people': people,
        'fight_status': fight_status,
        'alive': people.filter(health__gt=0).count(),
        'active': active,
    })


@require_POST
def import_people(request):
    services.start_people_import()
    messages.info(request, 'People import started.')
    return redirect('simulate')


@require_POST
def draft(request):
    services.start_draft()
    messages.info(request, 'Drafting started.')
    return redirect('simulate')


@require_POST
def download_fights(request):
    services.start_fights_download()
    messages.info(request, 'Fight download started.')
    return redirect('simulate')


@require_POST
def reset_health(request):
    if Fight.objects.filter(status=Fight.Status.RUNNING).exists():
        messages.error(request, 'Cannot reset while fights are running.')
    else:
        services.reset_health()
        messages.info(request, 'Health and fight results reset.')
    return redirect('simulate')
