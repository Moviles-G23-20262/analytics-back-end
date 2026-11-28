from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from .views import normalize_course, summarize_course_demand


def listing(id, course, status='AVAILABLE'):
    return {'id': id, 'course_code': course, 'status': status}


def chat(material, buyer):
    return {'material_id': material, 'buyer_id': buyer}


def save(material, user):
    return {'material_id': material, 'user_id': user}


class CourseDemandTestCase(SimpleTestCase):

    def course(self, result, code):
        return next(c for c in result['courses'] if c['course'] == code)

    def test_no_data_answers_zeros(self):
        result = summarize_course_demand([], [], [])

        self.assertEqual(result['total_courses'], 0)
        self.assertEqual(result['shortage_courses'], 0)
        self.assertEqual(result['courses'], [])

    def test_course_codes_are_compared_without_spaces_dashes_or_case(self):
        self.assertEqual(normalize_course(' mate 1203 '), 'MATE1203')
        self.assertEqual(normalize_course('MATE-1203'), 'MATE1203')
        self.assertIsNone(normalize_course('   '))
        self.assertIsNone(normalize_course(None))

        result = summarize_course_demand([listing('a', 'mate 1203'), listing('b', 'MATE-1203')], [], [])
        self.assertEqual(self.course(result, 'MATE1203')['listings'], 2)

    def test_listings_without_a_course_are_counted_apart(self):
        result = summarize_course_demand([listing('a', None), listing('b', ''), listing('c', 'FISI1018')], [], [])

        self.assertEqual(result['listings_without_course'], 2)
        self.assertEqual(result['total_courses'], 1)

    def test_only_available_listings_count_as_stock(self):
        result = summarize_course_demand(
            [listing('a', 'ISIS1105'), listing('b', 'ISIS1105', 'SOLD'), listing('c', 'ISIS1105', 'RESERVED')], [], [])

        row = self.course(result, 'ISIS1105')
        self.assertEqual((row['listings'], row['available'], row['sold']), (3, 1, 1))

    def test_a_student_counts_once_per_course_whether_they_chat_or_save(self):
        result = summarize_course_demand(
            [listing('a', 'MATE1203'), listing('b', 'MATE1203')],
            [chat('a', 'ana'), chat('b', 'ana'), chat('a', 'luis')],
            [save('a', 'ana'), save('b', 'sofi')],
        )

        row = self.course(result, 'MATE1203')
        self.assertEqual(row['buyers_in_chat'], 2)
        self.assertEqual(row['wishlist_saves'], 2)
        self.assertEqual(row['interested_students'], 3)  # ana, luis, sofi
        self.assertEqual(row['demand_per_listing'], 1.5)
        self.assertEqual(row['gap'], 1)
        self.assertEqual(row['status'], 'balanced')

    def test_shortage_when_nothing_is_on_sale_or_two_per_listing(self):
        result = summarize_course_demand(
            [listing('a', 'SOLDOUT', 'SOLD'), listing('b', 'BUSY'), listing('c', 'CALM'), listing('d', 'QUIET')],
            [chat('a', 'u1'), chat('b', 'u1'), chat('b', 'u2'), chat('c', 'u3')],
            [],
        )

        self.assertEqual(self.course(result, 'SOLDOUT')['status'], 'shortage')
        self.assertIsNone(self.course(result, 'SOLDOUT')['demand_per_listing'])
        self.assertEqual(self.course(result, 'BUSY')['status'], 'shortage')
        self.assertEqual(self.course(result, 'CALM')['status'], 'balanced')
        self.assertEqual(self.course(result, 'QUIET')['status'], 'no_demand')
        self.assertEqual(result['shortage_courses'], 2)
        self.assertEqual(result['courses_without_demand'], 1)

    def test_courses_are_ranked_by_the_gap_between_demand_and_supply(self):
        result = summarize_course_demand(
            [listing('a', 'A'), listing('b', 'B'), listing('c', 'C', 'SOLD')],
            [chat('a', 'u1'), chat('b', 'u1'), chat('b', 'u2'), chat('c', 'u1'), chat('c', 'u2'), chat('c', 'u3')],
            [],
        )

        self.assertEqual([c['course'] for c in result['courses']], ['C', 'B', 'A'])

    def test_limit_keeps_the_top_courses_but_totals_count_all(self):
        result = summarize_course_demand([listing(str(i), f'C{i}') for i in range(5)], [], [], limit=2)

        self.assertEqual(len(result['courses']), 2)
        self.assertEqual(result['total_courses'], 5)


class CourseDemandEndpointTestCase(SimpleTestCase):

    @patch('analytics.views.WishlistItem.objects')
    @patch('analytics.views.ChatRoom.objects')
    @patch('analytics.views.Material.objects')
    def test_endpoint_returns_the_summary(self, materials, chat_rooms, wishlist):
        materials.values.return_value = [listing('a', 'MATE1203')]
        chat_rooms.values.return_value = [chat('a', 'ana')]
        wishlist.values.return_value = [save('a', 'luis')]

        response = self.client.get(reverse('course-demand'), {'limit': '5'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reverse('course-demand'), '/analytics/course-demand/')
        body = response.json()
        self.assertEqual(body['courses'][0]['course'], 'MATE1203')
        self.assertEqual(body['courses'][0]['interested_students'], 2)
