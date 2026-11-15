from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mobileapi', '0003_idempotency_request_hash'),
    ]
    operations = [
        migrations.AlterField(
            model_name='notificationpreference',
            name='pick_reminders',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='PickReminderLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField()),
                ('week', models.PositiveSmallIntegerField()),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='pick_reminder_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'season', 'week'), name='mobile_unique_pick_reminder')],
            },
        ),
    ]
