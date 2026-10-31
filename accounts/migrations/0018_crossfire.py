from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0014_quarterscore'),
        ('accounts', '0017_alerts_read_state'),
    ]

    operations = [
        migrations.CreateModel(
            name='Crossfire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveIntegerField(db_index=True)),
                ('week', models.PositiveIntegerField(db_index=True)),
                ('attacker_side', models.CharField(choices=[('home', 'Home Team'), ('away', 'Away Team')], max_length=10)),
                ('target_side', models.CharField(choices=[('home', 'Home Team'), ('away', 'Away Team')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('attacker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crossfires_fired', to=settings.AUTH_USER_MODEL)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crossfires', to='api.game')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crossfires_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='crossfire',
            constraint=models.UniqueConstraint(fields=('attacker', 'game'), name='unique_crossfire_per_attacker_game'),
        ),
        migrations.AddConstraint(
            model_name='crossfire',
            constraint=models.CheckConstraint(check=~models.Q(attacker=models.F('target')), name='crossfire_not_self'),
        ),
        migrations.AddIndex(
            model_name='crossfire',
            index=models.Index(fields=['season', 'week'], name='accounts_cr_season_week_idx'),
        ),
        migrations.AddIndex(
            model_name='crossfire',
            index=models.Index(fields=['target', 'season', 'week'], name='accounts_cr_target_season_idx'),
        ),
    ]
