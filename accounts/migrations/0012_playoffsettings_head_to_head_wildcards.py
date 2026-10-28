from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0011_playoffsettings')]

    operations = [
        migrations.AddField(
            model_name='playoffsettings',
            name='head_to_head_wildcard_spots',
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
