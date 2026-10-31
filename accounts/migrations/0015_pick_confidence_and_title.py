from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_squares_board'),
    ]

    operations = [
        migrations.AddField(
            model_name='pick',
            name='confidence',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, 'Lean'), (2, 'Solid'), (3, 'Lock')],
                help_text='Optional. Higher confidence on correct picks earns Confidence Points.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='playeridentity',
            name='active_title',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Unlockable title shown on profile and leaderboard.',
                max_length=40,
            ),
        ),
    ]
