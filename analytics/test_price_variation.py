from decimal import Decimal

from django.test import SimpleTestCase

from .views import item_key, summarize_price_variation


def listing(title, price, condition='GOOD', seller='s1', faculty='Engineering', category='BOOKS', edition='8th', model_name=None):
    return {
        'title': title, 'price': Decimal(str(price)), 'condition': condition, 'seller_id': seller,
        'faculty': faculty, 'category': category, 'edition': edition, 'model_name': model_name,
    }


class ItemKeyTestCase(SimpleTestCase):

    def test_titles_match_ignoring_case_accents_and_punctuation(self):
        self.assertEqual(
            item_key(listing('Cálculo  de Stewart,', 1)),
            item_key(listing('calculo de stewart', 1)),
        )

    def test_a_different_edition_is_a_different_item(self):
        self.assertNotEqual(item_key(listing('Stewart', 1, edition='7th')), item_key(listing('Stewart', 1, edition='8th')))

    def test_model_wins_over_title(self):
        a = listing('Casio scientific calculator', 1, category='CALCULATORS', edition=None, model_name='fx-991LA')
        b = listing('Calculadora Casio', 1, category='CALCULATORS', edition=None, model_name='FX 991LA')
        self.assertEqual(item_key(a), item_key(b))


class SummarizePriceVariationTestCase(SimpleTestCase):

    def test_no_listings_answers_zeros(self):
        result = summarize_price_variation([])

        self.assertEqual(result['listings'], 0)
        self.assertEqual(result['items_compared'], 0)
        self.assertEqual(result['median_spread_pct'], 0.0)
        self.assertEqual(result['items'], [])

    def test_items_listed_once_are_not_compared(self):
        result = summarize_price_variation([listing('Stewart', 100), listing('Arduino', 50, category='LAB_EQUIPMENT', edition=None)])

        self.assertEqual(result['listings'], 2)
        self.assertEqual(result['items_compared'], 0)

    def test_free_listings_are_left_out(self):
        result = summarize_price_variation([listing('Stewart', 0), listing('Stewart', 100)])

        self.assertEqual(result['listings'], 1)
        self.assertEqual(result['items_compared'], 0)

    def test_spread_of_the_same_item_between_sellers(self):
        result = summarize_price_variation([
            listing('Stewart', 80, seller='s1'),
            listing('Stewart', 100, seller='s2'),
            listing('Stewart', 120, seller='s3', condition='NEW'),
        ])

        item = result['items'][0]
        self.assertEqual((item['listings'], item['sellers']), (3, 3))
        self.assertEqual((item['min'], item['median'], item['max']), (80.0, 100.0, 120.0))
        self.assertEqual(item['spread_pct'], 40.0)
        self.assertEqual(item['by_condition'], {'GOOD': 90.0, 'NEW': 120.0})
        self.assertEqual(item['item'], 'Stewart, 8th')

    def test_condition_and_faculty_are_compared_against_each_items_median(self):
        result = summarize_price_variation([
            listing('Stewart', 100, condition='NEW', faculty='Engineering'),
            listing('Stewart', 50, condition='FAIR', faculty=None),
            listing('Casio', 40, condition='NEW', category='CALCULATORS', edition=None, model_name='fx-991', faculty='Engineering'),
            listing('Casio', 20, condition='FAIR', category='CALCULATORS', edition=None, model_name='fx-991', faculty=None),
        ])

        by_condition = {r['condition']: r['median_relative_price'] for r in result['by_condition']}
        self.assertEqual(by_condition, {'NEW': 1.3333, 'FAIR': 0.6667})
        self.assertEqual([r['condition'] for r in result['by_condition']], ['NEW', 'FAIR'])
        by_faculty = {r['faculty']: r['median_relative_price'] for r in result['by_faculty']}
        self.assertEqual(by_faculty, {'Engineering': 1.3333, 'Unknown': 0.6667})


class PriceVariationWithoutRepeatedItemsTestCase(SimpleTestCase):
    """Before any item is listed twice the page still needs something to chart: the category ranges."""

    def test_every_category_gets_its_price_range(self):
        result = summarize_price_variation([
            listing('Stewart', 80), listing('Apostol', 120, edition='2nd'), listing('Larson', 100, edition='10th'),
            listing('Casio', 64000, category='CALCULATORS', edition=None, model_name='fx-991'),
        ])

        self.assertEqual(result['items_compared'], 0)
        books, calculators = result['by_category']
        self.assertEqual(books, {'category': 'BOOKS', 'listings': 3, 'min': 80.0, 'median': 100.0, 'max': 120.0, 'spread_pct': 40.0})
        self.assertEqual(calculators['spread_pct'], 0.0)

    def test_condition_is_compared_against_the_category_until_items_repeat(self):
        result = summarize_price_variation([
            listing('Stewart', 150, condition='NEW'), listing('Apostol', 50, condition='FAIR', edition='2nd'),
        ])

        self.assertEqual(result['relative_to'], 'category')
        by_condition = {r['condition']: r['median_relative_price'] for r in result['by_condition']}
        self.assertEqual(by_condition, {'NEW': 1.5, 'FAIR': 0.5})

    def test_repeated_items_take_over_as_the_baseline(self):
        result = summarize_price_variation([listing('Stewart', 80), listing('Stewart', 120), listing('Apostol', 500, edition='2nd')])

        self.assertEqual(result['relative_to'], 'item')
        self.assertEqual(result['by_condition'][0]['listings'], 2)
