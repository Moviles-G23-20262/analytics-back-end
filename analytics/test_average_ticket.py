from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import resolve

from .views import average_ticket, completed_sales_by_condition, summarize_average_ticket


def group(condition, total, sales):
    # One row of the GROUP BY Material.condition query.
    return {'condition': condition, 'total': Decimal(total), 'sales': sales}


class SummarizeAverageTicketTestCase(SimpleTestCase):

    def test_no_completed_sales(self):
        self.assertEqual(summarize_average_ticket([]), {'globalAverage': None, 'byCondition': {}})

    def test_global_and_per_condition_averages(self):
        result = summarize_average_ticket([
            group('NEW', '120000', 2),   # 60 000 each
            group('GOOD', '90000', 3),   # 30 000 each
        ])

        self.assertEqual(result, {'globalAverage': 42000, 'byCondition': {'NEW': 60000, 'GOOD': 30000}})

    def test_global_average_is_weighted_by_sales_not_by_condition(self):
        result = summarize_average_ticket([group('NEW', '100000', 1), group('FAIR', '90000', 9)])

        # (100 000 + 90 000) / 10 sales, not the mean of 100 000 and 10 000.
        self.assertEqual(result['globalAverage'], 19000)

    def test_sales_without_condition_count_only_in_the_global_average(self):
        result = summarize_average_ticket([group('LIKE_NEW', '50000', 1), group(None, '10000', 1)])

        self.assertEqual(result['globalAverage'], 30000)
        self.assertEqual(result['byCondition'], {'LIKE_NEW': 50000})

    def test_conditions_follow_the_enum_order(self):
        result = summarize_average_ticket([
            group('FAIR', '1000', 1), group('NEW', '4000', 1), group('GOOD', '2000', 1), group('LIKE_NEW', '3000', 1),
        ])

        self.assertEqual(list(result['byCondition']), ['NEW', 'LIKE_NEW', 'GOOD', 'FAIR'])

    def test_averages_are_rounded_to_whole_pesos(self):
        result = summarize_average_ticket([group('GOOD', '100000.50', 3)])

        self.assertEqual(result['byCondition']['GOOD'], 33334)
        self.assertIsInstance(result['globalAverage'], int)

    def test_route(self):
        self.assertIs(resolve('/analytics/average-ticket/').func, average_ticket)


class AverageTicketQueryTestCase(SimpleTestCase):

    def test_query_joins_material_filters_completed_and_groups_by_condition(self):
        sql = str(completed_sales_by_condition().query)

        self.assertIn('INNER JOIN "Material"', sql)
        self.assertIn('"Exchange"."status" = COMPLETED', sql)
        # Django may group by position: column 1 is Material.condition.
        self.assertTrue(sql.startswith('SELECT "Material"."condition" AS "condition"'), sql)
        self.assertRegex(sql, r'GROUP BY (1|"Material"\."condition")$')
