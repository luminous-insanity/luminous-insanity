from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0016_gameodds_injuryreport'),
        ('accounts', '0020_livechat'),
    ]

    operations = [
        # ---- Private leagues -------------------------------------------
        migrations.CreateModel(
            name='League',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60)),
                ('invite_code', models.CharField(editable=False, max_length=8, unique=True)),
                ('is_open', models.BooleanField(default=True, help_text='When off, nobody new can join with the invite code.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owned_leagues', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LeagueMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('league', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='accounts.league')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='league_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['joined_at', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='leaguemembership',
            constraint=models.UniqueConstraint(fields=('league', 'user'), name='unique_league_member'),
        ),

        # ---- Tiebreaker: The Score is Right -----------------------------
        migrations.CreateModel(
            name='TiebreakerGame',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField()),
                ('week', models.PositiveSmallIntegerField()),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='api.game')),
            ],
        ),
        migrations.AddConstraint(
            model_name='tiebreakergame',
            constraint=models.UniqueConstraint(fields=('season', 'week'), name='unique_tiebreaker_game_per_week'),
        ),
        migrations.CreateModel(
            name='TiebreakerPick',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_points', models.PositiveSmallIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tiebreaker_picks', to='api.game')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tiebreaker_picks', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='tiebreakerpick',
            constraint=models.UniqueConstraint(fields=('user', 'game'), name='unique_tiebreaker_pick'),
        ),

        # ---- Chat moderation --------------------------------------------
        migrations.CreateModel(
            name='ChatBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('mute', 'Mute'), ('block', 'Block')], default='mute', max_length=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('blocked', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_blocked_by', to=settings.AUTH_USER_MODEL)),
                ('blocker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_blocks_made', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='chatblock',
            constraint=models.UniqueConstraint(fields=('blocker', 'blocked'), name='unique_chat_block_pair'),
        ),
        migrations.AddConstraint(
            model_name='chatblock',
            constraint=models.CheckConstraint(check=models.Q(('blocker', models.F('blocked')), _negated=True), name='chat_block_not_self'),
        ),
        migrations.CreateModel(
            name='ChatReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body_snapshot', models.CharField(blank=True, default='', max_length=240)),
                ('game_label', models.CharField(blank=True, default='', max_length=80)),
                ('reason', models.CharField(choices=[('harassment', 'Harassment or bullying'), ('hate', 'Hate speech'), ('threat', 'Threats'), ('sexual', 'Sexual content'), ('spam', 'Spam or scam'), ('other', 'Something else')], default='other', max_length=12)),
                ('details', models.CharField(blank=True, default='', max_length=200)),
                ('status', models.CharField(choices=[('open', 'Open'), ('actioned', 'Action taken'), ('dismissed', 'Dismissed')], db_index=True, default='open', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('resolution', models.CharField(blank=True, default='', max_length=200)),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reports', to='accounts.livechatmessage')),
                ('reported_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_reports_against', to=settings.AUTH_USER_MODEL)),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_reports_made', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='chatreport',
            constraint=models.UniqueConstraint(fields=('reporter', 'message'), name='unique_report_per_message'),
        ),
        migrations.CreateModel(
            name='ChatSanction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('until', models.DateTimeField(blank=True, null=True)),
                ('reason', models.CharField(blank=True, default='', max_length=200)),
                ('source', models.CharField(choices=[('staff', 'Staff'), ('auto', 'Automatic')], default='staff', max_length=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('revoked', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_sanctions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='chatsanction',
            index=models.Index(fields=['user', 'revoked'], name='acc_sanction_user_idx'),
        ),
    ]
