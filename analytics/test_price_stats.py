import json
from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .views import MIN_PRICE_SAMPLES, calculate_price_stats, price_stats


class CalculatePriceStatsTestCase(SimpleTestCase):

    def test_no_sales_answers_zeros(self):
        self.assertEqual(
            calculate_price_stats([]),
            {'sample_size': 0, 'p25': 0.0, 'median': 0.0, 'p75': 0.0},
        )

    def test_quartiles_with_linear_interpolation(self):
        result = calculate_price_stats([10, 20, 30, 40, 50])

        self.assertEqual(result, {'sample_size': 5, 'p25': 20.0, 'median': 30.0, 'p75': 40.0})

    def test_tukey_fences_drop_high_outlier(self):
        result = calculate_price_stats([100, 102, 104, 106, 108, 5000])

        self.assertEqual(result['sample_size'], 5)
        self.assertEqual(result['median'], 104.0)

    def test_tukey_fences_drop_low_outlier(self):
        result = calculate_price_stats([1, 100, 102, 104, 106, 108])

        self.assertEqual(result['sample_size'], 5)
        self.assertEqual(result['p25'], 102.0)

    def test_accepts_decimal_prices(self):
        result = calculate_price_stats([Decimal('10.50'), Decimal('20.50'), Decimal('30.50')])

        self.assertEqual(result['median'], 20.5)

    def test_fewer_than_four_samples_are_not_filtered(self):
        self.assertEqual(calculate_price_stats([10, 5000])['sample_size'], 2)


class FakeSales:
    """Stands in for the Exchange queryset: returns canned prices and narrows by condition."""

    def __init__(self, prices, condition_prices=None):
        self.prices = prices
        self.condition_prices = condition_prices

    def filter(self, **kwargs):
        if 'material__condition' in kwargs:
            return FakeSales(self.condition_prices)
        return self

    def count(self):
        return len(self.prices)

    def values_list(self, *args, **kwargs):
        return self.prices


class PriceStatsViewTestCase(SimpleTestCase):

    def call(self, params, sales):
        with patch('analytics.views.Exchange.objects') as manager:
            manager.filter.return_value = sales
            response = price_stats(RequestFactory().get('/analytics/price-stats/', params))
        return response.status_code, json.loads(response.content)

    def test_category_is_required(self):
        status, body = self.call({}, FakeSales([]))

        self.assertEqual(status, 400)
        self.assertIn('error', body)

    def test_invalid_category_is_rejected(self):
        status, _ = self.call({'category': 'CARS'}, FakeSales([]))

        self.assertEqual(status, 400)

    def test_invalid_condition_is_rejected(self):
        status, _ = self.call({'category': 'BOOKS', 'condition': 'BROKEN'}, FakeSales([]))

        self.assertEqual(status, 400)

    def test_category_without_sales_answers_zeros(self):
        status, body = self.call({'category': 'BOOKS'}, FakeSales([]))

        self.assertEqual(status, 200)
        self.assertEqual(body['sample_size'], 0)
        self.assertEqual(body['median'], 0.0)
        self.assertEqual(body['scope'], 'category')
        self.assertIsNone(body['condition'])

    def test_enough_sales_in_condition_narrows_the_scope(self):
        condition_prices = [100, 110, 120, 130, 140]
        self.assertEqual(len(condition_prices), MIN_PRICE_SAMPLES)

        _, body = self.call(
            {'category': 'BOOKS', 'condition': 'GOOD'},
            FakeSales([10, 20, 30, 40, 50, 60, 70], condition_prices),
        )

        self.assertEqual(body['scope'], 'category_condition')
        self.assertEqual(body['median'], 120.0)
        self.assertEqual(body['condition'], 'GOOD')

    def test_few_sales_in_condition_widens_to_the_category(self):
        _, body = self.call(
            {'category': 'BOOKS', 'condition': 'GOOD'},
            FakeSales([10, 20, 30, 40, 50, 60, 70], [100, 110, 120, 130]),
        )

        self.assertEqual(body['scope'], 'category')
        self.assertEqual(body['median'], 40.0)
        self.assertEqual(body['sample_size'], 7)
