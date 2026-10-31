from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0014_quarterscore'),
        ('accounts', '0015_pick_confidence_and_title'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emoji', models.CharField(choices=[('🔥', 'Fire'), ('😱', 'Shock'), ('💪', 'Clutch'), ('💔', 'Heartbreak'), ('🎉', 'Party')], max_length=8)),
                ('created_at', models.DateTimeField(auto_now=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='api.game')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_reactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='gamereaction',
            constraint=models.UniqueConstraint(fields=('user', 'game'), name='unique_user_game_reaction'),
        ),
    ]
