from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from .views import summarize_time_to_sell

LISTED = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def sale(days, category='BOOKS'):
    return {'category': category, 'listed_at': LISTED, 'completed_at': LISTED + timedelta(days=days)}


class SummarizeTimeToSellTestCase(SimpleTestCase):

    def test_no_sales_answers_zeros(self):
        result = summarize_time_to_sell([])

        self.assertEqual(result['sold_listings'], 0)
        self.assertEqual(result['days_to_sell']['mean'], 0.0)
        self.assertTrue(all(b['sold'] == 0 for b in result['histogram']))

    def test_average_and_median_days(self):
        result = summarize_time_to_sell([sale(1), sale(2), sale(9)])

        self.assertEqual(result['sold_listings'], 3)
        self.assertEqual(result['days_to_sell']['mean'], 4.0)
        self.assertEqual(result['days_to_sell']['median'], 2.0)
        self.assertEqual(result['days_to_sell']['max'], 9.0)

    def test_fractions_of_a_day_are_kept(self):
        result = summarize_time_to_sell([sale(0.5)])

        self.assertEqual(result['days_to_sell']['mean'], 0.5)

    def test_histogram_buckets(self):
        result = summarize_time_to_sell([sale(0.2), sale(1), sale(5), sale(13.9), sale(45)])

        counts = {b['bucket']: b['sold'] for b in result['histogram']}
        self.assertEqual(counts, {
            'Under 1 day': 1, '1-3 days': 1, '3-7 days': 1, '1-2 weeks': 1, '2-4 weeks': 0, '30+ days': 1,
        })

    def test_missing_or_impossible_dates_are_skipped(self):
        broken = {'category': 'BOOKS', 'listed_at': LISTED, 'completed_at': None}
        before_listing = sale(-2)

        result = summarize_time_to_sell([sale(3), broken, before_listing])

        self.assertEqual(result['sold_listings'], 1)
        self.assertEqual(result['skipped'], 2)

    def test_categories_are_sorted_from_fastest_to_slowest(self):
        result = summarize_time_to_sell([sale(10, 'FURNITURE'), sale(2, 'CALCULATORS'), sale(4, 'CALCULATORS')])

        self.assertEqual([c['category'] for c in result['by_category']], ['CALCULATORS', 'FURNITURE'])
        self.assertEqual(result['by_category'][0]['median_days'], 3.0)

class TimeToSellViewTestCase(SimpleTestCase):

    def test_view_returns_expected_json(self):
        from unittest.mock import patch
        import json
        with patch('analytics.views.Exchange.objects') as manager:
            manager.filter.return_value.values.return_value = [
                {'category': 'BOOKS', 'listed_at': LISTED, 'completed_at': LISTED + timedelta(days=2)},
            ]
            response = self.client.get('/analytics/time-to-sell/')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['sold_listings'], 1)
            self.assertEqual(data['days_to_sell']['mean'], 2.0)

    def test_view_alias_time_to_sold(self):
        from unittest.mock import patch
        import json
        with patch('analytics.views.Exchange.objects') as manager:
            manager.filter.return_value.values.return_value = []
            response = self.client.get('/analytics/time-to-sold/')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['sold_listings'], 0)

