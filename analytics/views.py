from django.shortcuts import render

from django.http import JsonResponse
from django.db.models import Count, Func, IntegerField
from django.db.models.functions import ExtractHour, ExtractWeekDay
from .models import Material, AnalyticsEvent, AnalyticsEventType, Exchange

CAMPUS_TIME_ZONE = 'America/Bogota'

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
# TODO: implement

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

    return JsonResponse({
        'time_zone': CAMPUS_TIME_ZONE,
        'hour': hour,
        'data': [
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
        ],
    })
