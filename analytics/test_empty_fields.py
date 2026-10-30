from django.test import SimpleTestCase

from .views import summarize_empty_fields


def listing(category='BOOKS', **fields):
    base = {
        'category': category,
        'course_code': 'MATE1203',
        'edition': '8th',
        'model_name': None,
        'condition': 'GOOD',
        'description': 'Barely used',
        'image_urls': ['https://blob/1.jpg'],
        'faculty': 'Engineering',
    }
    return {**base, **fields}


class SummarizeEmptyFieldsTestCase(SimpleTestCase):

    def field(self, result, name):
        return next(f for f in result['fields'] if f['field'] == name)

    def test_no_listings_answers_zeros(self):
        result = summarize_empty_fields([])

        self.assertEqual(result['total_listings'], 0)
        self.assertEqual(result['complete_listings'], 0)
        self.assertTrue(all(f['empty_rate'] == 0.0 for f in result['fields']))

    def test_null_blank_and_empty_lists_count_as_empty(self):
        result = summarize_empty_fields([
            listing(course_code=None),
            listing(course_code='   ', image_urls=[]),
            listing(description=''),
        ])

        self.assertEqual(self.field(result, 'course_code')['empty'], 2)
        self.assertEqual(self.field(result, 'image_urls')['empty'], 1)
        self.assertEqual(self.field(result, 'description')['empty'], 1)
        self.assertEqual(result['complete_listings'], 0)

    def test_edition_only_counts_for_books_and_model_only_for_devices(self):
        result = summarize_empty_fields([
            listing('BOOKS', edition=None),
            listing('CALCULATORS', edition=None, model_name='fx-991'),
            listing('LAB_EQUIPMENT', edition=None, model_name=None),
        ])

        edition = self.field(result, 'edition')
        self.assertEqual((edition['listings'], edition['empty']), (1, 1))
        model = self.field(result, 'model_name')
        self.assertEqual((model['listings'], model['empty']), (2, 1))
        # The calculator has every field that applies to it.
        self.assertEqual(result['complete_listings'], 1)

    def test_fields_are_ranked_by_how_often_they_are_left_empty(self):
        result = summarize_empty_fields([
            listing(faculty=None, condition=None),
            listing(faculty=None),
            listing(),
        ])

        self.assertEqual([f['field'] for f in result['fields'][:2]], ['faculty', 'condition'])
        self.assertEqual(self.field(result, 'faculty')['empty_rate'], 0.6667)

    def test_breakdown_by_category(self):
        result = summarize_empty_fields([
            listing('BOOKS', course_code=None),
            listing('BOOKS'),
            listing('FURNITURE', course_code=None, image_urls=[]),
        ])

        books, furniture = result['by_category']
        self.assertEqual((books['category'], books['listings'], books['empty']), ('BOOKS', 2, {'course_code': 1}))
        self.assertEqual(furniture['empty'], {'course_code': 1, 'image_urls': 1})
