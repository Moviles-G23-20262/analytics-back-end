from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.category_performance, name='category-performance'),
    path('activity-times/', views.activity_by_time, name='activity-by-time'),
]