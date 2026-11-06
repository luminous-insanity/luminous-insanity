from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0015_game_season_week_status_idx'),
        ('accounts', '0019_crossfire_short_index_names'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveChatRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('went_live_at', models.DateTimeField()),
                ('last_message_at', models.DateTimeField()),
                ('game', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='chat_room', to='api.game')),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='LiveChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('say', 'Say'), ('emote', 'Emote'), ('react', 'Reaction'), ('whisper', 'Whisper'), ('system', 'System')], default='say', max_length=8)),
                ('body', models.CharField(max_length=240)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_hidden', models.BooleanField(default=False)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_chat_messages', to=settings.AUTH_USER_MODEL)),
                ('recipient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='live_chat_whispers', to=settings.AUTH_USER_MODEL)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='accounts.livechatroom')),
            ],
            options={
                'ordering': ['id'],
                'indexes': [
                    models.Index(fields=['room', 'id'], name='acc_chat_room_id_idx'),
                    models.Index(fields=['recipient', 'id'], name='acc_chat_rcpt_id_idx'),
                    models.Index(fields=['author', 'id'], name='acc_chat_auth_id_idx'),
                ],
            },
        ),
    ]
