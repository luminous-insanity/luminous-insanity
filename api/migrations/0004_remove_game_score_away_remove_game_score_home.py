# Generated by Django 5.0.2 on 2024-09-11 14:55

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_score'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='score_away',
        ),
        migrations.RemoveField(
            model_name='game',
            name='score_home',
        ),
    ]
