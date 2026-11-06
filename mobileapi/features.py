from .common import *

class PlayerFeatureSummaryView(APIView):
    """Read-only wrappers around existing feature calculators; no duplicate scoring."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.achievements import achievement_summary
        from accounts.quests import build_weekly_quests
        from accounts.path_to_playoffs import path_to_playoffs
        from accounts.recap import build_week_recap
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', current_week()))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)

        recap = build_week_recap(request.user, season=season, week=week)
        standing = recap['standing']
        recap_data = {
            'season': recap['season'], 'week': recap['week'],
            'wins': recap['wins'], 'losses': recap['losses'], 'ties': recap['ties'],
            'pending': recap['pending'], 'record': recap['record'],
            'standing': {'wins': standing.wins, 'losses': standing.losses,
                         'ties': standing.ties, 'completed': standing.completed,
                         'win_pct': standing.win_pct},
            'confidence_points': recap['confidence_points'],
            'underdog_locks': recap['underdog_locks'],
            'highlights': recap['highlights'], 'reactions': recap['reactions'],
            'games_total': recap['games_total'], 'games_final': recap['games_final'],
            'week_complete': recap['week_complete'], 'picked_count': recap['picked_count'],
            'friends': [{
                'user_id': row['user'].id, 'username': row['user'].username,
                'wins': row['wins'], 'losses': row['losses'], 'ties': row['ties'],
                'rank': row['rank'], 'is_me': row['is_me'],
            } for row in recap['friend_rows']],
        }
        return Response({
            'season': season, 'week': week,
            'quests': build_weekly_quests(request.user, season=season, week=week),
            'achievements': achievement_summary(request.user),
            'playoff_path': path_to_playoffs(request.user, season=season),
            'recap': recap_data,
        })


