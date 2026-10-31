from django.urls import path
from . import views

app_name = 'relaywars'

urlpatterns = [
    path('', views.relay_home, name='home'),
    path('join/<str:invite_code>/', views.join_team, name='join_team'),
    path('team/<int:team_id>/leave/', views.leave_team_view, name='leave_team'),
    path('match/<int:match_id>/', views.match_detail, name='match'),
    path('queue/leave/', views.leave_queue, name='leave_queue'),
]
