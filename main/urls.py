# main/urls.py

from django.urls import path
from .views import home, leaderboard, history_view, profile, about, contact, privacy, terms

urlpatterns = [
    path('', home, name='home'),
    path('leaderboard/', leaderboard, name='leaderboard'),
    path('history/', history_view, name='history'),
    path('profile/', profile, name='profile'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('privacy/', privacy, name='privacy'),
    path('terms/', terms, name='terms'),
]
