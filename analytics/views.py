from django.shortcuts import render

from django.http import JsonResponse
from django.db.models import Count
from .models import Material

# Business Question 5
# TODO: implement

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