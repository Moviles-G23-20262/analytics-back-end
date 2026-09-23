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
