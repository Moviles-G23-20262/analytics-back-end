"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from analytics.views import dashboard, dashboard_question

def api_root(request):
    return JsonResponse({
        "message": "Welcome to the API",
        "dashboard": "/dash-board/",
        "endpoints": {
            "categories": "/analytics/categories/",
            "activity_times": "/analytics/activity-times/",
            "wishlist_conversion": "/analytics/wishlist-conversion/",
            "meeting_points": "/analytics/meeting-points/",
            "buyer_journey_funnel": "/analytics/buyer-journey-funnel/",
            "chat_to_meeting_point": "/analytics/chat-to-meeting-point/"
        }
    })

urlpatterns = [
    # path('admin/', admin.site.urls),
    path('', api_root),  # Maps default URL to api_root
    path('dash-board/', dashboard, name='dashboard'),
    path('dash-board/bq<int:number>/', dashboard_question, name='dashboard-question'),
    path('analytics/', include('analytics.urls')),
]