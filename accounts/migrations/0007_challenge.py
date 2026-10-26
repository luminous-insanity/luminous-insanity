import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_useractivity_championrevealseen'),
        ('api', '0013_game_away_score_game_home_score_game_kickoff_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Challenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(choices=[('game', 'Single game'), ('week', 'Whole week')], max_length=10)),
                ('season', models.IntegerField()),
                ('week', models.IntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('challenger', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='challenges_sent', to=settings.AUTH_USER_MODEL)),
                ('game', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='challenges', to='api.game')),
                ('opponent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='challenges_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='challenge',
            constraint=models.CheckConstraint(check=models.Q(('challenger', models.F('opponent')), _negated=True), name='prevent_self_challenge'),
        ),
    ]
