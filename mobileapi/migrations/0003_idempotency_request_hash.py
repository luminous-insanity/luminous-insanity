from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('mobileapi', '0002_idempotencyrecord')]
    operations = [
        migrations.AddField(
            model_name='idempotencyrecord',
            name='request_hash',
            field=models.CharField(default='', max_length=64),
            preserve_default=False,
        ),
    ]
