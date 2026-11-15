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
    activity_page,
    activity_open,
)
from .account_views import delete_account_page
from .share_views import share_perfect_week, share_challenge, my_share_links
from .chat_views import (
    chat_status, chat_poll, chat_start, chat_send,
    chat_report, chat_block, chat_blocks,
)
from .tiebreaker_views import tiebreaker_save
from .insight_views import insights_page, site_analytics
from .league_views import (
    leagues_home, league_create, league_join, league_join_link,
    league_detail, league_manage,
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
    path('delete/', delete_account_page, name='delete_account'),
    path('activity/', activity_page, name='activity'),
    path('activity/open/', activity_open, name='activity_open'),
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
    path('tiebreaker/<str:game_id>/', tiebreaker_save, name='tiebreaker_save'),
    path('insights/', insights_page, name='insights'),
    path('staff/analytics/', site_analytics, name='site_analytics'),
    path('leagues/', leagues_home, name='leagues'),
    path('leagues/new/', league_create, name='league_create'),
    path('leagues/join/', league_join, name='league_join'),
    path('leagues/join/<str:code>/', league_join_link, name='league_join_link'),
    path('leagues/<int:league_id>/', league_detail, name='league_detail'),
    path('leagues/<int:league_id>/manage/', league_manage, name='league_manage'),
    path('chat/status/', chat_status, name='chat_status'),
    path('chat/report/', chat_report, name='chat_report'),
    path('chat/block/', chat_block, name='chat_block'),
    path('chat/blocks/', chat_blocks, name='chat_blocks'),
    path('chat/<str:game_id>/poll/', chat_poll, name='chat_poll'),
    path('chat/<str:game_id>/start/', chat_start, name='chat_start'),
    path('chat/<str:game_id>/send/', chat_send, name='chat_send'),
]
