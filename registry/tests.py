from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import httpx
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from . import services, tasks
from .models import Fight, FightEvent, Job, Person

PEOPLE = [
    {'id': 1, 'name': 'Alice', 'age': 30},
    {'id': 2, 'name': 'Bob', 'age': 25},
    {'id': 3, 'name': 'Carol', 'age': 40, 'key': 'fight-info'},
]


def fight_row(fight_id, blue, red, steps):
    return {
        'fight_id': fight_id,
        'blue_soldier_id': blue,
        'red_soldier_id': red,
        'steps': [{'attacker': a, 'defender': d, 'damage': dmg} for a, d, dmg in steps],
    }


class ImportTests(TestCase):
    @mock.patch('registry.api.fetch_people', return_value=PEOPLE)
    def test_import_people(self, _):
        Job.objects.create(kind=Job.Kind.PEOPLE)
        tasks.import_people()
        self.assertEqual(Person.objects.count(), 3)
        self.assertEqual(Person.objects.get(pk=3).key, 'fight-info')
        self.assertEqual(Job.objects.get().status, Job.Status.DONE)

    @mock.patch('registry.api.fetch_draft')
    def test_draft_adds_rank_and_health(self, fetch_draft):
        Person.objects.create(id=1, name='Alice', age=30)
        fetch_draft.return_value = [{**PEOPLE[0], 'rank': 'General', 'health': 100}]
        Job.objects.create(kind=Job.Kind.DRAFT, batch=4)
        tasks.apply_draft(tasks.download_draft(4))
        person = Person.objects.get(pk=1)
        self.assertEqual((person.rank, person.health), ('General', 100))
        self.assertEqual(Job.objects.get().status, Job.Status.DONE)

    @mock.patch('registry.api.fetch_draft', side_effect=httpx.ReadTimeout('slow'))
    def test_draft_retries_on_timeout(self, _):
        self.assertIn(httpx.TimeoutException, tasks.download_draft.autoretry_for)
        Job.objects.create(kind=Job.Kind.DRAFT, batch=0)
        result = tasks.download_draft.apply(args=[0])
        self.assertIsInstance(result.result, httpx.ReadTimeout)
        job = Job.objects.get()
        self.assertEqual(job.status, Job.Status.FAILED)
        self.assertEqual(job.attempts, tasks.RETRY_POLICY['max_retries'] + 1)

    @mock.patch('registry.api.fetch_fights')
    def test_download_fights_is_idempotent(self, fetch_fights):
        Person.objects.bulk_create(Person(**p) for p in PEOPLE)
        fetch_fights.return_value = [fight_row(0, 1, 2, [(1, 2, 5), (2, 1, 7)])]
        tasks.download_fights(0)
        tasks.download_fights(0)
        self.assertEqual(Fight.objects.count(), 1)
        self.assertEqual(list(FightEvent.objects.values_list('order', 'damage')), [(0, 5), (1, 7)])


class SimulationTests(TestCase):
    def setUp(self):
        Person.objects.bulk_create(Person(**p) for p in PEOPLE)

    def create_fight(self, fight_id, blue, red, steps):
        fight = Fight.objects.create(id=fight_id, batch=0, blue_id=blue, red_id=red)
        FightEvent.objects.bulk_create(
            FightEvent(fight=fight, order=i, attacker_id=a, defender_id=d, damage=dmg)
            for i, (a, d, dmg) in enumerate(steps)
        )
        return fight

    def test_simulate_fight_records_health_and_winner(self):
        fight = self.create_fight(0, 1, 2, [(1, 2, 60), (2, 1, 10), (1, 2, 70)])
        tasks.simulate_fight(fight.id)
        fight.refresh_from_db()
        self.assertEqual(fight.status, Fight.Status.DONE)
        self.assertEqual(fight.winner_id, 1)
        self.assertEqual(
            list(fight.events.values_list('defender_health_after', flat=True)), [40, 90, 0]
        )
        self.assertEqual(Person.objects.get(pk=2).health, 0)

    def test_simulate_fight_twice_does_not_double_damage(self):
        fight = self.create_fight(0, 1, 2, [(1, 2, 10)])
        tasks.simulate_fight(fight.id)
        tasks.simulate_fight(fight.id)
        self.assertEqual(Person.objects.get(pk=2).health, 90)

    def test_draw_has_no_winner(self):
        fight = self.create_fight(0, 1, 2, [(1, 2, 10), (2, 1, 10)])
        tasks.simulate_fight(fight.id)
        fight.refresh_from_db()
        self.assertIsNone(fight.winner)

    def test_reset_health(self):
        fight = self.create_fight(0, 1, 2, [(1, 2, 10)])
        tasks.simulate_fight(fight.id)
        services.reset_health()
        fight.refresh_from_db()
        self.assertEqual((fight.status, fight.winner), (Fight.Status.PENDING, None))
        self.assertEqual(Person.objects.get(pk=2).health, 100)
        self.assertIsNone(fight.events.get().defender_health_after)


class ConcurrentSimulationTests(TransactionTestCase):
    def test_parallel_fights_on_same_soldier(self):
        Person.objects.bulk_create(Person(**p) for p in PEOPLE)
        fights = []
        for fight_id in range(20):
            fight = Fight.objects.create(id=fight_id, batch=0, blue_id=1, red_id=2 + fight_id % 2)
            FightEvent.objects.bulk_create(
                FightEvent(fight=fight, order=i, attacker_id=fight.red_id, defender_id=1, damage=1)
                for i in range(3)
            )
            fights.append(fight.id)

        def run(fight_id):
            try:
                tasks.simulate_fight(fight_id)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(run, fights))

        self.assertEqual(Person.objects.get(pk=1).health, 40)
        self.assertEqual(
            sorted(FightEvent.objects.values_list('defender_health_after', flat=True)),
            list(range(40, 100)),
        )


class ViewTests(TestCase):
    def test_simulate_page_renders(self):
        Person.objects.create(id=1, name='Alice', age=30)
        response = self.client.get(reverse('simulate'))
        self.assertContains(response, 'Alice')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_actions_require_post(self):
        for name in ['import-people', 'draft', 'download-fights', 'reset-health']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 405)

    @mock.patch('registry.services.group')
    def test_simulate_post_launches_pending_fights(self, group):
        Person.objects.bulk_create(Person(**p) for p in PEOPLE)
        Fight.objects.create(id=0, batch=0, blue_id=1, red_id=2)
        Fight.objects.create(id=1, batch=0, blue_id=1, red_id=3, status=Fight.Status.DONE)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('simulate'))
        self.assertRedirects(response, reverse('simulate'))
        group.return_value.apply_async.assert_called_once()
        self.assertEqual(Fight.objects.get(pk=0).status, Fight.Status.RUNNING)
