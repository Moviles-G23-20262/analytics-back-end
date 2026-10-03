from django.test import SimpleTestCase
from django.urls import reverse

from .views import DASHBOARD_QUESTIONS


class DashboardPagesTests(SimpleTestCase):
    def test_overview_links_to_every_question(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        for q in DASHBOARD_QUESTIONS:
            with self.subTest(bq=q['number']):
                self.assertContains(response, q['question'])
                self.assertContains(response, reverse('dashboard-question', args=[q['number']]))

    def test_each_question_page_shows_its_question_and_endpoint(self):
        for q in DASHBOARD_QUESTIONS:
            with self.subTest(bq=q['number']):
                response = self.client.get(reverse('dashboard-question', args=[q['number']]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, q['question'])
                self.assertContains(response, reverse(q['endpoint']))

    def test_unimplemented_questions_have_no_page(self):
        for number in [1, 3, 8, 9, 10, 11, 13, 14]:
            with self.subTest(bq=number):
                self.assertEqual(self.client.get(f'/dash-board/bq{number}/').status_code, 404)

    def test_dash_board_path_is_served_at_the_requested_url(self):
        self.assertEqual(reverse('dashboard'), '/dash-board/')
