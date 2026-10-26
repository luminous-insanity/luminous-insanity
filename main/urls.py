# main/urls.py

from django.urls import path
from .views import (
    home, leaderboard, player_profile, react_to_performance, compare_picks, history_view, profile,
    about, contact, privacy, terms,
)

urlpatterns = [
    path('', home, name='home'),
    path('leaderboard/', leaderboard, name='leaderboard'),
    path('leaderboard/compare/<int:user_id>/', compare_picks, name='compare_picks'),
    path('players/<int:user_id>/', player_profile, name='player_profile'),
    path('players/<int:user_id>/react/', react_to_performance, name='react_to_performance'),
    path('history/', history_view, name='history'),
    path('profile/', profile, name='profile'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('privacy/', privacy, name='privacy'),
    path('terms/', terms, name='terms'),
]
