from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.category_performance, name='category-performance'),
    path('activity-times/', views.activity_by_time, name='activity-by-time'),
    path('wishlist-conversion/', views.wishlist_smart_match_conversion, name='wishlist-conversion'),
    path('empty-fields/', views.empty_fields, name='empty-fields'),
    path('price-variation/', views.price_variation, name='price-variation'),
    path('time-to-sell/', views.time_to_sell, name='time-to-sell'),
    path('average-ticket/', views.average_ticket, name='average-ticket'),
    path('meeting-points/', views.meeting_point_usage, name='meeting-point-usage'),
    path('buyer-journey-funnel/', views.buyer_journey_funnel, name='buyer-journey-funnel'),
    path('price-stats/', views.price_stats, name='price-stats'),
    path('chat-to-meeting-point/', views.chat_to_meeting_point, name='chat-to-meeting-point'),
    path('chat-agreement/<uuid:chat_room_id>/', views.chat_agreement, name='chat-agreement'),
]