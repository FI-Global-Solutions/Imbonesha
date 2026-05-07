from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        # UUID → bigint can't be cast directly in Postgres; drop and recreate.
        migrations.RemoveField(
            model_name='notificationlog',
            name='related_flag_id',
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='related_flag_id',
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
