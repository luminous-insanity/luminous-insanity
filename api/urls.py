# api/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('sync/', views.sync_view, name='sync'),
]
