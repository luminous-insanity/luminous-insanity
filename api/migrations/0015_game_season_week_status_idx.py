# Generated manually for performance: common filters are season+week and season+week+status.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_quarterscore'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='game',
            index=models.Index(fields=['season', 'week'], name='api_game_szn_wk_idx'),
        ),
        migrations.AddIndex(
            model_name='game',
            index=models.Index(fields=['season', 'week', 'status'], name='api_game_szn_wk_st_idx'),
        ),
    ]
