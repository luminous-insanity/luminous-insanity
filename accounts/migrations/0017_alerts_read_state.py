from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0016_gamereaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='friendrequest',
            name='receiver_seen',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='performancereaction',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
    ]
