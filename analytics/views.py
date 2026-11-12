import math
import re
import unicodedata
import uuid
from collections import Counter
from datetime import timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from django.http import JsonResponse
import logging

from django.db import DataError, ProgrammingError
from django.db import ProgrammingError
from django.db.models import Count, F, Func, IntegerField, Max, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay
from .models import Material, AnalyticsEvent, AnalyticsEventType
from .models import Exchange, Notification, NotificationType, WishlistItem
from .models import Material, AnalyticsEvent, AnalyticsEventType, Exchange, ExchangeStatus
from .models import ChatRoom, Message, MaterialCategory, MaterialCondition, MaterialStatus, MessageType
from .models import Rating
from .models import MeetingPoint, MeetingProposal, MeetingProposalStatus

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
            completed_exchanges=Count('exchange__id', filter=Q(exchange__status=ExchangeStatus.COMPLETED), distinct=True)
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
        if exchange['completed_at'] is None:
            continue
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
    exchanges = Exchange.objects.filter(status=ExchangeStatus.COMPLETED).values('buyer_id', 'material_id', 'completed_at')

    return JsonResponse(calculate_buyer_journey_metrics(listing_views, contacts, exchanges))

# Smart Feature: fair-price estimation from real completed sales (Exchange.price).
MIN_PRICE_SAMPLES = 5

def calculate_price_stats(prices):
    #Tukey fences: descarta outliers fuera de [Q1 - 1.5*IQR, Q3 + 1.5*IQR] antes de resumir
    ordered = sorted(float(p) for p in prices)
    if len(ordered) >= 4:
        q1, q3 = _percentile(ordered, 0.25), _percentile(ordered, 0.75)
        iqr = q3 - q1
        ordered = [p for p in ordered if q1 - 1.5 * iqr <= p <= q3 + 1.5 * iqr]
    return {
        'sample_size': len(ordered),
        'p25': round(_percentile(ordered, 0.25), 2),
        'median': round(_percentile(ordered, 0.5), 2),
        'p75': round(_percentile(ordered, 0.75), 2),
    }

def price_stats(request):
    category = request.GET.get('category')
    condition = request.GET.get('condition')
    if category not in MaterialCategory.values:
        return JsonResponse({'error': 'category is required and must be a valid MaterialCategory'}, status=400)
    if condition is not None and condition not in MaterialCondition.values:
        return JsonResponse({'error': 'condition must be a valid MaterialCondition'}, status=400)

    sales = Exchange.objects.filter(material__category=category, status=ExchangeStatus.COMPLETED)
    scope = 'category'
    if condition:
        narrowed = sales.filter(material__condition=condition)
        #si hay pocas ventas con la misma condicion se amplia a toda la categoria
        if narrowed.count() >= MIN_PRICE_SAMPLES:
            sales, scope = narrowed, 'category_condition'

    stats = calculate_price_stats(sales.values_list('price', flat=True))
    stats.update({'category': category, 'condition': condition, 'scope': scope})
    return JsonResponse(stats)

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


def calculate_chat_agreement(message_times, confirmed_at):
    """BQ4 for one chat: how many messages it took, and how long, until the meeting was confirmed.

    `confirmed_at` comes from the MEETING_CONFIRMED event (the phone's clientCreatedAt). Only the
    messages sent up to that moment count. Returns None when the chat has none of them.
    """
    sent = sorted(t for t in message_times if t <= confirmed_at)
    if not sent:
        return None
    minutes = max(0.0, (confirmed_at - sent[0]).total_seconds() / 60)
    return {'messagesToAgreement': len(sent), 'timeToAgreement': round(minutes, 4)}

def first_confirmation(events):
    """When the chat first agreed on a meeting: the earliest MEETING_CONFIRMED, by the time the
    phone created it (clientCreatedAt), falling back to when the server stored it."""
    times = [e['client_created_at'] or e['occurred_at'] for e in events]
    return min(times) if times else None

def chat_agreement(request, chat_room_id):
    """GET /analytics/chat-agreement/<chatRoomId>/ -> {"messagesToAgreement": N, "timeToAgreement": minutes}."""
    try:
        events = list(AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.MEETING_CONFIRMED,
            metadata__chatRoomId=str(chat_room_id),
        ).values('client_created_at', 'occurred_at'))
    except (DataError, ProgrammingError):
        logger.warning('MEETING_CONFIRMED is not in the AnalyticsEventType enum yet')
        events = []

    confirmed_at = first_confirmation(events)
    if confirmed_at is None:
        return JsonResponse({'error': 'No confirmed meeting for this chat'}, status=404)

    message_times = Message.objects.filter(chat_room_id=chat_room_id).values_list('created_at', flat=True)
    result = calculate_chat_agreement(list(message_times), confirmed_at)
    if result is None:
        return JsonResponse({'error': 'This chat has no messages before the confirmation'}, status=404)
    return JsonResponse(result)


# Business Question 8
# Field of the listing form -> (label, categories where it applies). None = every category.
# Edition only makes sense for books and model for devices, so a calculator without an edition is not "empty".
LISTING_FIELDS = [
    ('course_code', 'Course', None),
    ('edition', 'Edition', {MaterialCategory.BOOKS}),
    ('model_name', 'Model', {MaterialCategory.CALCULATORS, MaterialCategory.LAB_EQUIPMENT}),
    ('condition', 'Condition', None),
    ('description', 'Description', None),
    ('image_urls', 'Photos', None),
    ('faculty', 'Faculty', None),
]

def _is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return not value
    return False

def summarize_empty_fields(listings):
    #por campo: cuantas publicaciones lo podian llenar y cuantas lo dejaron vacio
    applicable = {field: 0 for field, _, _ in LISTING_FIELDS}
    empty = {field: 0 for field, _, _ in LISTING_FIELDS}
    by_category = {}
    complete = 0
    total = 0

    for listing in listings:
        total += 1
        category = listing['category']
        row = by_category.setdefault(category, {'category': category, 'listings': 0, 'empty': {}})
        row['listings'] += 1
        missing_any = False
        for field, _, categories in LISTING_FIELDS:
            if categories is not None and category not in categories:
                continue
            applicable[field] += 1
            if _is_empty(listing.get(field)):
                empty[field] += 1
                row['empty'][field] = row['empty'].get(field, 0) + 1
                missing_any = True
        if not missing_any:
            complete += 1

    fields = [
        {
            'field': field,
            'label': label,
            'applies_to': sorted(categories) if categories is not None else None,
            'listings': applicable[field],
            'empty': empty[field],
            'empty_rate': round(empty[field] / applicable[field], 4) if applicable[field] else 0.0,
        }
        for field, label, categories in LISTING_FIELDS
    ]
    fields.sort(key=lambda f: (-f['empty_rate'], -f['empty'], f['field']))
    return {
        'total_listings': total,
        'complete_listings': complete,
        'fields': fields,
        'by_category': sorted(by_category.values(), key=lambda r: (-r['listings'], r['category'])),
    }

def empty_fields(request):
    listings = Material.objects.values(
        'category', 'course_code', 'edition', 'model_name', 'condition', 'description', 'image_urls',
        faculty=F('seller__faculty'),
    )
    return JsonResponse(summarize_empty_fields(listings))

# Business Question 9
MAX_ITEMS_LISTED = 20

def _normalize(text):
    #"Cálculo  de Stewart, 8va." y "calculo de stewart 8va" cuentan como el mismo texto
    plain = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in plain.lower()).split())

def item_key(listing):
    #mismo item = mismo modelo; sin modelo, mismo titulo y edicion (dentro de la misma categoria)
    model = _normalize(listing.get('model_name'))
    if model:
        return (listing['category'], 'model', model)
    title = _normalize(listing.get('title'))
    if not title:
        return None
    return (listing['category'], 'title', title, _normalize(listing.get('edition')))

def _median(values):
    return _percentile(sorted(values), 0.5)

def _relative_by(groups, key):
    #precio de cada publicacion dividido por la mediana de su item: 0.8 = 20% mas barato que lo normal
    relative = {}
    for listings in groups:
        median = _median([l['price'] for l in listings])
        if not median:
            continue
        for l in listings:
            relative.setdefault(l.get(key), []).append(l['price'] / median)
    return relative

def summarize_price_variation(listings):
    groups = {}
    total = 0
    for listing in listings:
        price = float(listing['price'] or 0)
        if price <= 0:
            continue
        total += 1
        key = item_key(listing)
        if key is not None:
            groups.setdefault(key, []).append({**listing, 'price': price})

    #solo se comparan items publicados al menos dos veces
    comparable = [g for g in groups.values() if len(g) >= 2]

    items = []
    for g in comparable:
        prices = sorted(l['price'] for l in g)
        median = _percentile(prices, 0.5)
        first = g[0]
        label = first['title']
        if first.get('model_name'):
            label = f"{label} ({first['model_name']})"
        elif first.get('edition'):
            label = f"{label}, {first['edition']}"
        by_condition = {}
        for l in g:
            by_condition.setdefault(l.get('condition') or 'UNKNOWN', []).append(l['price'])
        items.append({
            'item': label,
            'category': first['category'],
            'listings': len(g),
            'sellers': len({str(l['seller_id']) for l in g}),
            'min': round(prices[0], 2),
            'median': round(median, 2),
            'max': round(prices[-1], 2),
            'spread_pct': round((prices[-1] - prices[0]) / median * 100, 2) if median else 0.0,
            'by_condition': {c: round(_median(v), 2) for c, v in sorted(by_condition.items())},
        })
    items.sort(key=lambda i: (-i['listings'], -i['spread_pct'], i['item']))

    condition_order = {c: i for i, c in enumerate(MaterialCondition.values)}
    by_condition = [
        {'condition': c or 'UNKNOWN', 'listings': len(v), 'median_relative_price': round(_median(v), 4)}
        for c, v in _relative_by(comparable, 'condition').items()
    ]
    by_condition.sort(key=lambda r: condition_order.get(r['condition'], len(condition_order)))
    by_faculty = [
        {'faculty': f or 'Unknown', 'listings': len(v), 'median_relative_price': round(_median(v), 4)}
        for f, v in _relative_by(comparable, 'faculty').items()
    ]
    by_faculty.sort(key=lambda r: (-r['listings'], r['faculty']))

    return {
        'listings': total,
        'items_compared': len(comparable),
        'listings_compared': sum(len(g) for g in comparable),
        'median_spread_pct': round(_median([i['spread_pct'] for i in items]), 2),
        'items': items[:MAX_ITEMS_LISTED],
        'by_condition': by_condition,
        'by_faculty': by_faculty,
    }

def price_variation(request):
    listings = Material.objects.values(
        'title', 'category', 'edition', 'model_name', 'condition', 'price', 'seller_id',
        faculty=F('seller__faculty'),
    )
    return JsonResponse(summarize_price_variation(listings))

# Business Question 3
# Photos per listing (length of imageUrls) against the buyers who contacted the seller about it
# (one ChatRoom per buyer and listing). What the photos show (angles, close-ups of damage) is not
# stored anywhere, so that part of the question cannot be answered from the database.
# The last bucket is open-ended: Sprint 1 asks whether 3 or more photos bring more contacts.
PHOTO_BUCKETS = [(0, 'No photos'), (1, '1 photo'), (2, '2 photos'), (3, '3+ photos')]
MANY_PHOTOS = PHOTO_BUCKETS[-1][0]

def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if not var_x or not var_y:
        return None
    return cov / (var_x * var_y) ** 0.5

def _as_utc(moment):
    # Prisma's DateTime columns have no time zone, so they come back naive; they are UTC.
    return moment.replace(tzinfo=dt_timezone.utc) if timezone.is_naive(moment) else moment

def summarize_photos_vs_contacts(listings, now):
    #cuantas fotos tiene cada publicacion y cuantos compradores distintos escribieron por ella
    rows = []
    for listing in listings:
        photos = len(listing.get('image_urls') or [])
        contacts = listing.get('contacts') or 0
        created_at = listing.get('created_at')
        age_days = max((_as_utc(now) - _as_utc(created_at)).total_seconds() / 86400, 0) if created_at else None
        rows.append((photos, contacts, age_days))

    buckets = []
    for i, (lower, label) in enumerate(PHOTO_BUCKETS):
        upper = PHOTO_BUCKETS[i + 1][0] if i + 1 < len(PHOTO_BUCKETS) else None
        group = [r for r in rows if r[0] >= lower and (upper is None or r[0] < upper)]
        contacts = [r[1] for r in group]
        ages = [r[2] for r in group if r[2] is not None]
        buckets.append({
            'bucket': label,
            'min_photos': lower,
            'listings': len(group),
            'contacts': sum(contacts),
            'mean_contacts': round(sum(contacts) / len(contacts), 4) if contacts else 0.0,
            'median_contacts': round(_median(contacts), 4) if contacts else 0.0,
            'contacted_share': round(sum(1 for c in contacts if c) / len(contacts), 4) if contacts else 0.0,
            # Older listings have had more time to be contacted; shown so that bias is visible.
            'mean_age_days': round(sum(ages) / len(ages), 2) if ages else 0.0,
        })

    many = [r[1] for r in rows if r[0] >= MANY_PHOTOS]
    few = [r[1] for r in rows if r[0] < MANY_PHOTOS]
    mean_many = sum(many) / len(many) if many else None
    mean_few = sum(few) / len(few) if few else None
    r = _pearson([row[0] for row in rows], [row[1] for row in rows])

    # One point per (photos, contacts) pair, sized by how many listings share it, for the bubble chart.
    pairs = Counter((row[0], row[1]) for row in rows)
    points = [{'photos': p, 'contacts': c, 'listings': n} for (p, c), n in sorted(pairs.items())]

    return {
        'total_listings': len(rows),
        'contacted_listings': sum(1 for row in rows if row[1]),
        'total_contacts': sum(row[1] for row in rows),
        'buckets': buckets,
        'points': points,
        'correlation': round(r, 4) if r is not None else None,
        # How many times more contacts a listing with 3+ photos gets than one with fewer; null when either side is missing.
        'many_photos_lift': round(mean_many / mean_few, 4) if mean_many is not None and mean_few else None,
        'many_photos_threshold': MANY_PHOTOS,
    }

def photos_vs_contacts(request):
    listings = Material.objects.annotate(
        contacts=Count('chat_rooms__buyer', distinct=True),
    ).values('image_urls', 'created_at', 'contacts')
    return JsonResponse(summarize_photos_vs_contacts(listings, timezone.now()))

# Business Question 10
DEFAULT_STALE_DAYS = 14
SURVIVAL_CHECKPOINTS = [0, 1, 3, 7, 14, 21, 30, 45, 60]
DEAD_LISTING_CLUSTERS_MAX = 4
MAX_DEAD_ITEMS_LISTED = 50

DEAD_PRICE_BANDS = [
    ('underpriced', 'Under market (< -15%)'),
    ('fair', 'Fair market (-15% to +15%)'),
    ('overpriced', 'Above market (+15% to +40%)'),
    ('steep', 'Heavily overpriced (> +40%)'),
    ('unpriced', 'Unpriced'),
]

DEAD_RATING_BUCKETS = [
    ('unrated', 'New / unrated seller'),
    ('low', 'Low rating (< 3.5)'),
    ('solid', 'Solid (3.5 - 4.4)'),
    ('top', 'Top rated (4.5+)'),
]


def _classify_price_band(price, price_ratio):
    if price <= 0 or price_ratio is None:
        return 'unpriced'
    if price_ratio < 0.85:
        return 'underpriced'
    if price_ratio <= 1.15:
        return 'fair'
    if price_ratio <= 1.40:
        return 'overpriced'
    return 'steep'


def _classify_photo_bucket(photos):
    if photos <= 0:
        return 'No photos'
    if photos == 1:
        return '1 photo'
    if photos == 2:
        return '2 photos'
    return '3+ photos'


def _classify_rating_bucket(rating):
    if rating <= 0:
        return 'unrated'
    if rating < 3.5:
        return 'low'
    if rating < 4.5:
        return 'solid'
    return 'top'


def _round_suggested_price(target, current_price):
    if current_price <= 0 or target <= 0:
        return None
    # Keep suggested price cleanly rounded in COP when in thousands, otherwise 2 decimals.
    rounded = round(target / 100.0) * 100.0 if current_price >= 1000 else round(target, 2)
    rounded = min(rounded, round(current_price * 0.95, 2) if current_price < 1000 else float(int(current_price) - 100))
    if rounded <= 0 or rounded >= current_price:
        return round(max(1.0, current_price * 0.85), 2) if current_price > 1 else None
    return round(float(rounded), 2)


def _build_dead_survival_curve(observations):
    if not observations:
        return [
            {'day': d, 'survival_rate': 0.0, 'at_risk': 0, 'sold_cumulative': 0}
            for d in SURVIVAL_CHECKPOINTS
        ]

    event_times = {}
    for duration, sold in observations:
        if sold:
            event_times[duration] = event_times.get(duration, 0) + 1
    sorted_events = sorted(event_times.items(), key=lambda kv: kv[0])

    # Precompute survival at each distinct event time (Kaplan-Meier estimator).
    km_steps = []
    surv = 1.0
    for t, d_j in sorted_events:
        n_j = sum(1 for duration, _ in observations if duration >= t)
        if n_j > 0:
            surv *= 1.0 - (d_j / n_j)
        km_steps.append((t, surv))

    curve = []
    for day in SURVIVAL_CHECKPOINTS:
        if day == 0:
            cur_surv = 1.0
            sold_cum = 0
        else:
            cur_surv = 1.0
            for t, step_surv in km_steps:
                if t <= day:
                    cur_surv = step_surv
                else:
                    break
            sold_cum = sum(1 for duration, sold in observations if sold and duration <= day)
        at_risk = sum(1 for duration, _ in observations if duration >= day)
        curve.append({
            'day': day,
            'survival_rate': round(max(0.0, min(1.0, cur_surv)), 4),
            'at_risk': at_risk,
            'sold_cumulative': sold_cum,
        })
    return curve


def _cohort_summary(rows):
    days = [r['duration_days'] for r in rows if r['duration_known']]
    ratios = [r['price_ratio'] for r in rows if r['price_ratio'] is not None]
    photos = [r['photos'] for r in rows]
    ratings = [r['seller_rating'] for r in rows]
    n = len(rows)
    return {
        'count': n,
        'median_days': round(_median(days), 2) if days else 0.0,
        'mean_days': round(sum(days) / len(days), 2) if days else 0.0,
        'median_price_ratio': round(_median(ratios), 4) if ratios else None,
        'mean_photos': round(sum(photos) / n, 2) if n else 0.0,
        'zero_photo_share': round(sum(1 for p in photos if p == 0) / n, 4) if n else 0.0,
        'zero_contact_share': round(sum(1 for r in rows if r['contacts'] == 0) / n, 4) if n else 0.0,
        'mean_seller_rating': round(sum(ratings) / n, 2) if n else 0.0,
    }


def _bucket_stats(rows, key_fn, ordered_keys):
    grouped = {k: [] for k, _ in ordered_keys}
    for row in rows:
        k = key_fn(row)
        if k in grouped:
            grouped[k].append(row)

    out = []
    for k, label in ordered_keys:
        group = grouped[k]
        total = len(group)
        dead = [r for r in group if r['lifecycle'] == 'dead']
        sold = [r for r in group if r['lifecycle'] == 'sold']
        dead_days = [r['duration_days'] for r in dead if r['duration_known']]
        out.append({
            'key': k,
            'label': label,
            'total': total,
            'dead': len(dead),
            'sold': len(sold),
            'dead_rate': round(len(dead) / total, 4) if total else 0.0,
            'median_days_active_dead': round(_median(dead_days), 2) if dead_days else 0.0,
        })
    return out


def _squared_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _label_dead_cluster(avg_price_ratio, avg_photos, avg_rating, avg_days, stale_days, top_category):
    signals = []
    if avg_price_ratio >= 1.25:
        signals.append(('Overpriced above market', 'Lower price toward the category median'))
    if avg_photos < 1.5:
        signals.append(('Too few photos', 'Upload 2-3 clear photos showing condition'))
    if avg_rating < 0.5:
        signals.append(('New / unrated sellers', 'Add course code, edition, and condition proof to build trust'))
    elif avg_rating < 3.5:
        signals.append(('Low seller rating', 'Highlight exact item condition and adjust price slightly for trust'))
    if avg_days >= max(stale_days * 2, 28):
        signals.append(('Long-tail stale listings', 'Refresh title/course tags or apply a clearance discount'))

    if len(signals) >= 2:
        label = f'{signals[0][0]} + {signals[1][0].lower()}'
        action = f'{signals[0][1]}; {signals[1][1].lower()}.'
    elif len(signals) == 1:
        label = signals[0][0]
        action = f'{signals[0][1]}.'
    else:
        cat_name = top_category.replace('_', ' ').title()
        label = f'Fair-priced low-demand ({cat_name})'
        action = 'Offer a 10-15% price drop or share course code tags to attract buyers.'
    return label, action


def _cluster_dead_listings(dead_rows, stale_days):
    if not dead_rows:
        return []

    # Sort deterministically so clustering is reproducible regardless of SQL row order.
    ordered = sorted(
        dead_rows,
        key=lambda r: (-r['cluster_price_ratio'], r['photos'], r['seller_rating'], -r['duration_days'], r['id']),
    )

    raw_vectors = [
        [r['cluster_price_ratio'], float(r['photos']), float(r['seller_rating']), float(r['duration_days'])]
        for r in ordered
    ]

    # Z-score standardization per feature axis across the dead-listing cohort.
    dims = 4
    n = len(raw_vectors)
    means = [sum(v[j] for v in raw_vectors) / n for j in range(dims)]
    stds = []
    for j in range(dims):
        variance = sum((v[j] - means[j]) ** 2 for v in raw_vectors) / n
        stds.append(math.sqrt(variance) if variance > 1e-12 else 1.0)

    scaled = [[(v[j] - means[j]) / stds[j] for j in range(dims)] for v in raw_vectors]
    unique_scaled = {tuple(round(x, 6) for x in v) for v in scaled}
    k = min(DEAD_LISTING_CLUSTERS_MAX, len(unique_scaled), n)
    if k == 0:
        return []

    # Deterministic farthest-first (Gonzales) initialization from the standardized vectors.
    first_idx = max(range(n), key=lambda i: sum(x * x for x in scaled[i]))
    center_indices = [first_idx]
    while len(center_indices) < k:
        best_idx = max(
            (i for i in range(n) if i not in center_indices),
            key=lambda i: min(_squared_distance(scaled[i], scaled[c]) for c in center_indices),
        )
        center_indices.append(best_idx)
    centers = [list(scaled[i]) for i in center_indices]

    assignments = [0] * n
    for _ in range(25):
        new_assignments = [
            min(range(k), key=lambda c: _squared_distance(scaled[i], centers[c]))
            for i in range(n)
        ]
        # Re-seed any empty cluster with the point farthest from its assigned center.
        counts = Counter(new_assignments)
        for c in range(k):
            if counts[c] == 0:
                farthest = max(range(n), key=lambda i: _squared_distance(scaled[i], centers[new_assignments[i]]))
                old_c = new_assignments[farthest]
                if counts[old_c] > 1:
                    new_assignments[farthest] = c
                    counts[old_c] -= 1
                    counts[c] += 1

        if new_assignments == assignments:
            break
        assignments = new_assignments
        for c in range(k):
            members = [scaled[i] for i, a in enumerate(assignments) if a == c]
            if members:
                centers[c] = [sum(m[j] for m in members) / len(members) for j in range(dims)]

    groups = {}
    for row, cid in zip(ordered, assignments):
        groups.setdefault(cid, []).append(row)

    prelim = []
    for cid, rows in groups.items():
        ratios = [r['price_ratio'] for r in rows if r['price_ratio'] is not None]
        avg_ratio = sum(ratios) / len(ratios) if ratios else 1.0
        avg_photos = sum(r['photos'] for r in rows) / len(rows)
        avg_rating = sum(r['seller_rating'] for r in rows) / len(rows)
        avg_days = sum(r['duration_days'] for r in rows) / len(rows)
        med_days = _median([r['duration_days'] for r in rows])
        cat_counts = Counter(r['category'] for r in rows)
        top_category = cat_counts.most_common(1)[0][0]
        label, action = _label_dead_cluster(avg_ratio, avg_photos, avg_rating, avg_days, stale_days, top_category)
        prelim.append({
            '_rows': rows,
            'label': label,
            'recommended_action': action,
            'count': len(rows),
            'share': round(len(rows) / n, 4),
            'avg_price_ratio': round(avg_ratio, 4),
            'median_price_ratio': round(_median(ratios), 4) if ratios else 1.0,
            'avg_photos': round(avg_photos, 2),
            'avg_seller_rating': round(avg_rating, 2),
            'avg_days_active': round(avg_days, 2),
            'median_days_active': round(med_days, 2),
            'zero_contact_share': round(sum(1 for r in rows if r['contacts'] == 0) / len(rows), 4),
            'top_category': top_category,
            'categories': [{'category': cat, 'count': cnt} for cat, cnt in cat_counts.most_common()],
            'sample_titles': [r['title'] for r in sorted(rows, key=lambda x: (-x['duration_days'], x['title']))[:3]],
        })

    prelim.sort(key=lambda c: (-c['count'], -c['avg_days_active'], c['label']))

    # Ensure unique cluster labels if two groups share the same primary label.
    seen_labels = Counter(c['label'] for c in prelim)
    for idx, c in enumerate(prelim):
        cluster_id = f'cluster-{idx + 1}'
        if seen_labels[c['label']] > 1:
            cat_label = c['top_category'].replace('_', ' ').title()
            candidate = f"{c['label']} ({cat_label})"
            c['label'] = candidate if sum(1 for x in prelim if x['label'] == candidate) == 0 else f'{candidate} #{idx + 1}'
        c['cluster_id'] = cluster_id
        for row in c['_rows']:
            row['cluster_id'] = cluster_id
            row['cluster_label'] = c['label']
        del c['_rows']

    return prelim


def _evaluate_listing_risk(row, stale_days):
    reasons = []
    score = 0.0
    days_active = row['duration_days']
    price = row['price']
    benchmark = row['benchmark_price']
    ratio = row['price_ratio']
    photos = row['photos']
    contacts = row['contacts']
    rating = row['seller_rating']
    is_dead = row['lifecycle'] == 'dead'

    age_pts = min(40.0, (days_active / max(stale_days, 1)) * 20.0)
    score += age_pts
    if is_dead:
        reasons.append(f'Unsold for {round(days_active, 1)} days (threshold {stale_days}d)')
    elif days_active >= max(1.0, stale_days * 0.5):
        reasons.append(f'Active for {round(days_active, 1)} days with no sale yet')

    if ratio is not None and ratio > 1.15:
        over_pct = round((ratio - 1.0) * 100)
        score += 30.0 if ratio >= 1.40 else 18.0
        reasons.append(f'Priced {over_pct}% above category median')

    if photos == 0:
        score += 20.0
        reasons.append('No photos uploaded')
    elif photos == 1:
        score += 10.0
        reasons.append('Only 1 photo (3+ photos attract more buyers)')

    if rating <= 0:
        score += 5.0
        reasons.append('New or unrated seller profile')
    elif rating < 3.5:
        score += 12.0
        reasons.append(f'Low seller rating ({rating:.1f}/5)')

    if contacts == 0 and days_active >= 3.0:
        score += 10.0
        reasons.append('No buyer messages yet')

    risk_score = min(100, round(score))
    if is_dead or risk_score >= 60:
        risk_level = 'high'
    elif risk_score >= 35:
        risk_level = 'medium'
    elif risk_score >= 15:
        risk_level = 'watch'
    else:
        risk_level = 'low'

    suggested_price = None
    recommended_drop_pct = 0.0
    if price > 0:
        if benchmark and ratio is not None and ratio > 1.15:
            target = benchmark * (0.95 if is_dead and contacts == 0 else 1.0)
            suggested_price = _round_suggested_price(target, price)
        elif is_dead:
            suggested_price = _round_suggested_price(price * 0.85, price)
    if suggested_price is not None and price > 0:
        recommended_drop_pct = round((price - suggested_price) / price * 100, 1)

    actions = []
    if suggested_price is not None:
        actions.append(f'Drop price by ~{recommended_drop_pct:.0f}% (to {suggested_price:,.0f})')
    if photos < 2:
        actions.append('add 2-3 clear photos')
    if contacts == 0 and not actions:
        actions.append('refresh title & course code')
    recommendation = '; '.join(actions).capitalize() + '.' if actions else 'Healthy pace - monitor inquiries.'

    return {
        'id': row['id'],
        'title': row['title'],
        'category': row['category'],
        'price': round(price, 2),
        'category_median_price': round(benchmark, 2) if benchmark is not None else None,
        'price_ratio': round(ratio, 4) if ratio is not None else None,
        'suggested_price': suggested_price,
        'recommended_drop_pct': recommended_drop_pct,
        'photos': photos,
        'contacts': contacts,
        'seller_id': row['seller_id'],
        'seller_rating': round(rating, 2),
        'days_active': round(days_active, 2),
        'is_dead': is_dead,
        'cluster_id': row.get('cluster_id'),
        'cluster_label': row.get('cluster_label'),
        'risk_score': risk_score,
        'risk_level': risk_level,
        'reasons': reasons,
        'recommendation': recommendation,
    }


def summarize_dead_listings(listings, now, stale_days=DEFAULT_STALE_DAYS, seller_id=None, sold_exchanges=None):
    now_utc = _as_utc(now)
    sold_at_by_material = {}
    for ex in (sold_exchanges or []):
        if ex.get('status') not in (None, ExchangeStatus.COMPLETED):
            continue
        mat_id = str(ex.get('material_id') or '')
        comp = ex.get('completed_at')
        if not mat_id or comp is None:
            continue
        comp_utc = _as_utc(comp)
        if mat_id not in sold_at_by_material or comp_utc < sold_at_by_material[mat_id]:
            sold_at_by_material[mat_id] = comp_utc

    parsed = []
    skipped = 0
    for idx, row in enumerate(listings):
        created_raw = row.get('created_at')
        if created_raw is None:
            skipped += 1
            continue
        created_utc = _as_utc(created_raw)
        mat_id = str(row.get('id') or f'row-{idx}')
        status = row.get('status') or MaterialStatus.AVAILABLE
        sold_raw = row.get('sold_at') or sold_at_by_material.get(mat_id)
        is_sold = (status == MaterialStatus.SOLD) or (sold_raw is not None)

        price = float(row.get('price') or 0.0)
        photos = len(row.get('image_urls') or [])
        contacts = int(row.get('contacts') or 0)
        seller_rating = float(row.get('seller_rating') or 0.0)
        category = row.get('category') or MaterialCategory.OTHER

        if is_sold:
            end_raw = sold_raw or row.get('updated_at')
            if end_raw is not None:
                end_utc = _as_utc(end_raw)
                if end_utc >= created_utc:
                    duration_days = (end_utc - created_utc).total_seconds() / 86400.0
                    duration_known = True
                else:
                    duration_days = None
                    duration_known = False
            else:
                duration_days = None
                duration_known = False
            lifecycle = 'sold'
        elif status == MaterialStatus.RESERVED:
            duration_days = max((now_utc - created_utc).total_seconds() / 86400.0, 0.0)
            duration_known = True
            lifecycle = 'reserved'
        else:
            duration_days = max((now_utc - created_utc).total_seconds() / 86400.0, 0.0)
            duration_known = True
            lifecycle = 'dead' if duration_days >= stale_days else 'active_fresh'

        parsed.append({
            'id': mat_id,
            'title': row.get('title') or 'Untitled',
            'category': category,
            'price': price,
            'condition': row.get('condition'),
            'status': status,
            'photos': photos,
            'contacts': contacts,
            'seller_id': str(row.get('seller_id') or ''),
            'seller_rating': seller_rating,
            'lifecycle': lifecycle,
            'duration_days': duration_days,
            'duration_known': duration_known,
            'cluster_id': None,
            'cluster_label': None,
        })

    # Category price benchmarks: completed sales preferred when >= 3 samples exist, else all priced items.
    sold_prices_by_cat = {}
    all_prices_by_cat = {}
    for item in parsed:
        if item['price'] <= 0:
            continue
        all_prices_by_cat.setdefault(item['category'], []).append(item['price'])
        if item['lifecycle'] == 'sold':
            sold_prices_by_cat.setdefault(item['category'], []).append(item['price'])

    benchmarks = {}
    for cat in {item['category'] for item in parsed}:
        sold_list = sold_prices_by_cat.get(cat, [])
        all_list = all_prices_by_cat.get(cat, [])
        if len(sold_list) >= 3:
            benchmarks[cat] = _median(sold_list)
        elif all_list:
            benchmarks[cat] = _median(all_list)
        else:
            benchmarks[cat] = None

    for item in parsed:
        bench = benchmarks.get(item['category'])
        item['benchmark_price'] = bench
        ratio = (item['price'] / bench) if (item['price'] > 0 and bench and bench > 0) else None
        item['price_ratio'] = ratio
        item['cluster_price_ratio'] = min(ratio, 3.0) if ratio is not None else 1.0
        item['price_band'] = _classify_price_band(item['price'], ratio)
        item['photo_bucket'] = _classify_photo_bucket(item['photos'])
        item['rating_bucket'] = _classify_rating_bucket(item['seller_rating'])

    sold_rows = [r for r in parsed if r['lifecycle'] == 'sold']
    reserved_rows = [r for r in parsed if r['lifecycle'] == 'reserved']
    fresh_rows = [r for r in parsed if r['lifecycle'] == 'active_fresh']
    dead_rows = [r for r in parsed if r['lifecycle'] == 'dead']

    observations = [
        (r['duration_days'], r['lifecycle'] == 'sold')
        for r in parsed
        if r['duration_known'] and r['duration_days'] is not None
    ]
    survival_curve = _build_dead_survival_curve(observations)
    clusters = _cluster_dead_listings(dead_rows, stale_days)

    categories_present = sorted({r['category'] for r in parsed})
    by_category = []
    for cat in categories_present:
        cat_rows = [r for r in parsed if r['category'] == cat]
        cat_dead = [r for r in cat_rows if r['lifecycle'] == 'dead']
        cat_sold = [r for r in cat_rows if r['lifecycle'] == 'sold']
        cat_reserved = [r for r in cat_rows if r['lifecycle'] == 'reserved']
        cat_fresh = [r for r in cat_rows if r['lifecycle'] == 'active_fresh']
        cat_dead_days = [r['duration_days'] for r in cat_dead if r['duration_known']]
        cat_prices = [r['price'] for r in cat_rows if r['price'] > 0]
        cat_sold_prices = [r['price'] for r in cat_sold if r['price'] > 0]
        cat_ratios = [r['price_ratio'] for r in cat_dead if r['price_ratio'] is not None]
        by_category.append({
            'category': cat,
            'total': len(cat_rows),
            'sold': len(cat_sold),
            'reserved': len(cat_reserved),
            'active_fresh': len(cat_fresh),
            'dead': len(cat_dead),
            'dead_rate': round(len(cat_dead) / len(cat_rows), 4) if cat_rows else 0.0,
            'median_days_active_dead': round(_median(cat_dead_days), 2) if cat_dead_days else 0.0,
            'median_price': round(_median(cat_prices), 2) if cat_prices else None,
            'median_sold_price': round(_median(cat_sold_prices), 2) if cat_sold_prices else None,
            'median_price_ratio_dead': round(_median(cat_ratios), 4) if cat_ratios else None,
        })
    by_category.sort(key=lambda r: (-r['dead'], -r['dead_rate'], r['category']))

    dead_evaluated = [_evaluate_listing_risk(r, stale_days) for r in dead_rows]
    dead_evaluated.sort(key=lambda r: (-r['days_active'], -r['risk_score'], r['id']))

    target_seller = str(seller_id) if seller_id is not None else None
    available_rows = [r for r in parsed if r['lifecycle'] in ('dead', 'active_fresh')]
    if target_seller is not None:
        seller_all = [r for r in parsed if r['seller_id'] == target_seller]
        seller_available = [r for r in available_rows if r['seller_id'] == target_seller]
        evaluated_seller = [_evaluate_listing_risk(r, stale_days) for r in seller_available]
        at_risk = [r for r in evaluated_seller if r['is_dead'] or r['risk_score'] >= 15]
        at_risk.sort(key=lambda r: (-(1 if r['is_dead'] else 0), -r['risk_score'], -r['days_active'], r['id']))
        seller_summary = {
            'seller_id': target_seller,
            'total_listings': len(seller_all),
            'sold_listings': sum(1 for r in seller_all if r['lifecycle'] == 'sold'),
            'reserved_listings': sum(1 for r in seller_all if r['lifecycle'] == 'reserved'),
            'active_fresh_listings': sum(1 for r in seller_all if r['lifecycle'] == 'active_fresh'),
            'dead_listings': sum(1 for r in seller_all if r['lifecycle'] == 'dead'),
            'at_risk_count': len(at_risk),
            'healthy_listings': max(0, len(seller_available) - len(at_risk)),
        }
    else:
        evaluated_avail = [_evaluate_listing_risk(r, stale_days) for r in available_rows]
        at_risk = [r for r in evaluated_avail if r['is_dead'] or r['risk_score'] >= 20]
        at_risk.sort(key=lambda r: (-(1 if r['is_dead'] else 0), -r['risk_score'], -r['days_active'], r['id']))
        at_risk = at_risk[:20]
        seller_summary = None

    total = len(parsed)
    dead_cohort = _cohort_summary(dead_rows)
    sold_cohort = _cohort_summary(sold_rows)

    return {
        'summary': {
            'total_listings': total,
            'sold_listings': len(sold_rows),
            'reserved_listings': len(reserved_rows),
            'active_fresh_listings': len(fresh_rows),
            'dead_listings': len(dead_rows),
            'skipped': skipped,
            'stale_days': stale_days,
            'dead_share': round(len(dead_rows) / total, 4) if total else 0.0,
            'never_sold_share': round((total - len(sold_rows)) / total, 4) if total else 0.0,
            'median_days_active_dead': dead_cohort['median_days'],
            'mean_days_active_dead': dead_cohort['mean_days'],
            'median_days_to_sell': sold_cohort['median_days'],
        },
        'survival_curve': survival_curve,
        'comparisons': {
            'dead': dead_cohort,
            'sold': sold_cohort,
        },
        'breakdowns': {
            'by_category': by_category,
            'by_price_band': _bucket_stats(parsed, lambda r: r['price_band'], DEAD_PRICE_BANDS),
            'by_photos': _bucket_stats(parsed, lambda r: r['photo_bucket'], [(b, b) for _, b in PHOTO_BUCKETS]),
            'by_seller_rating': _bucket_stats(parsed, lambda r: r['rating_bucket'], DEAD_RATING_BUCKETS),
        },
        'clusters': clusters,
        'dead_listings': dead_evaluated[:MAX_DEAD_ITEMS_LISTED],
        'at_risk_listings': at_risk,
        'seller_summary': seller_summary,
    }


def dead_listings(request):
    raw_stale = request.GET.get('staleDays')
    if raw_stale is not None:
        if not raw_stale.isdigit() or not (1 <= int(raw_stale) <= 365):
            return JsonResponse({'error': 'staleDays must be an integer between 1 and 365'}, status=400)
        stale_days = int(raw_stale)
    else:
        stale_days = DEFAULT_STALE_DAYS

    raw_seller_id = request.GET.get('sellerId')
    seller_id = None
    if raw_seller_id:
        try:
            seller_id = str(uuid.UUID(raw_seller_id))
        except ValueError:
            return JsonResponse({'error': 'sellerId must be a valid UUID'}, status=400)

    listings = list(
        Material.objects.annotate(
            contacts=Count('chat_rooms__buyer', distinct=True),
        ).values(
            'id', 'title', 'category', 'price', 'condition', 'status', 'image_urls',
            'seller_id', 'created_at', 'updated_at', 'contacts',
            seller_rating=F('seller__rating'),
        )
    )
    try:
        sold_exchanges = list(
            Exchange.objects.filter(status=ExchangeStatus.COMPLETED).values('material_id', 'completed_at', 'status')
        )
    except (DataError, ProgrammingError) as err:
        logger.warning('Could not query completed exchanges for dead listings: %s', err)
        sold_exchanges = []

    return JsonResponse(
        summarize_dead_listings(
            listings,
            timezone.now(),
            stale_days=stale_days,
            seller_id=seller_id,
            sold_exchanges=sold_exchanges,
        )
    )

# Business Question 11
# Upper bound (days) of each bar in the time-to-sell histogram; the last bar is open-ended.
SELL_TIME_BUCKETS = [(1, 'Under 1 day'), (3, '1-3 days'), (7, '3-7 days'), (14, '1-2 weeks'), (30, '2-4 weeks'), (None, '30+ days')]

def summarize_time_to_sell(sales):
    #dias entre que se publica el material y se completa su intercambio
    days = []
    by_category = {}
    skipped = 0
    for sale in sales:
        listed_at, sold_at = sale['listed_at'], sale['completed_at']
        if listed_at is None or sold_at is None or sold_at < listed_at:
            skipped += 1
            continue
        d = (sold_at - listed_at).total_seconds() / 86400
        days.append(d)
        by_category.setdefault(sale['category'], []).append(d)

    histogram = []
    lower = 0
    for upper, label in SELL_TIME_BUCKETS:
        count = sum(1 for d in days if d >= lower and (upper is None or d < upper))
        histogram.append({'bucket': label, 'sold': count})
        lower = upper

    categories = [
        {'category': c, 'sold': len(v), 'mean_days': round(sum(v) / len(v), 4), 'median_days': round(_median(v), 4)}
        for c, v in by_category.items()
    ]
    categories.sort(key=lambda r: (r['median_days'], r['category']))
    return {
        'sold_listings': len(days),
        'skipped': skipped,
        'days_to_sell': _describe(days),
        'histogram': histogram,
        'by_category': categories,
    }

def time_to_sell(request):
    sales = Exchange.objects.filter(status=ExchangeStatus.COMPLETED).values(
        'completed_at', category=F('material__category'), listed_at=F('material__created_at'),
    )
    return JsonResponse(summarize_time_to_sell(sales))

# Business Question 15 - Average ticket: what a completed sale is worth, overall and per item condition.

def _pesos(total, sales):
    return int(round(float(total) / sales)) if sales else None

def summarize_average_ticket(groups):
    #groups: una fila por condicion con la suma de precios y cuantas ventas tiene
    total = sum(float(g['total'] or 0) for g in groups)
    sales = sum(g['sales'] for g in groups)
    by_condition = {
        g['condition']: _pesos(g['total'], g['sales'])
        for g in groups
        if g['condition'] is not None and g['sales']
    }
    #mismo orden que MaterialCondition (de mejor a peor estado)
    order = {value: i for i, value in enumerate(MaterialCondition.values)}
    return {
        'globalAverage': _pesos(total, sales),
        'byCondition': dict(sorted(by_condition.items(), key=lambda kv: order.get(kv[0], len(order)))),
    }

def completed_sales_by_condition():
    #JOIN Exchange -> Material (INNER, por materialId) y GROUP BY Material.condition, solo ventas completadas
    return (
        Exchange.objects.filter(status=ExchangeStatus.COMPLETED)
        .values(condition=F('material__condition'))
        .annotate(total=Sum('price'), sales=Count('id'))
        .order_by()
    )

def average_ticket(request):
    return JsonResponse(summarize_average_ticket(list(completed_sales_by_condition())))


def calculate_time_to_sold_metrics(sales_records):
    """
    Computes time-to-sold metrics for published materials.
    sales_records is an iterable of dicts with:
      - 'material_id': str/UUID
      - 'category': str (MaterialCategory value)
      - 'listed_at': datetime
      - 'sold_at': datetime
    """
    durations_by_category = {}
    all_days = []

    buckets = {
        '< 1 day': 0,
        '1 - 3 days': 0,
        '3 - 7 days': 0,
        '7 - 14 days': 0,
        '14 - 30 days': 0,
        '> 30 days': 0,
    }

    for record in sales_records:
        listed = record.get('listed_at')
        sold = record.get('sold_at')
        if not listed or not sold:
            continue
        days = max(0.0, (sold - listed).total_seconds() / 86400.0)
        category = record.get('category') or 'OTHER'

        all_days.append(days)
        durations_by_category.setdefault(category, []).append(days)

        if days < 1:
            buckets['< 1 day'] += 1
        elif days <= 3:
            buckets['1 - 3 days'] += 1
        elif days <= 7:
            buckets['3 - 7 days'] += 1
        elif days <= 14:
            buckets['7 - 14 days'] += 1
        elif days <= 30:
            buckets['14 - 30 days'] += 1
        else:
            buckets['> 30 days'] += 1

    by_category = []
    for cat, cat_days in durations_by_category.items():
        by_category.append({
            'category': cat,
            'total_sold': len(cat_days),
            **_describe(cat_days),
        })

    by_category.sort(key=lambda c: (-c['total_sold'], c['mean']))

    fastest_category = min(by_category, key=lambda c: c['mean'])['category'] if by_category else None
    slowest_category = max(by_category, key=lambda c: c['mean'])['category'] if by_category else None

    return {
        'total_sold_items': len(all_days),
        'overall': _describe(all_days),
        'distribution': [
            {'range': r, 'count': count}
            for r, count in buckets.items()
        ],
        'by_category': by_category,
        'fastest_category': fastest_category,
        'slowest_category': slowest_category,
    }


def time_to_sold(request):
    """
    BQ 11: What is the average time (in days) it takes for a newly listed academic item to be marked as sold?
    """
    category = request.GET.get('category')
    if category is not None and category not in MaterialCategory.values:
        return JsonResponse({'error': 'category must be a valid MaterialCategory'}, status=400)

    try:
        exchanges = (
            Exchange.objects
            .filter(status=ExchangeStatus.COMPLETED, completed_at__isnull=False, material__isnull=False)
            .values('material_id', 'material__category', 'material__created_at', 'completed_at')
        )
        if category:
            exchanges = exchanges.filter(material__category=category)

        sales_data = [
            {
                'material_id': str(row['material_id']),
                'category': row['material__category'],
                'listed_at': row['material__created_at'],
                'sold_at': row['completed_at'],
            }
            for row in exchanges
            if row['material__created_at'] and row['completed_at']
        ]
    except (ProgrammingError, DataError) as err:
        logger.warning('Could not query time-to-sold data: %s', err)
        return JsonResponse({'error': 'Failed to query sales data', 'available': False}, status=500)

    result = calculate_time_to_sold_metrics(sales_data)
    result['available'] = True
    if category:
        result['filtered_category'] = category
    return JsonResponse(result)


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

# Business Question 14
# Sentimiento por diccionario (lexicon): cada palabra positiva suma 1, cada negativa resta 1,
# y un "not"/"no" justo antes invierte la palabra ("not good" cuenta como negativa).
SENTIMENTS = ('positive', 'neutral', 'negative')

POSITIVE_WORDS = {
    'good', 'great', 'excellent', 'friendly', 'kind', 'nice', 'fast', 'quick', 'punctual', 'perfect',
    'helpful', 'honest', 'reliable', 'amazing', 'smooth', 'easy', 'polite', 'recommend', 'recommended',
    'love', 'thanks', 'fair', 'clean', 'awesome',
    'bueno', 'buena', 'excelente', 'amable', 'rapido', 'rapida', 'puntual', 'perfecto', 'perfecta',
    'genial', 'honesto', 'honesta', 'confiable', 'recomiendo', 'recomendado', 'gracias', 'chevere', 'bien',
}
NEGATIVE_WORDS = {
    'bad', 'late', 'rude', 'slow', 'broken', 'damaged', 'scam', 'worst', 'terrible', 'poor', 'dirty',
    'fake', 'dishonest', 'wrong', 'missing', 'problem', 'awful', 'cancelled',
    'malo', 'mala', 'mal', 'tarde', 'grosero', 'grosera', 'lento', 'lenta', 'roto', 'rota', 'danado',
    'danada', 'estafa', 'peor', 'sucio', 'sucia', 'falso', 'falsa', 'problema', 'impuntual',
}
REVIEW_NEGATIONS = {'not', 'no', 'never', 'dont', 'didnt', 'wasnt', 'isnt', 'nunca', 'tampoco'}
REVIEW_STOPWORDS = {
    'the', 'and', 'was', 'were', 'very', 'with', 'for', 'that', 'this', 'but', 'are', 'you', 'they',
    'has', 'had', 'have', 'from', 'all', 'its', 'our', 'his', 'her', 'she', 'him', 'item',
    'una', 'uno', 'los', 'las', 'del', 'que', 'muy', 'con', 'por', 'para', 'fue', 'pero', 'como',
    'todo', 'esta', 'este', 'era', 'son', 'mas', 'sus',
}
REVIEW_TOP_WORDS = 10


def _words(text):
    # minúsculas y sin tildes: "Rápido" y "rapido" cuentan como la misma palabra
    plain = unicodedata.normalize('NFKD', text.lower()).encode('ascii', 'ignore').decode()
    return re.findall(r'[a-z]+', plain.replace("'", ''))


def classify_review(text):
    words = _words(text)
    score = 0
    for i, word in enumerate(words):
        value = 1 if word in POSITIVE_WORDS else -1 if word in NEGATIVE_WORDS else 0
        if value and i > 0 and words[i - 1] in REVIEW_NEGATIONS:
            value = -value
        score += value
    if score > 0:
        return 'positive'
    if score < 0:
        return 'negative'
    return 'neutral'


def _stars_sentiment(stars):
    if stars >= 4:
        return 'positive'
    if stars <= 2:
        return 'negative'
    return 'neutral'


def summarize_review_sentiment(ratings):
    counts = {s: 0 for s in SENTIMENTS}
    stars = {s: [] for s in SENTIMENTS}
    keywords = {s: Counter() for s in SENTIMENTS}
    tags = Counter()
    total = 0
    agree = 0

    for rating in ratings:
        total += 1
        tags.update(rating['tags'] or [])
        text = (rating['review'] or '').strip()
        if not text:
            continue  # solo estrellas y tags: no hay texto que clasificar
        sentiment = classify_review(text)
        counts[sentiment] += 1
        stars[sentiment].append(rating['stars'])
        keywords[sentiment].update(
            w for w in _words(text) if len(w) >= 3 and w not in REVIEW_STOPWORDS and w not in REVIEW_NEGATIONS
        )
        if _stars_sentiment(rating['stars']) == sentiment:
            agree += 1

    with_text = sum(counts.values())
    return {
        'ratings_total': total,
        'reviews_with_text': with_text,
        'sentiment': counts,
        'average_stars': {s: round(sum(v) / len(v), 2) if v else None for s, v in stars.items()},
        # de las reseñas con texto, cuántas dicen lo mismo que sus estrellas
        'agreement_with_stars': round(agree / with_text, 4) if with_text else 0.0,
        'top_keywords': {
            s: [{'word': w, 'count': c} for w, c in keywords[s].most_common(REVIEW_TOP_WORDS)] for s in SENTIMENTS
        },
        'top_tags': [{'tag': t, 'count': c} for t, c in tags.most_common()],
    }


def review_sentiment(request):
    ratings = Rating.objects.values('stars', 'tags', 'review')
    return JsonResponse(summarize_review_sentiment(ratings))


# Business Question 13
# Words students write right before a deal falls through. A chat falls through when its exchange was
# cancelled, or when nobody wrote in it for ABANDONED_AFTER_DAYS and no exchange was completed or is pending.
ABANDONED_AFTER_DAYS = 7
LAST_MESSAGES = 10      # "immediately before": only the last messages of each chat are read
MIN_CONVERSATIONS = 2   # a word must show up in at least this many chats, so names or nicknames of one chat never appear
TOP_WORDS = 40
TOP_PHRASES = 15

# Words that say nothing about why a deal ended: Spanish and English connectors, greetings and thanks.
# The text is normalized first (_normalize), so they are written without accents.
STOPWORDS = set('''
a al algo ante asi aun bien cada como con cual de del desde donde el ella ellos en entre era es esa ese eso esta
estas este esto estoy etc fue ha hay la las le les lo los mas me mi mis muy ni no nos o otra otro para pero por
porque pues que se si sin sobre su sus te tengo ti tu tus un una uno unos y ya yo
hola buenas buenos dias tardes noches gracias listo vale jaja jajaja
the and for you your are was not but with this that have has can its just from what when will would there they
them then than too yes also how hi hello hey thanks thank okay
'''.split())

URL_OR_EMAIL = re.compile(r'https?://\S+|\S+@\S+')
# Kept only inside phrases: without them "manana no puedo" would read as "manana puedo".
NEGATIONS = {'no', 'not', 'nunca', 'never'}


def message_words(content, keep_negations=False):
    #fuera las fotos (URL), los correos y los numeros (telefonos, precios); despues el mismo texto normalizado de BQ9
    text = _normalize(URL_OR_EMAIL.sub(' ', content or ''))
    return [
        w for w in text.split()
        if w.isalpha() and ((keep_negations and w in NEGATIONS) or (len(w) >= 3 and w not in STOPWORDS))
    ]


def message_phrases(content):
    #dos palabras seguidas; una negacion solo puede abrir la frase ("no puedo"), nunca cerrarla
    tokens = message_words(content, keep_negations=True)
    return [f'{a} {b}' for a, b in zip(tokens, tokens[1:]) if b not in NEGATIONS]


def _room_key(row):
    return (str(row['material_id']), str(row['buyer_id']), str(row['seller_id']))


def classify_chats(chat_rooms, exchanges, last_message_at, now):
    """How each chat ended and when: {roomId: (outcome, ended_at)}.

    A chat belongs to an exchange when both have the same material, buyer and seller (as in BQ4).
    Outcomes: 'completed' wins over everything (the buyer may cancel and then buy anyway), then
    'cancelled' (cut at the last cancellation), then 'open' while an exchange is still pending,
    'abandoned' after ABANDONED_AFTER_DAYS without messages, and 'open' otherwise.
    """
    by_room = {}
    for exchange in exchanges:
        by_room.setdefault(_room_key(exchange), []).append(exchange)

    outcomes = {}
    for room in chat_rooms:
        room_id = str(room['id'])
        related = by_room.get(_room_key(room), [])
        statuses = {e['status'] for e in related}
        last = last_message_at.get(room_id)

        if ExchangeStatus.COMPLETED in statuses:
            times = [e['completed_at'] for e in related if e['status'] == ExchangeStatus.COMPLETED and e['completed_at']]
            outcomes[room_id] = ('completed', min(times) if times else None)
        elif ExchangeStatus.PENDING in statuses:
            outcomes[room_id] = ('open', None)
        elif ExchangeStatus.CANCELLED in statuses:
            times = [e['cancelled_at'] for e in related if e['status'] == ExchangeStatus.CANCELLED and e['cancelled_at']]
            outcomes[room_id] = ('cancelled', max(times) if times else None)
        elif last is not None and now - last >= timedelta(days=ABANDONED_AFTER_DAYS):
            outcomes[room_id] = ('abandoned', last)
        else:
            outcomes[room_id] = ('open', None)
    return outcomes


def _share(part, whole):
    return round(part / whole, 4) if whole else 0.0


def summarize_failed_chat_words(outcomes, messages, last_messages=LAST_MESSAGES, min_conversations=MIN_CONVERSATIONS):
    """Word cloud of the last messages of the chats that fell through, compared with the chats that ended in a sale.

    `count` is how many times a word was written; `conversations` in how many chats it appears. The shares use
    chats, so one very talkative chat cannot fill the cloud by itself.
    """
    thread_by_room = {}
    for message in messages:
        thread_by_room.setdefault(str(message['chat_room_id']), []).append(message)

    words, phrases, completed_docs = Counter(), Counter(), Counter()
    word_docs, phrase_docs = Counter(), Counter()
    failed_chats = completed_chats = messages_read = 0
    by_outcome = Counter(outcome for outcome, _ in outcomes.values())

    for room_id, (outcome, ended_at) in outcomes.items():
        if outcome == 'open':
            continue
        thread = sorted(
            (m for m in thread_by_room.get(room_id, []) if ended_at is None or m['created_at'] <= ended_at),
            key=lambda m: m['created_at'],
        )[-last_messages:]
        if not thread:
            continue

        chat_words, chat_phrases = [], []
        for message in thread:
            chat_words += message_words(message['content'])
            chat_phrases += message_phrases(message['content'])

        if outcome == 'completed':
            completed_chats += 1
            completed_docs.update(set(chat_words))
            continue
        failed_chats += 1
        messages_read += len(thread)
        words.update(chat_words)
        word_docs.update(set(chat_words))
        phrases.update(chat_phrases)
        phrase_docs.update(set(chat_phrases))

    top_words = [
        {
            'word': w,
            'count': words[w],
            'conversations': word_docs[w],
            'share': _share(word_docs[w], failed_chats),
            'completed_share': _share(completed_docs[w], completed_chats),
        }
        for w in words if word_docs[w] >= min_conversations
    ]
    top_words.sort(key=lambda r: (-r['count'], -r['conversations'], r['word']))

    top_phrases = [
        {'phrase': p, 'count': phrases[p], 'conversations': phrase_docs[p]}
        for p in phrases if phrase_docs[p] >= min_conversations
    ]
    top_phrases.sort(key=lambda r: (-r['count'], r['phrase']))

    #palabras que aparecen mas en los chats que se cayeron que en los que terminaron en venta
    distinctive = [
        {**r, 'difference': round(r['share'] - r['completed_share'], 4)}
        for r in top_words if r['share'] > r['completed_share']
    ]
    distinctive.sort(key=lambda r: (-r['difference'], r['word']))

    return {
        'abandoned_after_days': ABANDONED_AFTER_DAYS,
        'last_messages': last_messages,
        'min_conversations': min_conversations,
        'chats': {key: by_outcome.get(key, 0) for key in ('cancelled', 'abandoned', 'completed', 'open')},
        'conversations_analyzed': failed_chats,
        'completed_conversations_compared': completed_chats,
        'messages_analyzed': messages_read,
        'words': top_words[:TOP_WORDS],
        'phrases': top_phrases[:TOP_PHRASES],
        'distinctive_words': distinctive[:10],
    }


def failed_chat_words(request):
    chat_rooms = list(ChatRoom.objects.values('id', 'material_id', 'buyer_id', 'seller_id'))
    columns = ('material_id', 'buyer_id', 'seller_id', 'status', 'completed_at')

    try:
        exchanges = list(Exchange.objects.values(*columns, 'cancelled_at'))
    except ProgrammingError:
        logger.warning('Exchange.cancelledAt is missing; apply the Prisma migration that adds it')
        exchanges = [{**e, 'cancelled_at': None} for e in Exchange.objects.values(*columns)]

    try:
        #las tarjetas de propuesta (MEETING) las escribe el servidor, no los estudiantes
        messages = list(Message.objects.exclude(type=MessageType.MEETING).values('chat_room_id', 'content', 'created_at'))
    except (DataError, ProgrammingError):
        logger.warning('Message.type is missing; meeting proposal cards are read as text')
        messages = list(Message.objects.values('chat_room_id', 'content', 'created_at'))

    last_message_at = {
        str(row['chat_room_id']): row['last']
        for row in Message.objects.values('chat_room_id').annotate(last=Max('created_at')).order_by()
    }
    outcomes = classify_chats(chat_rooms, exchanges, last_message_at, timezone.now())
    return JsonResponse(summarize_failed_chat_words(outcomes, messages))


def _campus_hour(moment):
    return _as_utc(moment).astimezone(ZoneInfo(CAMPUS_TIME_ZONE)).hour


def _outcome_counts():
    return {'agreed': 0, 'completed': 0, 'cancelled': 0, 'not_closed': 0}


def _with_rate(counts):
    return {**counts, 'completion_rate': _share(counts['completed'], counts['agreed'])}


def summarize_meetup_outcomes(proposals, chat_rooms, exchanges, points, now):
    statuses_by_room = {}
    for exchange in exchanges:
        statuses_by_room.setdefault(_room_key(exchange), set()).add(exchange['status'])
    room_keys = {str(room['id']): _room_key(room) for room in chat_rooms}

    by_room = {}
    for proposal in proposals:
        by_room.setdefault(str(proposal['chat_room_id']), []).append(proposal)

    overall = _outcome_counts()
    by_point, by_hour = {}, {}
    upcoming = first_try = 0
    changes = []

    for room_id, room_proposals in by_room.items():
        statuses = statuses_by_room.get(room_keys.get(room_id), set())
        for meetup in (p for p in room_proposals if p['status'] == MeetingProposalStatus.ACCEPTED):
            before = sum(
                1 for p in room_proposals
                if p['status'] in (MeetingProposalStatus.DECLINED, MeetingProposalStatus.CANCELLED)
                and _as_utc(p['created_at']) < _as_utc(meetup['created_at'])
            )
            changes.append(before)
            if before == 0:
                first_try += 1
            if _as_utc(meetup['ends_at']) > now:
                upcoming += 1
                continue

            if ExchangeStatus.COMPLETED in statuses:
                outcome = 'completed'
            elif ExchangeStatus.CANCELLED in statuses:
                outcome = 'cancelled'
            else:
                outcome = 'not_closed'

            point_id = str(meetup['meeting_point_id'])
            hour = _campus_hour(meetup['starts_at'])
            for counts in (
                overall,
                by_point.setdefault(point_id, _outcome_counts()),
                by_hour.setdefault(hour, _outcome_counts()),
            ):
                counts['agreed'] += 1
                counts[outcome] += 1

    point_rows = [
        {
            'meeting_point_id': point_id,
            'name': points.get(point_id, {}).get('name', 'Unknown point'),
            'is_monitored': points.get(point_id, {}).get('is_monitored', False),
            **_with_rate(counts),
        }
        for point_id, counts in by_point.items()
    ]
    point_rows.sort(key=lambda r: (-r['agreed'], -r['completion_rate'], r['name']))
    hour_rows = [{'hour': hour, **_with_rate(counts)} for hour, counts in sorted(by_hour.items())]

    return {
        'overall': {
            **_with_rate(overall),
            'upcoming': upcoming,
            'agreed_first_try_share': _share(first_try, len(changes)),
            'average_changes_before_agreement': round(sum(changes) / len(changes), 2) if changes else 0.0,
        },
        'by_point': point_rows,
        'by_hour': hour_rows,
    }


def meetup_outcomes(request):
    try:
        proposals = list(MeetingProposal.objects.values(
            'chat_room_id', 'status', 'starts_at', 'ends_at', 'created_at', 'meeting_point_id'))
    except ProgrammingError:
        logger.warning('MeetingProposal table is missing; apply the Prisma migration that creates it')
        return JsonResponse({'time_zone': CAMPUS_TIME_ZONE, 'available': False})

    chat_rooms = list(ChatRoom.objects.values('id', 'material_id', 'buyer_id', 'seller_id'))
    exchanges = list(Exchange.objects.values('material_id', 'buyer_id', 'seller_id', 'status'))
    points = {str(p['id']): p for p in MeetingPoint.objects.values('id', 'name', 'is_monitored')}
    summary = summarize_meetup_outcomes(proposals, chat_rooms, exchanges, points, timezone.now())
    return JsonResponse({'time_zone': CAMPUS_TIME_ZONE, 'available': True, **summary})


# Dashboard
# One entry per implemented business question; the sidebar, the overview and each question page read from here.
DASHBOARD_QUESTIONS = [
    {
        'number': 2,
        'title': 'Buyer journey funnel',
        'question': 'How many listings does a buyer open before contacting a seller, and how many before completing an exchange?',
        'endpoint': 'buyer-journey-funnel',
    },
    {
        'number': 3,
        'title': 'Photos and contacts',
        'question': 'Which photos do sellers upload most (number of photos, angles, close-ups of damage), and how does that relate to the number of buyers who contact them?',
        'endpoint': 'photos-vs-contacts',
    },
    {
        'number': 4,
        'title': 'Chat to meeting point',
        'question': 'How many messages do a buyer and a seller exchange in the app chat before they agree on a meeting point, and how long does this conversation take?',
        'endpoint': 'chat-to-meeting-point',
    },
    {
        'number': 5,
        'title': 'Activity by time',
        'question': 'At what time of the day and which days of the week do students publish and browse the most?',
        'endpoint': 'activity-by-time',
    },
    {
        'number': 6,
        'title': 'Category performance',
        'question': 'Which categories of items generate the most listings and the most completed exchanges?',
        'endpoint': 'category-performance',
    },
    {
        'number': 7,
        'title': 'Wishlist and Smart Match',
        'question': 'How many buyers save items in the wishlist, and how many of those saved items end in a purchase after a Smart matching notification?',
        'endpoint': 'wishlist-conversion',
    },
    {
        'number': 8,
        'title': 'Empty listing fields',
        'question': 'Which fields of the listing form do sellers leave empty most often (course, edition, condition, faculty)?',
        'endpoint': 'empty-fields',
    },
    {
        'number': 9,
        'title': 'Price variation',
        'question': 'How do prices of the same item vary (same book edition, same model) between sellers, faculties, and item condition?',
        'endpoint': 'price-variation',
    },
    {
        'number': 10,
        'title': 'Dead listings & patterns',
        'question': 'Which listings are published but never sold, how long do they stay active, and what hidden patterns do they have in common (clustering by price, category, photos, seller rating)?',
        'endpoint': 'dead-listings',
    },
    {
        'number': 11,
        'title': 'Time to sell',
        'question': 'What is the average time (in days) it takes for a newly listed academic item to be marked as sold?',
        'endpoint': 'time-to-sell',
    },
    {
        'number': 12,
        'title': 'Meeting points',
        'question': 'Which specific campus locations (visualized as a heat map) are most frequently used for item exchanges, and how does this density shift during different hours of the day?',
        'endpoint': 'meeting-point-usage',
    },
    {
        'number': 13,
        'title': 'Words before a deal falls through',
        'question': 'What are the most frequently used words and phrases (word cloud) in the in-app chat messages immediately before a transaction is cancelled or abandoned?',
        'endpoint': 'failed-chat-words',
    },
    {
        'number': 14,
        'title': 'Review sentiment',
        'question': 'What is the emotional sentiment (positive, neutral, negative) and the most common keywords found in the written reviews left for buyers and sellers?',
        'endpoint': 'review-sentiment',
    },
    {
        'number': 15,
        'title': 'Average ticket',
        'question': 'What is the average ticket (in COP) of a completed campus sale, overall and for each item condition?',
        'endpoint': 'average-ticket',
    },
    {
        'number': 16,
        'title': 'Meetups that happen',
        'question': 'What share of the meetups agreed in the chat end in a completed exchange, and how often is a meetup changed or dropped, by meeting point and hour of the day?',
        'endpoint': 'meetup-outcomes',
    },
]


def _dashboard_context(current=None):
    questions = [
        {
            **q,
            'url': reverse('dashboard-question', args=[q['number']]),
            'endpoint_url': reverse(q['endpoint']),
        }
        for q in DASHBOARD_QUESTIONS
    ]
    offset = timezone.now().astimezone(ZoneInfo(CAMPUS_TIME_ZONE)).utcoffset().total_seconds() / 3600
    return {
        'questions': questions,
        'current': next((q for q in questions if current and q['number'] == current), None),
        'campus_time_zone': CAMPUS_TIME_ZONE,
        'campus_utc_offset_hours': int(offset),
    }


def dashboard(request):
    return render(request, 'analytics/dashboard/index.html', _dashboard_context())


def dashboard_question(request, number):
    if number not in {q['number'] for q in DASHBOARD_QUESTIONS}:
        raise Http404('No dashboard for this business question')
    return render(request, f'analytics/dashboard/bq{number}.html', _dashboard_context(number))
