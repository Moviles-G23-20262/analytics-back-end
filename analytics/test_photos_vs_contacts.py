from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from .views import summarize_photos_vs_contacts

NOW = datetime(2026, 10, 30, 12, tzinfo=dt_timezone.utc)


def listing(photos=0, contacts=0, days_old=10):
    return {
        'image_urls': [f'https://blob/{i}.jpg' for i in range(photos)],
        'contacts': contacts,
        'created_at': NOW - timedelta(days=days_old),
    }


class SummarizePhotosVsContactsTestCase(SimpleTestCase):

    def bucket(self, result, min_photos):
        return next(b for b in result['buckets'] if b['min_photos'] == min_photos)

    def test_no_listings_answers_zeros(self):
        result = summarize_photos_vs_contacts([], NOW)

        self.assertEqual(result['total_listings'], 0)
        self.assertEqual(result['total_contacts'], 0)
        self.assertEqual(result['points'], [])
        self.assertIsNone(result['correlation'])
        self.assertIsNone(result['many_photos_lift'])
        self.assertTrue(all(b['listings'] == 0 and b['mean_contacts'] == 0.0 for b in result['buckets']))

    def test_three_or_more_photos_share_the_last_bucket(self):
        result = summarize_photos_vs_contacts([listing(3), listing(5), listing(2), listing(0)], NOW)

        self.assertEqual([b['listings'] for b in result['buckets']], [1, 0, 1, 2])
        self.assertEqual(self.bucket(result, 3)['bucket'], '3+ photos')

    def test_missing_photo_list_counts_as_no_photos(self):
        result = summarize_photos_vs_contacts([{'image_urls': None, 'contacts': 1, 'created_at': NOW}], NOW)

        self.assertEqual(self.bucket(result, 0)['listings'], 1)

    def test_contacts_per_bucket(self):
        result = summarize_photos_vs_contacts([
            listing(1, contacts=0),
            listing(1, contacts=2),
            listing(1, contacts=4),
            listing(3, contacts=5),
        ], NOW)

        one = self.bucket(result, 1)
        self.assertEqual((one['listings'], one['contacts']), (3, 6))
        self.assertEqual(one['mean_contacts'], 2.0)
        self.assertEqual(one['median_contacts'], 2.0)
        self.assertAlmostEqual(one['contacted_share'], 2 / 3, places=4)
        self.assertEqual(result['contacted_listings'], 3)
        self.assertEqual(result['total_contacts'], 11)

    def test_lift_compares_three_or_more_photos_with_fewer(self):
        result = summarize_photos_vs_contacts([
            listing(0, contacts=1), listing(2, contacts=1),
            listing(3, contacts=3), listing(4, contacts=3),
        ], NOW)

        self.assertEqual(result['many_photos_lift'], 3.0)

    def test_lift_is_null_without_listings_on_both_sides(self):
        only_few = summarize_photos_vs_contacts([listing(1, contacts=2)], NOW)
        no_contacts_with_few = summarize_photos_vs_contacts([listing(1, contacts=0), listing(3, contacts=2)], NOW)

        self.assertIsNone(only_few['many_photos_lift'])
        self.assertIsNone(no_contacts_with_few['many_photos_lift'])

    def test_correlation(self):
        rising = summarize_photos_vs_contacts([listing(p, contacts=p) for p in range(5)], NOW)
        falling = summarize_photos_vs_contacts([listing(p, contacts=4 - p) for p in range(5)], NOW)
        flat = summarize_photos_vs_contacts([listing(p, contacts=1) for p in range(5)], NOW)

        self.assertEqual(rising['correlation'], 1.0)
        self.assertEqual(falling['correlation'], -1.0)
        self.assertIsNone(flat['correlation'], 'no variation in contacts, so no correlation')

    def test_points_group_listings_with_the_same_photos_and_contacts(self):
        result = summarize_photos_vs_contacts([listing(2, 1), listing(2, 1), listing(0, 0)], NOW)

        self.assertEqual(result['points'], [
            {'photos': 0, 'contacts': 0, 'listings': 1},
            {'photos': 2, 'contacts': 1, 'listings': 2},
        ])

    def test_dates_without_time_zone_are_read_as_utc(self):
        # The database returns Prisma's DateTime columns without a time zone.
        naive = {'image_urls': [], 'contacts': 0, 'created_at': datetime(2026, 10, 29, 12)}

        result = summarize_photos_vs_contacts([naive], NOW)

        self.assertEqual(self.bucket(result, 0)['mean_age_days'], 1.0)

    def test_average_age_shows_how_long_each_group_has_been_online(self):
        result = summarize_photos_vs_contacts([listing(3, days_old=30), listing(3, days_old=10), listing(0, days_old=2)], NOW)

        self.assertEqual(self.bucket(result, 3)['mean_age_days'], 20.0)
        self.assertEqual(self.bucket(result, 0)['mean_age_days'], 2.0)


class PhotosVsContactsEndpointTestCase(SimpleTestCase):

    @patch('analytics.views.Material.objects')
    def test_endpoint_returns_the_summary(self, objects):
        objects.annotate.return_value.values.return_value = [listing(3, contacts=2), listing(0, contacts=0)]

        response = self.client.get(reverse('photos-vs-contacts'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reverse('photos-vs-contacts'), '/analytics/photos-vs-contacts/')
        body = response.json()
        self.assertEqual(body['total_listings'], 2)
        self.assertEqual(body['total_contacts'], 2)
        self.assertEqual(len(body['buckets']), 4)
