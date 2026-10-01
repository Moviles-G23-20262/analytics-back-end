from django.test import SimpleTestCase
from datetime import datetime, timezone
from .views import calculate_buyer_journey_metrics


def at(day, hour=12):
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)


def view(user, material, day, hour=12):
    return {'user_id': user, 'material_id': material, 'occurred_at': at(day, hour)}


class BuyerJourneyMetricsTestCase(SimpleTestCase):

    def test_no_data_answers_zeros(self):
        result = calculate_buyer_journey_metrics([], [], [])

        for cut in ('views_before_contact', 'views_before_exchange'):
            self.assertEqual(result[cut]['mean'], 0.0)
            self.assertEqual(result[cut]['median'], 0.0)
            self.assertEqual(result[cut]['p75'], 0.0)
            self.assertEqual(result[cut]['total_users_analyzed'], 0)
            self.assertEqual(result[cut]['total_events'], 0)

    def test_buyer_with_zero_views_counts_as_zero(self):
        contacts = [view('u1', 'm1', 1)]

        result = calculate_buyer_journey_metrics([], contacts, [])

        self.assertEqual(result['views_before_contact']['total_users_analyzed'], 1)
        self.assertEqual(result['views_before_contact']['mean'], 0.0)
        self.assertEqual(result['views_before_contact']['total_events'], 0)

    def test_repeated_views_of_same_item_count_once(self):
        views = [view('u1', 'm1', 1, 9), view('u1', 'm1', 1, 10), view('u1', 'm2', 1, 11)]
        contacts = [view('u1', 'm2', 1, 12)]

        result = calculate_buyer_journey_metrics(views, contacts, [])

        self.assertEqual(result['views_before_contact']['mean'], 2.0)
        self.assertEqual(result['views_before_contact']['total_events'], 3)

    def test_contact_without_purchase_has_no_exchange_users(self):
        views = [view('u1', 'm1', 1), view('u1', 'm2', 2)]
        contacts = [view('u1', 'm2', 3)]

        result = calculate_buyer_journey_metrics(views, contacts, [])

        self.assertEqual(result['views_before_contact']['total_users_analyzed'], 1)
        self.assertEqual(result['views_before_contact']['mean'], 2.0)
        self.assertEqual(result['views_before_exchange']['total_users_analyzed'], 0)

    def test_views_after_the_cut_are_ignored_and_cut_is_inclusive(self):
        views = [view('u1', 'm1', 1), view('u1', 'm2', 2), view('u1', 'm3', 5)]
        contacts = [view('u1', 'm2', 2), view('u1', 'm3', 4)]  #usa el primer contacto (dia 2)

        result = calculate_buyer_journey_metrics(views, contacts, [])

        self.assertEqual(result['views_before_contact']['mean'], 2.0)

    def test_completed_exchange_uses_buyer_completion_time(self):
        views = [view('u1', 'm1', 1), view('u1', 'm2', 2), view('u1', 'm3', 3), view('u1', 'm4', 9)]
        contacts = [view('u1', 'm2', 2)]
        exchanges = [{'buyer_id': 'u1', 'material_id': 'm3', 'completed_at': at(4)}]

        result = calculate_buyer_journey_metrics(views, contacts, exchanges)

        self.assertEqual(result['views_before_contact']['mean'], 2.0)
        self.assertEqual(result['views_before_exchange']['mean'], 3.0)
        self.assertEqual(result['views_before_exchange']['total_events'], 3)

    def test_median_and_p75_across_users(self):
        views = (
            [view('u1', 'a', 1)] +
            [view('u2', m, 1) for m in ('a', 'b', 'c')] +
            [view('u3', m, 1) for m in ('a', 'b', 'c', 'd', 'e')] +
            [view('u4', m, 1) for m in ('a', 'b', 'c', 'd', 'e', 'f', 'g')]
        )
        contacts = [view(u, 'x', 2) for u in ('u1', 'u2', 'u3', 'u4')]

        result = calculate_buyer_journey_metrics(views, contacts, [])['views_before_contact']

        self.assertEqual(result['mean'], 4.0)
        self.assertEqual(result['median'], 4.0)
        self.assertEqual(result['p75'], 5.5)
        self.assertEqual(result['total_users_analyzed'], 4)
