from django.urls import path
from .views import (
    signup_view,
    login_view,
    logout_view,
    dashboard,
    achievements_page,
    make_pick,
    picks,
    friend_search,
    send_friend_request,
    respond_friend_request,
)
from .challenge_views import (
    challenges,
    challenge_new,
    challenge_respond,
    challenge_detail,
)

urlpatterns = [
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('achievements/', achievements_page, name='achievements'),
    path('picks/', picks, name='picks'),
    path('make_pick/<str:game_id>/', make_pick, name='make_pick'),
    path('friends/search/', friend_search, name='friend_search'),
    path('challenges/', challenges, name='challenges'),
    path('challenges/new/<int:user_id>/', challenge_new, name='challenge_new'),
    path(
        'challenges/<int:challenge_id>/respond/<str:action>/',
        challenge_respond,
        name='challenge_respond',
    ),
    path('challenges/<int:challenge_id>/', challenge_detail, name='challenge_detail'),
    path(
        'friends/request/<int:user_id>/',
        send_friend_request,
        name='send_friend_request',
    ),
    path(
        'friends/respond/<int:request_id>/<str:action>/',
        respond_friend_request,
        name='respond_friend_request',
    ),
]
