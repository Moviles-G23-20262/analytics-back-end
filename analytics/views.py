from django.shortcuts import render

from django.http import JsonResponse
import logging

from django.db import ProgrammingError
from django.db.models import Count, Func, IntegerField
from django.db.models.functions import ExtractHour, ExtractWeekDay
from .models import Material, AnalyticsEvent, AnalyticsEventType
from .models import Exchange, Notification, NotificationType, WishlistItem
from .models import Material, AnalyticsEvent, AnalyticsEventType, Exchange

CAMPUS_TIME_ZONE = 'America/Bogota'

logger = logging.getLogger(__name__)

# Business Question 5
def activity_by_time(request):
    publishing_activity = (
        Material.objects
        .annotate(
            day_of_week=ExtractWeekDay('created_at'),
            hour=ExtractHour('created_at'),
        )
        .values('day_of_week', 'hour')
        .annotate(total=Count('id'))
        .order_by('day_of_week', 'hour')
    )

    browsing_activity = (
        AnalyticsEvent.objects
        .filter(event_type__in=[AnalyticsEventType.LISTING_VIEW, AnalyticsEventType.SEARCH])
        .annotate(
            day_of_week=ExtractWeekDay('occurred_at'),
            hour=ExtractHour('occurred_at'),
        )
        .values('day_of_week', 'hour')
        .annotate(total=Count('id'))
        .order_by('day_of_week', 'hour')
    )

    return JsonResponse({
        'publishing_activity': list(publishing_activity),
        'browsing_activity': list(browsing_activity),
    })

# Business Question 6
def category_performance(request):
    results = (
        Material.objects
        .values('category')
        .annotate(
            total_listings=Count('id', distinct=True),
            completed_exchanges=Count('exchange__id', distinct=True)
        )
        .order_by('-completed_exchanges', '-total_listings')
    )
    
    return JsonResponse({'data': list(results)})

# Business Question 7
def summarize_whishlist_conversion(whislist_items, smart_matches, exchanges):
    first_match_at = {} #dicc cuado recibio su primer smart match (usuario, producto)
    for notification in smart_matches:
        key = (notification['user_id'], notification['material_id'])
        if key not in first_match_at or notification['sent_at'] < first_match_at[key]:
            first_match_at[key] = notification['sent_at']

    purchase_at = {
        #dicc cuando se compro el producto
        (exchange['buyer_id'], exchange['material_id']): exchange['completed_at']
        for exchange in exchanges
    }
    buyers = set()
    items = 0
    with_match = 0
    after_match = 0
    without_match = 0

    for item in whislist_items:
        #clasifica cada producto guardado en la wishlist en una de las 3 categorias: con smart match, comprado despues del smart match, comprado sin smart match
        key = (item['user_id'], item['material_id'])
        buyers.add(item['user_id'])
        items += 1

        match_at = first_match_at.get(key)
        bought_at = purchase_at.get(key)

        if match_at is not None:
            with_match += 1
            if bought_at is not None and bought_at > match_at:
                after_match += 1
        elif bought_at is not None:
            without_match += 1

    return {
        'buyers_with_wishlist': len(buyers),
        'wishlist_items': items,
        'items_with_smart_match': with_match,
        'purchased_after_smart_match': after_match,
        'purchased_without_smart_match': without_match,
        #de los productos que recibieron un smart match, cuantos fueron comprados despues de recibir el smart match
        'conversion_rate': round(after_match / with_match, 4) if with_match else 0.0,
    }

def wishlist_smart_match_conversion(request):
    #devuelve diccionarios con la informacion de los productos
    wishlist_items = WishlistItem.objects.values('user_id', 'material_id')

    #Trae notificaciones de Smart Match que tenga producto asociado
    smart_matches = (Notification.objects
        .filter(type=NotificationType.SMART_MATCH, material__isnull=False)
        .values('user_id', 'material_id', 'sent_at')
    )

    exchanges = Exchange.objects.values('buyer_id', 'material_id', 'completed_at')
    
    #Convierte el dicc a JsonResponse
    return JsonResponse(summarize_whishlist_conversion(wishlist_items, smart_matches, exchanges))

# Business Question 8
# TODO: implement

# Business Question 9
# TODO: implement

# Business Question 10
# TODO: implement

# Business Question 11
# TODO: implement


class CampusHour(Func):
    template = f"EXTRACT(HOUR FROM %(expressions)s AT TIME ZONE 'UTC' AT TIME ZONE '{CAMPUS_TIME_ZONE}')::int"
    output_field = IntegerField()


def meeting_point_usage(request):
    hour = request.GET.get('hour')
    if hour is not None:
        if not hour.isdigit() or not 0 <= int(hour) <= 23:
            return JsonResponse({'error': 'hour must be an integer between 0 and 23'}, status=400)
        hour = int(hour)

    exchanges = Exchange.objects.filter(meeting_point__isnull=False).annotate(hour=CampusHour('completed_at'))
    if hour is not None:
        exchanges = exchanges.filter(hour=hour)

    results = (
        exchanges
        .values('hour', 'meeting_point_id', 'meeting_point__name', 'meeting_point__lat', 'meeting_point__lng', 'meeting_point__is_monitored')
        .annotate(total=Count('id'))
        .order_by('hour', '-total', 'meeting_point__name')
    )

    try:
        data = [
            {
                'meeting_point_id': str(row['meeting_point_id']),
                'name': row['meeting_point__name'],
                'lat': row['meeting_point__lat'],
                'lng': row['meeting_point__lng'],
                'is_monitored': row['meeting_point__is_monitored'],
                'hour': row['hour'],
                'total': row['total'],
            }
            for row in results
        ]
    except ProgrammingError:
        logger.warning('Meeting point tables are missing; apply the BQ12 Prisma migration')
        return JsonResponse({'time_zone': CAMPUS_TIME_ZONE, 'hour': hour, 'available': False, 'data': []})

    return JsonResponse({'time_zone': CAMPUS_TIME_ZONE, 'hour': hour, 'available': True, 'data': data})
