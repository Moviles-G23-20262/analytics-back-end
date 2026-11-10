import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.db import ProgrammingError
from django.test import SimpleTestCase
from django.urls import reverse

from .models import ExchangeStatus, MaterialCategory, MaterialStatus
from .views import SURVIVAL_CHECKPOINTS, summarize_dead_listings

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=dt_timezone.utc)


def make_listing(
    mat_id,
    *,
    title='Calculus Stewart',
    category=MaterialCategory.BOOKS,
    price=50000,
    status=MaterialStatus.AVAILABLE,
    days_old=20,
    sold_after_days=None,
    photos=3,
    contacts=2,
    seller_id='seller-1',
    seller_rating=4.8,
):
    created = NOW - timedelta(days=days_old)
    sold_at = (created + timedelta(days=sold_after_days)) if sold_after_days is not None else None
    updated_at = sold_at or created
    return {
        'id': mat_id,
        'title': title,
        'category': category,
        'price': Decimal(str(price)),
        'condition': 'GOOD',
        'status': status,
        'image_urls': [f'https://cdn.example/{mat_id}-{i}.jpg' for i in range(photos)],
        'seller_id': seller_id,
        'seller_rating': seller_rating,
        'contacts': contacts,
        'created_at': created,
        'updated_at': updated_at,
        'sold_at': sold_at,
    }


class SummarizeDeadListingsTestCase(SimpleTestCase):

    def test_empty_dataset_returns_safe_defaults(self):
        result = summarize_dead_listings([], NOW)

        self.assertEqual(result['summary']['total_listings'], 0)
        self.assertEqual(result['summary']['dead_listings'], 0)
        self.assertEqual(result['summary']['dead_share'], 0.0)
        self.assertEqual(result['clusters'], [])
        self.assertEqual(result['dead_listings'], [])
        self.assertEqual(result['at_risk_listings'], [])
        self.assertIsNone(result['seller_summary'])
        self.assertEqual([p['day'] for p in result['survival_curve']], SURVIVAL_CHECKPOINTS)
        self.assertTrue(all(p['survival_rate'] == 0.0 for p in result['survival_curve']))

    def test_lifecycle_classification_sold_reserved_fresh_dead_and_skipped(self):
        rows = [
            make_listing('m-sold-status', status=MaterialStatus.SOLD, days_old=15, sold_after_days=5),
            make_listing('m-sold-exchange', status=MaterialStatus.AVAILABLE, days_old=18, photos=2),
            make_listing('m-reserved', status=MaterialStatus.RESERVED, days_old=25),
            make_listing('m-fresh', status=MaterialStatus.AVAILABLE, days_old=4),
            make_listing('m-dead', status=MaterialStatus.AVAILABLE, days_old=22, photos=0, contacts=0),
            {'id': 'm-missing-created', 'title': 'Broken', 'price': Decimal('1000'), 'created_at': None},
        ]
        exchanges = [
            {'material_id': 'm-sold-exchange', 'status': ExchangeStatus.COMPLETED, 'completed_at': NOW - timedelta(days=12)},
        ]

        result = summarize_dead_listings(rows, NOW, stale_days=14, sold_exchanges=exchanges)
        summary = result['summary']

        self.assertEqual(summary['total_listings'], 5)
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(summary['sold_listings'], 2)
        self.assertEqual(summary['reserved_listings'], 1)
        self.assertEqual(summary['active_fresh_listings'], 1)
        self.assertEqual(summary['dead_listings'], 1)
        self.assertAlmostEqual(summary['dead_share'], 0.2, places=4)
        self.assertEqual([item['id'] for item in result['dead_listings']], ['m-dead'])

    def test_naive_datetimes_are_treated_as_utc(self):
        naive_created = datetime(2026, 10, 20, 12, 0)  # 21 days before NOW (no tzinfo)
        row = {
            'id': 'm-naive',
            'title': 'Physics Resnick',
            'category': MaterialCategory.BOOKS,
            'price': Decimal('40000'),
            'status': MaterialStatus.AVAILABLE,
            'image_urls': ['a.jpg'],
            'seller_id': 's1',
            'seller_rating': 4.0,
            'contacts': 0,
            'created_at': naive_created,
            'updated_at': naive_created,
        }

        result = summarize_dead_listings([row], NOW, stale_days=14)

        self.assertEqual(result['summary']['dead_listings'], 1)
        self.assertEqual(result['summary']['median_days_active_dead'], 21.0)

    def test_survival_curve_is_monotone_and_right_censored(self):
        rows = [
            make_listing('s1', status=MaterialStatus.SOLD, days_old=20, sold_after_days=2),
            make_listing('s2', status=MaterialStatus.SOLD, days_old=25, sold_after_days=10),
            make_listing('d1', status=MaterialStatus.AVAILABLE, days_old=35, photos=0, contacts=0),
            make_listing('f1', status=MaterialStatus.AVAILABLE, days_old=5),
        ]

        curve = summarize_dead_listings(rows, NOW)['survival_curve']

        self.assertEqual(curve[0]['day'], 0)
        self.assertEqual(curve[0]['survival_rate'], 1.0)
        self.assertEqual(curve[0]['at_risk'], 4)
        for prev, nxt in zip(curve, curve[1:]):
            self.assertGreaterEqual(prev['survival_rate'], nxt['survival_rate'])
            self.assertGreaterEqual(prev['at_risk'], nxt['at_risk'])
            self.assertLessEqual(prev['sold_cumulative'], nxt['sold_cumulative'])

        day14 = next(p for p in curve if p['day'] == 14)
        self.assertEqual(day14['sold_cumulative'], 2)
        self.assertAlmostEqual(day14['survival_rate'], 0.375, places=4)

    def test_cohort_comparisons_and_breakdowns(self):
        rows = [
            # Three fast, fair-priced sold benchmarks with 3 photos and strong ratings
            make_listing('s1', price=40000, status=MaterialStatus.SOLD, days_old=20, sold_after_days=3, photos=3, contacts=4, seller_rating=4.9),
            make_listing('s2', price=40000, status=MaterialStatus.SOLD, days_old=22, sold_after_days=4, photos=4, contacts=3, seller_rating=4.8),
            make_listing('s3', price=40000, status=MaterialStatus.SOLD, days_old=24, sold_after_days=5, photos=3, contacts=2, seller_rating=4.6),
            # Two overpriced dead listings with 0/1 photos and low/unrated sellers
            make_listing('d1', price=70000, status=MaterialStatus.AVAILABLE, days_old=30, photos=0, contacts=0, seller_rating=0.0, category=MaterialCategory.CALCULATORS),
            make_listing('d2', price=60000, status=MaterialStatus.AVAILABLE, days_old=18, photos=1, contacts=0, seller_rating=3.0),
        ]

        result = summarize_dead_listings(rows, NOW, stale_days=14)
        dead_cmp = result['comparisons']['dead']
        sold_cmp = result['comparisons']['sold']

        self.assertEqual(dead_cmp['count'], 2)
        self.assertEqual(sold_cmp['count'], 3)
        self.assertGreater(dead_cmp['median_days'], sold_cmp['median_days'])
        self.assertGreater(dead_cmp['zero_contact_share'], sold_cmp['zero_contact_share'])
        self.assertLess(dead_cmp['mean_photos'], sold_cmp['mean_photos'])

        by_photos = {b['key']: b for b in result['breakdowns']['by_photos']}
        self.assertEqual(by_photos['No photos']['dead'], 1)
        self.assertEqual(by_photos['3+ photos']['sold'], 3)

        by_rating = {b['key']: b for b in result['breakdowns']['by_seller_rating']}
        self.assertEqual(by_rating['unrated']['dead'], 1)
        self.assertEqual(by_rating['low']['dead'], 1)
        self.assertEqual(by_rating['top']['sold'], 3)

        by_cat = {b['category']: b for b in result['breakdowns']['by_category']}
        self.assertEqual(by_cat[MaterialCategory.CALCULATORS]['dead_rate'], 1.0)
        self.assertEqual(by_cat[MaterialCategory.BOOKS]['dead'], 1)

    def test_kmeans_clustering_is_deterministic_and_handles_edge_cases(self):
        # Sold benchmarks establish a category median price of 50,000.
        benchmarks = [
            make_listing(f'bench-{i}', price=50000, status=MaterialStatus.SOLD, days_old=10, sold_after_days=2)
            for i in range(3)
        ]
        # Two clearly separated dead archetypes (high price + 0 photos vs fair price + unrated + long stale).
        dead_group_a = [
            make_listing(f'da-{i}', price=90000, days_old=20 + i, photos=0, contacts=0, seller_rating=4.5)
            for i in range(3)
        ]
        dead_group_b = [
            make_listing(f'db-{i}', price=50000, days_old=48 + i, photos=3, contacts=0, seller_rating=0.0)
            for i in range(3)
        ]

        ordered_res = summarize_dead_listings(benchmarks + dead_group_a + dead_group_b, NOW)
        reversed_res = summarize_dead_listings(list(reversed(benchmarks + dead_group_a + dead_group_b)), NOW)

        self.assertGreaterEqual(len(ordered_res['clusters']), 2)
        self.assertLessEqual(len(ordered_res['clusters']), 4)
        self.assertEqual(sum(c['count'] for c in ordered_res['clusters']), 6)
        self.assertEqual(ordered_res['clusters'], reversed_res['clusters'])

        # Identical feature vectors must not fail due to zero variance.
        identical = [
            make_listing(f'id-{i}', price=50000, days_old=20, photos=1, contacts=0, seller_rating=4.0)
            for i in range(3)
        ]
        identical_res = summarize_dead_listings(identical, NOW)
        self.assertEqual(len(identical_res['clusters']), 1)
        self.assertEqual(identical_res['clusters'][0]['count'], 3)

    def test_seller_filter_and_suggested_price_drop(self):
        seller_id = '11111111-1111-1111-1111-111111111111'
        other_id = '22222222-2222-2222-2222-222222222222'
        rows = [
            make_listing('b1', price=40000, status=MaterialStatus.SOLD, days_old=12, sold_after_days=3, seller_id=other_id),
            make_listing('b2', price=40000, status=MaterialStatus.SOLD, days_old=12, sold_after_days=4, seller_id=other_id),
            make_listing('b3', price=40000, status=MaterialStatus.SOLD, days_old=12, sold_after_days=5, seller_id=other_id),
            make_listing('other-dead', price=90000, days_old=30, photos=0, contacts=0, seller_id=other_id),
            make_listing('mine-overpriced-dead', price=70000, days_old=22, photos=0, contacts=0, seller_id=seller_id, seller_rating=3.2),
            make_listing('mine-healthy-fresh', price=39000, days_old=1, photos=4, contacts=3, seller_id=seller_id, seller_rating=4.9),
        ]

        result = summarize_dead_listings(rows, NOW, stale_days=14, seller_id=seller_id)

        # Marketplace summary remains global while at_risk_listings and seller_summary scope to seller_id.
        self.assertEqual(result['summary']['dead_listings'], 2)
        self.assertEqual(result['seller_summary']['seller_id'], seller_id)
        self.assertEqual(result['seller_summary']['dead_listings'], 1)
        self.assertEqual(result['seller_summary']['at_risk_count'], 1)
        self.assertEqual(result['seller_summary']['healthy_listings'], 1)

        flagged = result['at_risk_listings']
        self.assertEqual([item['id'] for item in flagged], ['mine-overpriced-dead'])
        item = flagged[0]
        self.assertTrue(item['is_dead'])
        self.assertEqual(item['risk_level'], 'high')
        self.assertIsNotNone(item['suggested_price'])
        self.assertLess(item['suggested_price'], item['price'])
        self.assertGreater(item['recommended_drop_pct'], 0.0)
        self.assertIn('Drop price', item['recommendation'])


class DeadListingsEndpointTestCase(SimpleTestCase):

    @patch('analytics.views.Exchange.objects')
    @patch('analytics.views.Material.objects')
    def test_endpoint_returns_summary_and_supports_params(self, mat_objects, ex_objects):
        seller_uuid = uuid.UUID('11111111-1111-1111-1111-111111111111')
        mat_objects.annotate.return_value.values.return_value = [
            make_listing('m1', price=80000, days_old=25, photos=0, contacts=0, seller_id=seller_uuid),
            make_listing('m2', price=40000, status=MaterialStatus.SOLD, days_old=10, sold_after_days=2, seller_id='other'),
        ]
        ex_objects.filter.return_value.values.return_value = []

        url = reverse('dead-listings')
        self.assertEqual(url, '/analytics/dead-listings/')

        res = self.client.get(f'{url}?staleDays=21&sellerId={str(seller_uuid).upper()}')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['summary']['stale_days'], 21)
        self.assertEqual(body['summary']['dead_listings'], 1)
        self.assertEqual(body['seller_summary']['seller_id'], str(seller_uuid))
        self.assertEqual(len(body['at_risk_listings']), 1)

    def test_invalid_query_parameters_return_400(self):
        url = reverse('dead-listings')
        self.assertEqual(self.client.get(f'{url}?staleDays=0').status_code, 400)
        self.assertEqual(self.client.get(f'{url}?staleDays=abc').status_code, 400)
        self.assertEqual(self.client.get(f'{url}?staleDays=366').status_code, 400)
        self.assertEqual(self.client.get(f'{url}?sellerId=not-a-uuid').status_code, 400)

    @patch('analytics.views.Exchange.objects')
    @patch('analytics.views.Material.objects')
    def test_endpoint_survives_exchange_programming_error(self, mat_objects, ex_objects):
        mat_objects.annotate.return_value.values.return_value = [
            make_listing('m1', price=50000, days_old=20, photos=1, contacts=0),
        ]
        ex_objects.filter.side_effect = ProgrammingError('column missing')

        res = self.client.get(reverse('dead-listings'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['summary']['dead_listings'], 1)
