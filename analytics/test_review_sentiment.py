from django.test import SimpleTestCase
from .views import classify_review, summarize_review_sentiment


def rating(stars, review=None, tags=None):
    return {'stars': stars, 'review': review, 'tags': tags or []}


class ClassifyReviewTests(SimpleTestCase):

    def test_positive_and_negative_words(self):
        self.assertEqual(classify_review('Very friendly and punctual, great book'), 'positive')
        self.assertEqual(classify_review('Llegó tarde y el libro estaba roto'), 'negative')

    def test_text_without_opinion_words_is_neutral(self):
        self.assertEqual(classify_review('We met at the library at noon'), 'neutral')

    def test_negation_flips_the_next_word(self):
        # "not good" no puede contar como positiva
        self.assertEqual(classify_review('The calculator was not good'), 'negative')

    def test_accents_and_capitals_do_not_matter(self):
        self.assertEqual(classify_review('Muy RÁPIDO y amable'), 'positive')


class SummarizeReviewSentimentTests(SimpleTestCase):

    def test_empty_data_answers_zeros(self):
        result = summarize_review_sentiment([])
        self.assertEqual(result['ratings_total'], 0)
        self.assertEqual(result['reviews_with_text'], 0)
        self.assertEqual(result['agreement_with_stars'], 0.0)

    def test_ratings_without_text_count_but_are_not_classified(self):
        result = summarize_review_sentiment([rating(5, tags=['Punctual']), rating(4, '  ')])
        self.assertEqual(result['ratings_total'], 2)
        self.assertEqual(result['reviews_with_text'], 0)
        self.assertEqual(result['top_tags'], [{'tag': 'Punctual', 'count': 1}])

    def test_counts_sentiments_stars_and_keywords(self):
        result = summarize_review_sentiment([
            rating(5, 'Great seller, very punctual'),
            rating(4, 'Punctual and friendly'),
            rating(1, 'Late and rude'),
            rating(5, 'Late but the book was fine'),
        ])
        self.assertEqual(result['sentiment'], {'positive': 2, 'neutral': 0, 'negative': 2})
        self.assertEqual(result['average_stars']['positive'], 4.5)
        self.assertEqual(result['average_stars']['neutral'], None)
        self.assertEqual(result['agreement_with_stars'], 0.75)
        self.assertEqual(result['top_keywords']['positive'][0], {'word': 'punctual', 'count': 2})
        self.assertEqual(result['top_keywords']['negative'][0], {'word': 'late', 'count': 2})