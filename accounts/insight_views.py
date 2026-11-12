"""Pages: My insights (every player) and Site analytics (staff only)."""
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .analytics import build_site_analytics
from .insights import build_insights
from .views import _selected_season


@login_required
def insights_page(request):
    season, seasons = _selected_season(request)
    return render(request, 'accounts/insights.html', {
        'insights': build_insights(request.user, season),
        'selected_season': season,
        'seasons': seasons,
    })


@staff_member_required(login_url='login')
def site_analytics(request):
    return render(request, 'accounts/site_analytics.html', build_site_analytics())
