# Generated by Django 5.0.2 on 2024-09-12 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_remove_game_game_time_alter_game_game_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='game',
            name='game_date',
            field=models.DateField(),
        ),
    ]
