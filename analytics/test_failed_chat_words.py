from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from .views import ABANDONED_AFTER_DAYS, classify_chats, message_phrases, message_words, summarize_failed_chat_words

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
START = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)


def room(room_id, material='m1', buyer='b1', seller='s1'):
    return {'id': room_id, 'material_id': material, 'buyer_id': buyer, 'seller_id': seller}


def exchange(status, material='m1', buyer='b1', seller='s1', completed_at=None, cancelled_at=None):
    return {'material_id': material, 'buyer_id': buyer, 'seller_id': seller, 'status': status,
            'completed_at': completed_at, 'cancelled_at': cancelled_at}


def msg(room_id, minute, content):
    return {'chat_room_id': room_id, 'content': content, 'created_at': START + timedelta(minutes=minute)}


class MessageWordsTestCase(SimpleTestCase):

    def test_accents_and_case_are_normalized(self):
        self.assertEqual(message_words('El PRECIO está muy caro'), ['precio', 'caro'])

    def test_photos_emails_and_numbers_are_dropped(self):
        words = message_words('https://cdn.campusswap.co/foto.jpg escribeme a ana@uniandes.edu.co o al 3001234567 rebaja 20000')
        self.assertEqual(words, ['escribeme', 'rebaja'])

    def test_greetings_and_connectors_are_ignored(self):
        self.assertEqual(message_words('Hola! gracias, ok? hi thanks'), [])

    def test_negation_is_kept_inside_phrases_only(self):
        self.assertEqual(message_words('mañana no puedo'), ['manana', 'puedo'])
        self.assertEqual(message_phrases('mañana no puedo'), ['no puedo'])


class ClassifyChatsTestCase(SimpleTestCase):

    def test_completed_wins_over_an_earlier_cancellation(self):
        done = START + timedelta(days=2)
        outcomes = classify_chats(
            [room('r1')],
            [exchange('CANCELLED', cancelled_at=START), exchange('COMPLETED', completed_at=done)],
            {'r1': START}, NOW)
        self.assertEqual(outcomes['r1'], ('completed', done))

    def test_cancelled_chat_is_cut_at_the_last_cancellation(self):
        later = START + timedelta(days=3)
        outcomes = classify_chats(
            [room('r1')],
            [exchange('CANCELLED', cancelled_at=START), exchange('CANCELLED', cancelled_at=later)],
            {'r1': START}, NOW)
        self.assertEqual(outcomes['r1'], ('cancelled', later))

    def test_pending_exchange_keeps_the_chat_open_even_if_it_is_quiet(self):
        outcomes = classify_chats([room('r1')], [exchange('PENDING')], {'r1': START}, NOW)
        self.assertEqual(outcomes['r1'], ('open', None))

    def test_quiet_chat_without_exchange_is_abandoned(self):
        quiet = NOW - timedelta(days=ABANDONED_AFTER_DAYS)
        recent = NOW - timedelta(days=ABANDONED_AFTER_DAYS - 1)
        outcomes = classify_chats([room('old'), room('new', buyer='b2')], [], {'old': quiet, 'new': recent}, NOW)
        self.assertEqual(outcomes['old'], ('abandoned', quiet))
        self.assertEqual(outcomes['new'], ('open', None))

    def test_exchange_of_another_buyer_does_not_count(self):
        outcomes = classify_chats([room('r1', buyer='b1')], [exchange('COMPLETED', buyer='b2', completed_at=START)], {}, NOW)
        self.assertEqual(outcomes['r1'], ('open', None))


class SummarizeFailedChatWordsTestCase(SimpleTestCase):

    def test_no_chats_answers_zeros(self):
        result = summarize_failed_chat_words({}, [])
        self.assertEqual(result['conversations_analyzed'], 0)
        self.assertEqual(result['words'], [])
        self.assertEqual(result['phrases'], [])

    def test_only_the_last_messages_before_the_end_are_read(self):
        ended = START + timedelta(minutes=10)
        messages = [msg('r1', 0, 'calculadora'), msg('r1', 1, 'precio alto'), msg('r1', 2, 'precio alto'),
                    msg('r1', 30, 'despues cancelado')]
        result = summarize_failed_chat_words({'r1': ('cancelled', ended)}, messages, last_messages=2, min_conversations=1)

        self.assertEqual(result['messages_analyzed'], 2)
        self.assertEqual({w['word'] for w in result['words']}, {'precio', 'alto'})

    def test_words_of_a_single_chat_are_hidden(self):
        outcomes = {'r1': ('abandoned', None), 'r2': ('cancelled', None)}
        messages = [msg('r1', 0, 'Mariana precio'), msg('r2', 0, 'precio')]
        result = summarize_failed_chat_words(outcomes, messages)

        self.assertEqual([w['word'] for w in result['words']], ['precio'])
        self.assertEqual(result['words'][0]['share'], 1.0)

    def test_phrases_are_consecutive_words(self):
        outcomes = {'r1': ('cancelled', None), 'r2': ('abandoned', None)}
        messages = [msg('r1', 0, 'muy caro el precio final'), msg('r2', 0, 'precio final?')]
        result = summarize_failed_chat_words(outcomes, messages)

        self.assertEqual(result['phrases'], [{'phrase': 'precio final', 'count': 2, 'conversations': 2}])

    def test_distinctive_words_compare_with_completed_chats(self):
        outcomes = {
            'f1': ('cancelled', None), 'f2': ('abandoned', None),
            'c1': ('completed', None), 'c2': ('completed', None),
        }
        messages = [
            msg('f1', 0, 'rebaja libro'), msg('f2', 0, 'rebaja libro'),
            msg('c1', 0, 'libro'), msg('c2', 0, 'libro'),
        ]
        result = summarize_failed_chat_words(outcomes, messages)

        self.assertEqual(result['completed_conversations_compared'], 2)
        self.assertEqual([d['word'] for d in result['distinctive_words']], ['rebaja'])
        self.assertEqual(result['distinctive_words'][0]['difference'], 1.0)
        book = next(w for w in result['words'] if w['word'] == 'libro')
        self.assertEqual(book['completed_share'], 1.0)

    def test_open_chats_and_chats_without_messages_are_skipped(self):
        outcomes = {'open': ('open', None), 'empty': ('cancelled', None)}
        result = summarize_failed_chat_words(outcomes, [msg('open', 0, 'precio')])

        self.assertEqual(result['conversations_analyzed'], 0)
        self.assertEqual(result['chats'], {'cancelled': 1, 'abandoned': 0, 'completed': 0, 'open': 1})
