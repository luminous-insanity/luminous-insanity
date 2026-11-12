from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_game_season_week_status_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameOdds',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('spread_home', models.DecimalField(blank=True, decimal_places=1, help_text='Home-team spread. Negative = home favored, positive = away favored.', max_digits=4, null=True)),
                ('total_points', models.DecimalField(blank=True, decimal_places=1, help_text='Over/under for combined points.', max_digits=4, null=True)),
                ('moneyline_home', models.IntegerField(blank=True, null=True)),
                ('moneyline_away', models.IntegerField(blank=True, null=True)),
                ('sportsbook', models.CharField(blank=True, default='', max_length=40)),
                ('source', models.CharField(blank=True, default='manual', max_length=20)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('game', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='odds', to='api.game')),
            ],
            options={
                'verbose_name': 'game odds',
                'verbose_name_plural': 'game odds',
            },
        ),
        migrations.CreateModel(
            name='InjuryReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.IntegerField(db_index=True)),
                ('week', models.IntegerField()),
                ('team', models.CharField(max_length=100)),
                ('player_name', models.CharField(max_length=80)),
                ('position', models.CharField(blank=True, default='', max_length=8)),
                ('status', models.CharField(choices=[('out', 'Out'), ('doubtful', 'Doubtful'), ('questionable', 'Questionable'), ('probable', 'Probable'), ('ir', 'Injured reserve')], default='questionable', max_length=12)),
                ('detail', models.CharField(blank=True, default='', help_text='Body part or note, e.g. "Knee".', max_length=120)),
                ('is_key_player', models.BooleanField(default=False, help_text='Starter or star. Key players are listed first.')),
                ('source', models.CharField(blank=True, default='manual', max_length=20)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='injuryreport',
            index=models.Index(fields=['season', 'week', 'team'], name='api_injury_szn_wk_team_idx'),
        ),
        migrations.AddConstraint(
            model_name='injuryreport',
            constraint=models.UniqueConstraint(fields=('season', 'week', 'team', 'player_name'), name='unique_injury_per_player_week'),
        ),
    ]
