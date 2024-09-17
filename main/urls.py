# main/urls.py

from django.urls import path
from .views import home, history_view

urlpatterns = [
    path('', home, name='home'),
    path('history/', history_view, name='history'),
]
