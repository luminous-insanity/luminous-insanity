from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0010_playeridentity')]

    operations = [
        migrations.CreateModel(
            name='PlayoffSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(unique=True)),
                ('qualifiers_per_division', models.PositiveSmallIntegerField(default=4)),
            ],
            options={
                'verbose_name': 'playoff settings',
                'verbose_name_plural': 'playoff settings',
            },
        ),
    ]
