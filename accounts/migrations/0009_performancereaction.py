import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0008_achievementunlock'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PerformanceReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveIntegerField()),
                ('week', models.PositiveSmallIntegerField()),
                ('emoji', models.CharField(choices=[('👏', 'Clap'), ('🔥', 'Fire'), ('👑', 'Crown')], max_length=8)),
                ('created_at', models.DateTimeField(auto_now=True)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='performance_reactions_received', to=settings.AUTH_USER_MODEL)),
                ('reactor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='performance_reactions_sent', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(model_name='performancereaction', constraint=models.UniqueConstraint(fields=('reactor', 'player', 'season', 'week'), name='unique_weekly_performance_reaction')),
        migrations.AddConstraint(model_name='performancereaction', constraint=models.CheckConstraint(check=~models.Q(reactor=models.F('player')), name='prevent_self_performance_reaction')),
    ]
