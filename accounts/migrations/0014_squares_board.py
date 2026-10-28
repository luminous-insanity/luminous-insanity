import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0014_quarterscore'),
        ('accounts', '0013_playoff_entries_and_cuts'),
    ]

    operations = [
        migrations.CreateModel(
            name='SquaresBoard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(unique=True)),
                ('home_digits', models.CharField(blank=True, default='', max_length=10)),
                ('away_digits', models.CharField(blank=True, default='', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='squares_boards', to='api.game')),
            ],
            options={
                'verbose_name_plural': 'squares boards',
            },
        ),
        migrations.CreateModel(
            name='BoardSquare',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row', models.PositiveSmallIntegerField()),
                ('col', models.PositiveSmallIntegerField()),
                ('board', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='squares', to='accounts.squaresboard')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='board_squares', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['row', 'col'],
            },
        ),
        migrations.AddConstraint(
            model_name='boardsquare',
            constraint=models.UniqueConstraint(fields=('board', 'row', 'col'), name='unique_square_per_board'),
        ),
    ]
