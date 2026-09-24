import json
from unittest.mock import MagicMock, patch

from django.db import ProgrammingError
from django.test import RequestFactory, SimpleTestCase

from .views import meeting_point_usage


class MeetingPointUsageValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def get(self, hour):
        return meeting_point_usage(self.factory.get('/analytics/meeting-points/', {'hour': hour}))

    def test_rejects_hours_outside_the_day(self):
        for hour in ['24', '-1', '99']:
            with self.subTest(hour=hour):
                self.assertEqual(self.get(hour).status_code, 400)

    def test_rejects_non_integer_hours(self):
        for hour in ['abc', '7.5', '']:
            with self.subTest(hour=hour):
                self.assertEqual(self.get(hour).status_code, 400)


class MeetingPointUsageMissingTablesTests(SimpleTestCase):
    def test_answers_empty_instead_of_failing_before_the_migration(self):
        query = MagicMock()
        query.filter.return_value = query
        query.annotate.return_value = query
        query.values.return_value = query
        query.order_by.return_value = query
        query.__iter__.side_effect = ProgrammingError('relation "MeetingPoint" does not exist')

        with patch('analytics.views.Exchange.objects', query), self.assertLogs('analytics.views', 'WARNING'):
            response = meeting_point_usage(RequestFactory().get('/analytics/meeting-points/', {'hour': '12'}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'time_zone': 'America/Bogota', 'hour': 12, 'available': False, 'data': []})
