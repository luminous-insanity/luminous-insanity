import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0012_playoffsettings_head_to_head_wildcards'),
    ]

    operations = [
        migrations.AddField(
            model_name='playoffsettings',
            name='qualifier_percent',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='playoffsettings',
            name='field_target',
            field=models.PositiveSmallIntegerField(default=50),
        ),
        migrations.AddField(
            model_name='playoffsettings',
            name='first_playoff_week',
            field=models.PositiveSmallIntegerField(default=19),
        ),
        migrations.AddField(
            model_name='playoffsettings',
            name='rounds_cut',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='PlayoffEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(db_index=True)),
                ('route', models.CharField(blank=True, default='', max_length=80)),
                ('division', models.CharField(blank=True, default='', max_length=12)),
                ('regular_win_pct', models.FloatField(default=0)),
                ('head_to_head_wins', models.PositiveSmallIntegerField(default=0)),
                ('tiebreak_draw', models.BigIntegerField(default=0)),
                ('status', models.CharField(choices=[('active', 'Active'), ('eliminated', 'Eliminated')], default='active', max_length=12)),
                ('eliminated_round', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='playoff_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'playoff entries',
            },
        ),
        migrations.AddConstraint(
            model_name='playoffentry',
            constraint=models.UniqueConstraint(fields=('user', 'season'), name='unique_playoff_entry_per_season'),
        ),
    ]
