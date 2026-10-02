from datetime import datetime, timezone
from django.test import SimpleTestCase

from .views import (
    calculate_chat_to_meeting_metrics,
    map_events_to_chat_rooms,
    map_exchanges_to_chat_rooms,
)


def at(hour, minute=0, day=1):
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


def msg(room, hour, minute=0):
    return {'chat_room_id': room, 'created_at': at(hour, minute)}


class ChatToMeetingPointMetricsTestCase(SimpleTestCase):

    def test_no_data_answers_zeros(self):
        result = calculate_chat_to_meeting_metrics([], [], {})

        self.assertEqual(result['conversations_analyzed'], 0)
        self.assertEqual(result['messages_before_agreement']['mean'], 0.0)
        self.assertEqual(result['messages_before_agreement']['histogram'], [])
        self.assertEqual(result['minutes_to_agreement']['boxplot']['median'], 0.0)

    def test_counts_messages_and_minutes_up_to_the_agreement(self):
        messages = [msg('r1', 10, 0), msg('r1', 10, 5), msg('r1', 10, 30)]

        result = calculate_chat_to_meeting_metrics(['r1'], messages, {'r1': at(10, 30)})

        self.assertEqual(result['conversations_analyzed'], 1)
        self.assertEqual(result['messages_before_agreement']['mean'], 3.0)
        self.assertEqual(result['minutes_to_agreement']['mean'], 30.0)

    def test_messages_after_the_agreement_are_ignored_and_the_cut_is_inclusive(self):
        messages = [msg('r1', 10, 0), msg('r1', 10, 10), msg('r1', 11, 0)]

        result = calculate_chat_to_meeting_metrics(['r1'], messages, {'r1': at(10, 10)})

        self.assertEqual(result['messages_before_agreement']['mean'], 2.0)
        self.assertEqual(result['minutes_to_agreement']['mean'], 10.0)

    def test_chats_without_agreement_are_reported_apart(self):
        messages = [msg('r1', 10), msg('r2', 10)]

        result = calculate_chat_to_meeting_metrics(['r1', 'r2'], messages, {'r1': at(10, 20)})

        self.assertEqual(result['conversations_analyzed'], 1)
        self.assertEqual(result['conversations_without_agreement'], 1)

    def test_agreement_without_prior_messages_is_not_averaged(self):
        messages = [msg('r1', 12)]

        result = calculate_chat_to_meeting_metrics(['r1'], messages, {'r1': at(10)})

        self.assertEqual(result['conversations_analyzed'], 0)
        self.assertEqual(result['conversations_without_messages'], 1)

    def test_histogram_and_boxplot_across_conversations(self):
        messages = (
            [msg('a', 10, m) for m in (0, 1)] +                    # 2 messages, 10 min
            [msg('b', 10, m) for m in (0, 1)] +                    # 2 messages, 20 min
            [msg('c', 10, m) for m in (0, 1, 2, 3)] +              # 4 messages, 30 min
            [msg('d', 10, m) for m in (0, 1, 2, 3, 4, 5)]          # 6 messages, 40 min
        )
        agreed = {'a': at(10, 10), 'b': at(10, 20), 'c': at(10, 30), 'd': at(10, 40)}

        result = calculate_chat_to_meeting_metrics(['a', 'b', 'c', 'd'], messages, agreed)

        self.assertEqual(result['messages_before_agreement']['histogram'], [
            {'messages': 2, 'conversations': 2},
            {'messages': 4, 'conversations': 1},
            {'messages': 6, 'conversations': 1},
        ])
        self.assertEqual(result['messages_before_agreement']['median'], 3.0)
        self.assertEqual(result['minutes_to_agreement']['boxplot'], {
            'min': 10.0, 'q1': 17.5, 'median': 25.0, 'q3': 32.5, 'max': 40.0,
        })

    def test_uuid_and_string_ids_match(self):
        import uuid
        room = uuid.uuid4()
        messages = [{'chat_room_id': room, 'created_at': at(10)}]

        result = calculate_chat_to_meeting_metrics([room], messages, {str(room): at(10, 5)})

        self.assertEqual(result['conversations_analyzed'], 1)


class AgreementMappingTestCase(SimpleTestCase):

    def test_exchange_is_matched_to_the_chat_of_the_same_material_buyer_seller(self):
        rooms = [
            {'id': 'r1', 'material_id': 'm1', 'buyer_id': 'b1', 'seller_id': 's1'},
            {'id': 'r2', 'material_id': 'm1', 'buyer_id': 'b2', 'seller_id': 's1'},
        ]
        exchanges = [{'material_id': 'm1', 'buyer_id': 'b1', 'seller_id': 's1', 'completed_at': at(11)}]

        self.assertEqual(map_exchanges_to_chat_rooms(rooms, exchanges), {'r1': at(11)})

    def test_first_meeting_confirmed_event_wins_and_events_without_room_are_skipped(self):
        events = [
            {'metadata': {'chatRoomId': 'r1'}, 'occurred_at': at(12)},
            {'metadata': {'chatRoomId': 'r1'}, 'occurred_at': at(10)},
            {'metadata': None, 'occurred_at': at(9)},
            {'metadata': {'other': 1}, 'occurred_at': at(9)},
        ]

        self.assertEqual(map_events_to_chat_rooms(events), {'r1': at(10)})
