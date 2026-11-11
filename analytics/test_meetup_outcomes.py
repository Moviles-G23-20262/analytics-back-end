from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from .views import summarize_meetup_outcomes

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
POINTS = {
    'library': {'name': 'Central Library lobby', 'is_monitored': True},
    'plaza': {'name': 'Student Center plaza', 'is_monitored': False},
}


def room(room_id, material='m1', buyer='b1', seller='s1'):
    return {'id': room_id, 'material_id': material, 'buyer_id': buyer, 'seller_id': seller}


def exchange(status, material='m1', buyer='b1', seller='s1'):
    return {'material_id': material, 'buyer_id': buyer, 'seller_id': seller, 'status': status}


def proposal(room_id, status, starts_at, point='library', created_at=None):
    return {
        'chat_room_id': room_id,
        'status': status,
        'starts_at': starts_at,
        'ends_at': starts_at + timedelta(hours=1),
        'created_at': created_at or starts_at - timedelta(days=1),
        'meeting_point_id': point,
    }


class SummarizeMeetupOutcomesTestCase(SimpleTestCase):

    def test_no_meetups_answers_zeros(self):
        result = summarize_meetup_outcomes([], [], [], POINTS, NOW)
        self.assertEqual(result['overall']['agreed'], 0)
        self.assertEqual(result['overall']['completion_rate'], 0.0)
        self.assertEqual(result['by_point'], [])
        self.assertEqual(result['by_hour'], [])

    def test_outcome_comes_from_the_exchange_of_the_same_chat(self):
        past = NOW - timedelta(days=3)
        rooms = [room('r1'), room('r2', material='m2'), room('r3', material='m3')]
        exchanges = [exchange('COMPLETED'), exchange('CANCELLED', material='m2')]
        proposals = [proposal('r1', 'ACCEPTED', past), proposal('r2', 'ACCEPTED', past), proposal('r3', 'ACCEPTED', past)]

        overall = summarize_meetup_outcomes(proposals, rooms, exchanges, POINTS, NOW)['overall']

        self.assertEqual((overall['agreed'], overall['completed'], overall['cancelled'], overall['not_closed']), (3, 1, 1, 1))
        self.assertEqual(overall['completion_rate'], 0.3333)

    def test_completed_wins_over_an_earlier_cancellation(self):
        past = NOW - timedelta(days=3)
        result = summarize_meetup_outcomes(
            [proposal('r1', 'ACCEPTED', past)], [room('r1')], [exchange('CANCELLED'), exchange('COMPLETED')], POINTS, NOW)
        self.assertEqual(result['overall']['completed'], 1)

    def test_exchange_of_another_buyer_does_not_count(self):
        past = NOW - timedelta(days=3)
        result = summarize_meetup_outcomes(
            [proposal('r1', 'ACCEPTED', past)], [room('r1', buyer='b1')], [exchange('COMPLETED', buyer='b2')], POINTS, NOW)
        self.assertEqual(result['overall']['not_closed'], 1)

    def test_meetups_still_to_come_are_counted_apart(self):
        result = summarize_meetup_outcomes(
            [proposal('r1', 'ACCEPTED', NOW + timedelta(days=1))], [room('r1')], [], POINTS, NOW)
        self.assertEqual(result['overall']['agreed'], 0)
        self.assertEqual(result['overall']['upcoming'], 1)

    def test_only_accepted_proposals_are_meetups(self):
        past = NOW - timedelta(days=3)
        proposals = [proposal('r1', status, past) for status in ('PENDING', 'DECLINED', 'CANCELLED')]
        result = summarize_meetup_outcomes(proposals, [room('r1')], [exchange('COMPLETED')], POINTS, NOW)
        self.assertEqual(result['overall']['agreed'], 0)

    def test_proposals_declined_or_withdrawn_before_the_agreement_are_changes(self):
        start = NOW - timedelta(days=5)
        proposals = [
            proposal('r1', 'DECLINED', start, created_at=start - timedelta(days=3)),
            proposal('r1', 'CANCELLED', start, created_at=start - timedelta(days=2)),
            proposal('r1', 'ACCEPTED', start, created_at=start - timedelta(days=1)),
            proposal('r2', 'ACCEPTED', start, created_at=start - timedelta(days=1)),
        ]
        overall = summarize_meetup_outcomes(proposals, [room('r1'), room('r2', material='m2')], [], POINTS, NOW)['overall']
        self.assertEqual(overall['average_changes_before_agreement'], 1.0)
        self.assertEqual(overall['agreed_first_try_share'], 0.5)

    def test_hour_is_the_campus_hour_of_the_meetup(self):
        bogota_noon = datetime(2026, 11, 10, 17, tzinfo=timezone.utc)
        result = summarize_meetup_outcomes([proposal('r1', 'ACCEPTED', bogota_noon)], [room('r1')], [], POINTS, NOW)
        self.assertEqual([row['hour'] for row in result['by_hour']], [12])

    def test_naive_times_from_prisma_are_read_as_utc(self):
        naive = datetime(2026, 11, 10, 17)
        result = summarize_meetup_outcomes([proposal('r1', 'ACCEPTED', naive)], [room('r1')], [], POINTS, NOW)
        self.assertEqual(result['by_hour'][0]['hour'], 12)

    def test_points_are_ranked_by_meetups_and_carry_their_rate(self):
        past = NOW - timedelta(days=3)
        rooms = [room('r1'), room('r2', material='m2'), room('r3', material='m3')]
        proposals = [
            proposal('r1', 'ACCEPTED', past, point='plaza'),
            proposal('r2', 'ACCEPTED', past, point='plaza'),
            proposal('r3', 'ACCEPTED', past, point='library'),
        ]
        by_point = summarize_meetup_outcomes(proposals, rooms, [exchange('COMPLETED')], POINTS, NOW)['by_point']
        self.assertEqual([row['name'] for row in by_point], ['Student Center plaza', 'Central Library lobby'])
        self.assertEqual(by_point[0]['completion_rate'], 0.5)
        self.assertFalse(by_point[0]['is_monitored'])
