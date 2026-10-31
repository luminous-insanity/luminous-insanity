from django.urls import path
from .crossfire_views import (
    crossfire_board,
    crossfire_aim,
    crossfire_fire,
    crossfire_cancel,
)
from .views import (
    signup_view,
    login_view,
    logout_view,
    dashboard,
    mark_alerts_read,
    achievements_page,
    make_pick,
    picks,
    friend_search,
    send_friend_request,
    respond_friend_request,
    equip_title_view,
    react_to_game,
    week_recap,
)
from .share_views import share_perfect_week, share_challenge, my_share_links
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
    path('alerts/read/', mark_alerts_read, name='mark_alerts_read'),
    path('achievements/', achievements_page, name='achievements'),
    path('picks/', picks, name='picks'),
    path('crossfire/', crossfire_board, name='crossfire'),
    path('crossfire/aim/<str:game_id>/', crossfire_aim, name='crossfire_aim'),
    path('crossfire/fire/<str:game_id>/<int:user_id>/', crossfire_fire, name='crossfire_fire'),
    path('crossfire/cancel/<int:crossfire_id>/', crossfire_cancel, name='crossfire_cancel'),

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
    path('share/perfect/<int:user_id>/<int:season>/<int:week>/', share_perfect_week, name='share_perfect_week'),
    path('share/challenge/<int:challenge_id>/', share_challenge, name='share_challenge'),
    path('share/', my_share_links, name='share_hub'),
    path('titles/equip/', equip_title_view, name='equip_title'),
    path('react/game/<str:game_id>/', react_to_game, name='react_to_game'),
    path('recap/', week_recap, name='week_recap'),
]
