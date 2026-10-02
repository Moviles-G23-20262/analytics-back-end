from django.shortcuts import render

from django.http import JsonResponse
import logging

from django.db import DataError, ProgrammingError
from django.db import ProgrammingError
from django.db.models import Count, Func, IntegerField
from django.db.models.functions import ExtractHour, ExtractWeekDay
from .models import Material, AnalyticsEvent, AnalyticsEventType
from .models import Exchange, Notification, NotificationType, WishlistItem
from .models import Material, AnalyticsEvent, AnalyticsEventType, Exchange, ExchangeStatus

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

# Business Question 2
def _percentile(sorted_values, pct):
    #percentil con interpolacion lineal sobre una lista ya ordenada
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)

def _summarize_cut(views_by_user, cut_at_by_user):
    #por usuario: publicaciones distintas vistas hasta el momento del corte (inclusive)
    counts = []
    total_events = 0
    for user_id, cut_at in cut_at_by_user.items():
        seen = set()
        for view in views_by_user.get(user_id, []):
            if view['occurred_at'] <= cut_at:
                seen.add(view['material_id'])
                total_events += 1
        counts.append(len(seen))

    counts.sort()
    return {
        'mean': round(sum(counts) / len(counts), 4) if counts else 0.0,
        'median': round(_percentile(counts, 0.5), 4),
        'p75': round(_percentile(counts, 0.75), 4),
        'total_users_analyzed': len(counts),
        'total_events': total_events,
    }

def calculate_buyer_journey_metrics(listing_views, contacts, exchanges):
    views_by_user = {}
    for view in listing_views:
        if view['user_id'] is None or view['material_id'] is None:
            continue
        views_by_user.setdefault(view['user_id'], []).append(view)

    #corte 1: primer CONTACT_SELLER del usuario
    first_contact_at = {}
    for contact in contacts:
        user_id = contact['user_id']
        if user_id is None:
            continue
        if user_id not in first_contact_at or contact['occurred_at'] < first_contact_at[user_id]:
            first_contact_at[user_id] = contact['occurred_at']

    #corte 2: primer intercambio completado donde el usuario es comprador
    first_exchange_at = {}
    for exchange in exchanges:
        buyer_id = exchange['buyer_id']
        if buyer_id not in first_exchange_at or exchange['completed_at'] < first_exchange_at[buyer_id]:
            first_exchange_at[buyer_id] = exchange['completed_at']

    return {
        'views_before_contact': _summarize_cut(views_by_user, first_contact_at),
        'views_before_exchange': _summarize_cut(views_by_user, first_exchange_at),
    }

def buyer_journey_funnel(request):
    events = AnalyticsEvent.objects.values('user_id', 'material_id', 'occurred_at')
    listing_views = events.filter(event_type=AnalyticsEventType.LISTING_VIEW)
    contacts = events.filter(event_type=AnalyticsEventType.CONTACT_SELLER)
    exchanges = Exchange.objects.values('buyer_id', 'material_id', 'completed_at')

    return JsonResponse(calculate_buyer_journey_metrics(listing_views, contacts, exchanges))

# Business Question 4

def _describe(values):
    ordered = sorted(values)
    return {
        'mean': round(sum(ordered) / len(ordered), 4) if ordered else 0.0,
        'median': round(_percentile(ordered, 0.5), 4),
        'p75': round(_percentile(ordered, 0.75), 4),
        'min': round(ordered[0], 4) if ordered else 0.0,
        'max': round(ordered[-1], 4) if ordered else 0.0,
    }

def map_exchanges_to_chat_rooms(chat_rooms, exchanges):
    completed_at = {
        (str(e['material_id']), str(e['buyer_id']), str(e['seller_id'])): e['completed_at']
        for e in exchanges
    }
    agreed = {}
    for room in chat_rooms:
        key = (str(room['material_id']), str(room['buyer_id']), str(room['seller_id']))
        if key in completed_at:
            agreed[str(room['id'])] = completed_at[key]
    return agreed

def map_events_to_chat_rooms(events):
    agreed = {}
    for event in events:
        metadata = event['metadata'] if isinstance(event['metadata'], dict) else {}
        room_id = metadata.get('chatRoomId')
        if not room_id:
            continue
        room_id = str(room_id)
        if room_id not in agreed or event['occurred_at'] < agreed[room_id]:
            agreed[room_id] = event['occurred_at']
    return agreed

def calculate_chat_to_meeting_metrics(chat_room_ids, messages, agreed_at_by_room):
    sent_by_room = {}
    for message in messages:
        sent_by_room.setdefault(str(message['chat_room_id']), []).append(message['created_at'])

    message_counts = []
    minutes_to_agreement = []
    without_agreement = 0   
    without_messages = 0    

    for room_id in (str(r) for r in chat_room_ids):
        agreed_at = agreed_at_by_room.get(room_id)
        if agreed_at is None:
            without_agreement += 1
            continue

        sent = sorted(t for t in sent_by_room.get(room_id, []) if t <= agreed_at)
        if not sent:
            without_messages += 1
            continue
        message_counts.append(len(sent))

        minutes_to_agreement.append((agreed_at - sent[0]).total_seconds() / 60)

    histogram = {}
    for count in message_counts:
        histogram[count] = histogram.get(count, 0) + 1

    ordered = sorted(minutes_to_agreement)
    return {
        'conversations_analyzed': len(message_counts),
        'conversations_without_agreement': without_agreement,
        'conversations_without_messages': without_messages,
        'messages_before_agreement': {
            **_describe(message_counts),

            'histogram': [{'messages': n, 'conversations': histogram[n]} for n in sorted(histogram)],
        },
        'minutes_to_agreement': {
            **_describe(minutes_to_agreement),

            'boxplot': {
                'min': round(ordered[0], 4) if ordered else 0.0,
                'q1': round(_percentile(ordered, 0.25), 4),
                'median': round(_percentile(ordered, 0.5), 4),
                'q3': round(_percentile(ordered, 0.75), 4),
                'max': round(ordered[-1], 4) if ordered else 0.0,
            },
        },
    }

def chat_to_meeting_point(request):
    chat_rooms = list(ChatRoom.objects.values('id', 'material_id', 'buyer_id', 'seller_id'))
    messages = Message.objects.values('chat_room_id', 'created_at')

    try:
        exchanges = Exchange.objects.filter(meeting_point__isnull=False).values(
            'material_id', 'buyer_id', 'seller_id', 'completed_at')
        from_exchanges = map_exchanges_to_chat_rooms(chat_rooms, exchanges)
    except ProgrammingError:
        logger.warning('Exchange.meetingPointId is missing; apply the BQ12 Prisma migration')
        from_exchanges = {}

    try:
        events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.MEETING_CONFIRMED).values('metadata', 'occurred_at')
        from_events = map_events_to_chat_rooms(events)
    except (DataError, ProgrammingError):
        logger.warning('MEETING_CONFIRMED is not in the AnalyticsEventType enum yet; using exchanges only')
        from_events = {}

    agreed_at_by_room = {**from_exchanges, **from_events}  #the event wins over the fallback
    result = calculate_chat_to_meeting_metrics(
        [room['id'] for room in chat_rooms], messages, agreed_at_by_room)
    result['agreement_sources'] = {
        'meeting_confirmed_event': len(from_events),
        'exchange_completed_at': len(set(from_exchanges) - set(from_events)),
    }
    return JsonResponse(result)


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

    exchanges = (
        Exchange.objects
        .filter(meeting_point__isnull=False, status=ExchangeStatus.COMPLETED, completed_at__isnull=False)
        .annotate(hour=CampusHour('completed_at'))
    )
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
