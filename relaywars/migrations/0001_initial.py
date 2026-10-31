from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('api', '0014_quarterscore'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='RelayTeam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(db_index=True)),
                ('week', models.PositiveSmallIntegerField(db_index=True)),
                ('name', models.CharField(max_length=40)),
                ('invite_code', models.CharField(editable=False, max_length=32, unique=True)),
                ('is_random', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('recruiting', 'Recruiting'), ('ready', 'Ready'), ('matched', 'Matched')], default='recruiting', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_owned_teams', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='RelayQueueEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField()),
                ('week', models.PositiveSmallIntegerField()),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_queue_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['queued_at']},
        ),
        migrations.CreateModel(
            name='RelayTeamMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('draft_priority', models.PositiveSmallIntegerField(default=0)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='relaywars.relayteam')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['draft_priority', 'joined_at']},
        ),
        migrations.CreateModel(
            name='RelayMatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(db_index=True)),
                ('week', models.PositiveSmallIntegerField(db_index=True)),
                ('lock_at', models.DateTimeField()),
                ('status', models.CharField(choices=[('draft', 'Drafting'), ('active', 'In progress'), ('complete', 'Complete')], default='draft', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('team_a', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='match_as_a', to='relaywars.relayteam')),
                ('team_b', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='match_as_b', to='relaywars.relayteam')),
            ],
        ),
        migrations.CreateModel(
            name='RelayMatchSide',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ability_tokens', models.PositiveSmallIntegerField(default=2)),
                ('current_chain', models.PositiveSmallIntegerField(default=0)),
                ('best_chain', models.PositiveSmallIntegerField(default=0)),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sides', to='relaywars.relaymatch')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='match_sides', to='relaywars.relayteam')),
            ],
        ),
        migrations.CreateModel(
            name='RelayDraftTurn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField()),
                ('skipped', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_assigned_turns', to=settings.AUTH_USER_MODEL)),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='draft_turns', to='relaywars.relaymatch')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='draft_turns', to='relaywars.relayteam')),
            ],
            options={'ordering': ['position']},
        ),
        migrations.CreateModel(
            name='RelayPick',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('picked_side', models.CharField(choices=[('home', 'Home'), ('away', 'Away')], max_length=4)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_picks', to=settings.AUTH_USER_MODEL)),
                ('draft_turn', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pick', to='relaywars.relaydraftturn')),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_picks', to='api.game')),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='picks', to='relaywars.relaymatch')),
                ('selected_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_submitted_picks', to=settings.AUTH_USER_MODEL)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_picks', to='relaywars.relayteam')),
            ],
            options={'ordering': ['game__kickoff', 'created_at']},
        ),
        migrations.CreateModel(
            name='RelayAbility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('jinx', 'Jinx'), ('protect', 'Protection')], max_length=8)),
                ('status', models.CharField(choices=[('pending', 'Voting'), ('active', 'Active'), ('resolved', 'Resolved'), ('expired', 'Expired')], default='pending', max_length=10)),
                ('token_spent', models.BooleanField(default=False)),
                ('reward_granted', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abilities', to='relaywars.relaymatch')),
                ('proposed_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_proposals', to=settings.AUTH_USER_MODEL)),
                ('target_pick', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abilities', to='relaywars.relaypick')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_abilities', to='relaywars.relayteam')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='RelayAbilityVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('approved', models.BooleanField()),
                ('created_at', models.DateTimeField(auto_now=True)),
                ('ability', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='relaywars.relayability')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relaywars_ability_votes', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name='relayqueueentry', constraint=models.UniqueConstraint(fields=('user', 'season', 'week'), name='rw_unique_queue_entry')),
        migrations.AddConstraint(model_name='relayteammember', constraint=models.UniqueConstraint(fields=('team', 'user'), name='rw_unique_team_member')),
        migrations.AddConstraint(model_name='relaymatchside', constraint=models.UniqueConstraint(fields=('match', 'team'), name='rw_unique_match_side')),
        migrations.AddConstraint(model_name='relaydraftturn', constraint=models.UniqueConstraint(fields=('match', 'position'), name='rw_unique_draft_position')),
        migrations.AddConstraint(model_name='relaypick', constraint=models.UniqueConstraint(fields=('match', 'game'), name='rw_unique_game_per_match')),
        migrations.AddConstraint(model_name='relayability', constraint=models.UniqueConstraint(fields=('target_pick', 'kind'), name='rw_one_ability_kind_per_pick')),
        migrations.AddConstraint(model_name='relayabilityvote', constraint=models.UniqueConstraint(fields=('ability', 'user'), name='rw_one_vote_per_member')),
    ]
