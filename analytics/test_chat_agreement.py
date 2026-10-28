import uuid
from datetime import datetime, timezone
from unittest import mock

from django.test import SimpleTestCase

from .views import calculate_chat_agreement, first_confirmation


def at(hour, minute=0):
    return datetime(2026, 9, 1, hour, minute, tzinfo=timezone.utc)


class CalculateChatAgreementTestCase(SimpleTestCase):

    def test_counts_the_messages_up_to_the_confirmation_and_the_minutes_since_the_first(self):
        times = [at(10, 0), at(10, 5), at(10, 30), at(11, 0)]

        result = calculate_chat_agreement(times, at(10, 30))

        self.assertEqual(result, {'messagesToAgreement': 3, 'timeToAgreement': 30.0})

    def test_messages_after_the_confirmation_are_ignored(self):
        result = calculate_chat_agreement([at(10, 0), at(12, 0)], at(10, 10))

        self.assertEqual(result['messagesToAgreement'], 1)

    def test_a_chat_without_earlier_messages_has_no_answer(self):
        self.assertIsNone(calculate_chat_agreement([at(12, 0)], at(10, 0)))
        self.assertIsNone(calculate_chat_agreement([], at(10, 0)))

    def test_a_confirmation_stamped_a_bit_before_the_first_message_never_gives_negative_time(self):
        # Phone and server clocks can disagree; the first message is at the confirmation instant.
        result = calculate_chat_agreement([at(10, 0)], at(10, 0))

        self.assertEqual(result['timeToAgreement'], 0.0)


class FirstConfirmationTestCase(SimpleTestCase):

    def test_prefers_the_client_creation_time_over_the_time_the_server_stored_it(self):
        events = [{'client_created_at': at(10, 0), 'occurred_at': at(15, 0)}]

        self.assertEqual(first_confirmation(events), at(10, 0))

    def test_falls_back_to_occurred_at_for_events_without_client_time(self):
        events = [{'client_created_at': None, 'occurred_at': at(15, 0)}]

        self.assertEqual(first_confirmation(events), at(15, 0))

    def test_uses_the_earliest_when_the_meeting_was_agreed_more_than_once(self):
        events = [
            {'client_created_at': at(12, 0), 'occurred_at': at(12, 0)},
            {'client_created_at': at(10, 0), 'occurred_at': at(10, 0)},
        ]

        self.assertEqual(first_confirmation(events), at(10, 0))

    def test_no_events_means_no_confirmation(self):
        self.assertIsNone(first_confirmation([]))


class ChatAgreementEndpointTestCase(SimpleTestCase):
    room = uuid.uuid4()

    def get(self, events, messages):
        with mock.patch('analytics.views.AnalyticsEvent') as event_model, \
                mock.patch('analytics.views.Message') as message_model:
            event_model.objects.filter.return_value.values.return_value = events
            message_model.objects.filter.return_value.values_list.return_value = messages
            response = self.client.get(f'/analytics/chat-agreement/{self.room}/')
            event_filter = event_model.objects.filter.call_args.kwargs
        return response, event_filter

    def test_answers_messages_and_minutes_for_the_chat(self):
        response, event_filter = self.get(
            [{'client_created_at': at(10, 20), 'occurred_at': at(10, 21)}],
            [at(10, 0), at(10, 10), at(10, 20)],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'messagesToAgreement': 3, 'timeToAgreement': 20.0})
        self.assertEqual(event_filter['metadata__chatRoomId'], str(self.room))

    def test_404_when_the_chat_has_no_confirmed_meeting(self):
        response, _ = self.get([], [at(10, 0)])

        self.assertEqual(response.status_code, 404)

    def test_404_when_there_are_no_messages_before_the_confirmation(self):
        response, _ = self.get([{'client_created_at': at(10, 0), 'occurred_at': at(10, 0)}], [at(12, 0)])

        self.assertEqual(response.status_code, 404)
