import unicodedata
from zoneinfo import ZoneInfo

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from django.http import JsonResponse
import logging

from django.db import DataError, ProgrammingError
from django.db import ProgrammingError
from django.db.models import Count, F, Func, IntegerField, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay
from .models import Material, AnalyticsEvent, AnalyticsEventType
from .models import Exchange, Notification, NotificationType, WishlistItem
from .models import Material, AnalyticsEvent, AnalyticsEventType, Exchange, ExchangeStatus
from .models import ChatRoom, Message, MaterialCategory, MaterialCondition

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

# Business Question 10
# TODO: implement

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

# Business Question 14 - Average ticket: what a completed sale is worth, overall and per item condition.

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
