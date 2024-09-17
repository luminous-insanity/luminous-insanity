# accounts/urls.py

from django.urls import path
from .views import signup_view, login_view, logout_view, dashboard, make_pick

urlpatterns = [
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('make_pick/<str:game_id>/', make_pick, name='make_pick'),
]
