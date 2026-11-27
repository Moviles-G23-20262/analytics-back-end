from django.test import SimpleTestCase

from .major_activity import summarize_major_activity


class SummarizeMajorActivityTests(SimpleTestCase):
    def test_empty_data_returns_zero_totals(self):
        result = summarize_major_activity([], [], [], [])
        self.assertEqual(result['users_total'], 0)
        self.assertEqual(result['listings_total'], 0)
        self.assertEqual(result['inquiries_total'], 0)
        self.assertEqual(result['completed_exchanges_total'], 0)
        self.assertEqual(result['by_major'], [])
        self.assertEqual(result['by_faculty'], [])

    def test_aggregates_real_listings_inquiries_and_completed_exchanges_by_major_and_faculty(self):
        users = [
            {'id': 'u1', 'major': 'Systems Engineering', 'faculty': 'Engineering'},
            {'id': 'u2', 'major': 'systems engineering ', 'faculty': 'Engineering'},
            {'id': 'u3', 'major': 'Economics', 'faculty': 'Economics'},
            {'id': 'u4', 'major': 'Design', 'faculty': None},
        ]
        listings = [
            {'id': 'm1', 'seller_id': 'u1', 'status': 'SOLD'},
            {'id': 'm2', 'seller_id': 'u2', 'status': 'AVAILABLE'},
            {'id': 'm3', 'seller_id': 'u3', 'status': 'SOLD'},
        ]
        chat_rooms = [
            {'id': 'c1', 'material_id': 'm1', 'buyer_id': 'u3', 'seller_id': 'u1'},
            {'id': 'c2', 'material_id': 'm2', 'buyer_id': 'u3', 'seller_id': 'u2'},
            {'id': 'c3', 'material_id': 'm2', 'buyer_id': 'u4', 'seller_id': 'u2'},
        ]
        exchanges = [
            {'material_id': 'm1', 'buyer_id': 'u3', 'seller_id': 'u1', 'status': 'COMPLETED'},
            {'material_id': 'm2', 'buyer_id': 'u4', 'seller_id': 'u2', 'status': 'CANCELLED'},
        ]

        result = summarize_major_activity(users, listings, chat_rooms, exchanges)

        self.assertEqual(result['users_total'], 4)
        self.assertEqual(result['listings_total'], 3)
        self.assertEqual(result['inquiries_total'], 3)
        # m1 counted once (both COMPLETED exchange and SOLD status) + m3 (SOLD status) = 2
        self.assertEqual(result['completed_exchanges_total'], 2)
        self.assertEqual(result['majors_active'], 2)

        top = result['by_major'][0]
        self.assertEqual(top['name'], 'Systems Engineering')
        self.assertEqual(top['faculty'], 'Engineering')
        self.assertEqual(top['users'], 2)
        self.assertEqual(top['active_sellers'], 2)
        self.assertEqual(top['listings'], 2)
        self.assertEqual(top['buyer_inquiries'], 3)
        self.assertEqual(top['completed_exchanges'], 1)
        self.assertEqual(top['conversion_rate'], 0.5)

        econ = result['by_major'][1]
        self.assertEqual(econ['name'], 'Economics')
        self.assertEqual(econ['completed_exchanges'], 1)
        self.assertEqual(econ['conversion_rate'], 1.0)

        design = result['by_major'][2]
        self.assertEqual(design['name'], 'Design')
        self.assertEqual(design['faculty'], 'Unspecified')
        self.assertEqual(design['listings'], 0)

    def test_bq18_dashboard_route_renders(self):
        response = self.client.get('/dash-board/bq18/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BQ18')
        self.assertContains(response, '/analytics/major-activity/')
