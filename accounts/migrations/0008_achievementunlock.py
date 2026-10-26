import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0007_challenge'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AchievementUnlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('achievement_key', models.CharField(max_length=40)),
                ('level', models.PositiveIntegerField(default=1)),
                ('unlocked_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achievement_unlocks', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-unlocked_at', 'achievement_key', 'level']},
        ),
        migrations.AddConstraint(
            model_name='achievementunlock',
            constraint=models.UniqueConstraint(fields=('user', 'achievement_key', 'level'), name='unique_user_achievement_level'),
        ),
    ]
