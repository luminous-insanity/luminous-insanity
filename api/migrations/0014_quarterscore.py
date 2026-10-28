import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0013_game_away_score_game_home_score_game_kickoff_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuarterScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quarter', models.PositiveSmallIntegerField(choices=[(1, 'End of Q1'), (2, 'Halftime'), (3, 'End of Q3')])),
                ('home_score', models.PositiveSmallIntegerField()),
                ('away_score', models.PositiveSmallIntegerField()),
                ('source', models.CharField(default='manual', max_length=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quarter_scores', to='api.game')),
            ],
            options={
                'ordering': ['game', 'quarter'],
            },
        ),
        migrations.AddConstraint(
            model_name='quarterscore',
            constraint=models.UniqueConstraint(fields=('game', 'quarter'), name='unique_quarter_score_per_game'),
        ),
    ]
