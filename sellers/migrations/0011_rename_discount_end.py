# Adds discount fields to Product and renames discount_end -> discount_end_date

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0010_remove_notification_buyer_email_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='discount_percent',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='discount_start_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='discount_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RenameField(
            model_name='product',
            old_name='discount_end',
            new_name='discount_end_date',
        ),
    ]
