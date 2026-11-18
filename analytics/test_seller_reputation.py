from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase
from .seller_reputation import summarize_seller_reputation

START = datetime(2026, 11, 1, tzinfo=timezone.utc)


def listing(listing_id, seller_id, status='AVAILABLE'):
    return {'id': listing_id, 'seller_id': seller_id, 'status': status, 'created_at': START}


def group(rows, key):
    return next(row for row in rows if row['group'] == key)


class SummarizeSellerReputationTests(SimpleTestCase):

    def test_empty_data_answers_zeros(self):
        result = summarize_seller_reputation([], {}, [], [])
        self.assertEqual(result['listings_total'], 0)
        self.assertEqual(result['sellers_with_reviews'], 0)
        for row in result['by_stars'] + result['by_review_count']:
            self.assertEqual(row['listings'], 0)
            self.assertEqual(row['sale_rate'], 0.0)
            self.assertIsNone(row['median_days_to_sell'])

    def test_listing_goes_to_the_group_of_its_seller_average(self):
        ratings = [{'rated_id': 'good', 'stars': 5}, {'rated_id': 'good', 'stars': 4}, {'rated_id': 'bad', 'stars': 2}]
        listings = [listing('a', 'good'), listing('b', 'bad'), listing('c', 'new')]
        result = summarize_seller_reputation(listings, {}, ratings, [])
        self.assertEqual(group(result['by_stars'], '4_5_and_up')['listings'], 1)  # 4.5 promedio
        self.assertEqual(group(result['by_stars'], 'below_3')['listings'], 1)
        self.assertEqual(group(result['by_stars'], 'no_reviews')['listings'], 1)
        self.assertEqual(group(result['by_review_count'], '1_2')['listings'], 2)
        self.assertEqual(group(result['by_review_count'], 'none')['listings'], 1)
        self.assertEqual(result['sellers_with_reviews'], 2)

    def test_contacts_count_distinct_buyers_per_listing(self):
        contacts = [
            {'material_id': 'a', 'buyer_id': 'x'},
            {'material_id': 'a', 'buyer_id': 'x'},  # el mismo comprador dos veces cuenta una
            {'material_id': 'a', 'buyer_id': 'y'},
        ]
        result = summarize_seller_reputation([listing('a', 's'), listing('b', 's')], {}, [], contacts)
        row = group(result['by_stars'], 'no_reviews')
        self.assertEqual(row['contacted'], 1)
        self.assertEqual(row['contact_rate'], 0.5)
        self.assertEqual(row['buyers_per_listing'], 1.0)

    def test_sale_rate_and_median_days_use_completed_exchanges(self):
        ratings = [{'rated_id': 's', 'stars': 4}]
        listings = [listing('a', 's', 'SOLD'), listing('b', 's', 'SOLD'), listing('c', 's'), listing('d', 's')]
        completed = {'a': START + timedelta(days=2), 'b': START + timedelta(days=4)}
        row = group(summarize_seller_reputation(listings, completed, ratings, [])['by_stars'], '4_to_4_5')
        self.assertEqual(row['sold'], 2)
        self.assertEqual(row['sale_rate'], 0.5)
        self.assertEqual(row['median_days_to_sell'], 3.0)

    def test_sold_without_exchange_date_counts_as_sold_but_not_in_days(self):
        row = group(summarize_seller_reputation([listing('a', 's', 'SOLD')], {}, [], [])['by_stars'], 'no_reviews')
        self.assertEqual(row['sold'], 1)
        self.assertIsNone(row['median_days_to_sell'])

    def test_sellers_are_counted_once_per_group(self):
        result = summarize_seller_reputation([listing('a', 's'), listing('b', 's')], {}, [], [])
        self.assertEqual(group(result['by_stars'], 'no_reviews')['sellers'], 1)