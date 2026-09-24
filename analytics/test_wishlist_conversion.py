#Este codigo funciona solo es para evitar el conflicto en test.py

from django.test import SimpleTestCase
from datetime import datetime, timezone
from .views import summarize_whishlist_conversion

# Create your tests here.

def at(day, hour=12):
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)

class WishlistConversionTestCase(SimpleTestCase):

    def test_empty_data_answer_zeros(self):
        #test de ceros, si no hay datos, la respuesta debe ser 0
        result = summarize_whishlist_conversion([], [], [])

        self.assertEqual(result['wishlist_items'], 0)
        self.assertEqual(result['conversion_rate'], 0.0)

    def test_counts_purchase_after_smart_match_and_baseline(self):
        #test para contar compras después de la coincidencia inteligente y la línea base
        wishlist_items = [
            {'user_id': 'u1', 'material_id': 'm1'},
            {'user_id': 'u1', 'material_id': 'm2'},
            {'user_id': 'u2', 'material_id': 'm3'},
        ]
        matches = [
            {'user_id': 'u1', 'material_id': 'm1', 'sent_at': at(10)},
            {'user_id': 'u2', 'material_id': 'm3', 'sent_at': at(10)},
        ]
        exchanges = [
            {'buyer_id': 'u1', 'material_id': 'm1', 'completed_at': at(12)},
            {'buyer_id': 'u1', 'material_id': 'm2', 'completed_at': at(12)},
        ]

        result = summarize_whishlist_conversion(wishlist_items, matches, exchanges)

        self.assertEqual(result['buyers_with_wishlist'], 2)
        self.assertEqual(result['wishlist_items'], 3)
        self.assertEqual(result['items_with_smart_match'], 2)
        self.assertEqual(result['purchased_after_smart_match'], 1)
        self.assertEqual(result['purchased_without_smart_match'], 1)
        self.assertEqual(result['conversion_rate'], 0.5)

    def test_purchase_before_the_notification_does_not_count(self):
        #test si compro antes del aviso, no cuenta como Smart Match
        wishlist = [{'user_id': 'u1', 'material_id': 'm1'}]
        matches = [{'user_id': 'u1', 'material_id': 'm1', 'sent_at': at(15)}]
        exchanges = [{'buyer_id': 'u1', 'material_id': 'm1', 'completed_at': at(12)}]

        result = summarize_whishlist_conversion(wishlist, matches, exchanges)

        self.assertEqual(result['purchased_after_smart_match'], 0)

    def test_purchase_by_another_user_does_not_count(self):
        #test si compro otro usuario, no cuenta como Smart Match
        wishlist = [{'user_id': 'u1', 'material_id': 'm1'}]
        matches = [{'user_id': 'u1', 'material_id': 'm1', 'sent_at': at(10)}]
        exchanges = [{'buyer_id': 'u2', 'material_id': 'm1', 'completed_at': at(12)}]

        result = summarize_whishlist_conversion(wishlist, matches, exchanges)

        self.assertEqual(result['purchased_after_smart_match'], 0)