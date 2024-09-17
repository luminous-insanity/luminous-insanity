from django.contrib import admin
from .models import Pick, UserStatistics  # Import the models

# Register the Pick model
@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'team_picked')  # Columns to display in admin list view
    list_filter = ('team_picked',)  # Add a filter by team picked
    search_fields = ('user__username', 'game__game_id')  # Add search fields for user and game

# Register the UserStatistics model
@admin.register(UserStatistics)
class UserStatisticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'wins', 'losses', 'ties')  # Display user statistics
    search_fields = ('user__username',)  # Add search field for user
