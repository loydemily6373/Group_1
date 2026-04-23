from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buyers', '0010_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='discount_percent_applied',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
