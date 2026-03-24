from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_products(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Product = apps.get_model('products', 'Product')

    # Create a fallback seller so legacy rows can satisfy the new non-null seller relationship.
    fallback_seller, _ = User.objects.get_or_create(
        username='legacy_product_owner',
        defaults={
            'first_name': 'Legacy',
            'last_name': 'Owner',
            'email': 'legacy_product_owner@example.com',
            'role': 'seller',
        },
    )

    category_map = {
        'Clothing': 'Shirt',
        'Shoes': 'Shoes',
        'Accessories': 'Accessories',
        'Other': 'Accessories',
    }

    for product in Product.objects.all():
        product.seller_id_id = fallback_seller.id
        product.active = bool(getattr(product, 'approved', False))
        product.status = getattr(product, 'approval_status', 'pending') or 'pending'
        product.category = category_map.get(product.category, product.category)
        product.save(update_fields=['seller_id', 'active', 'status', 'category'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0003_product_approval_status_product_approved'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='active',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='redirect_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='redirected_products', to='products.product'),
        ),
        migrations.AddField(
            model_name='product',
            name='seller_id',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(migrate_existing_products, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='product',
            name='approval_status',
        ),
        migrations.RemoveField(
            model_name='product',
            name='approved',
        ),
        migrations.AlterField(
            model_name='product',
            name='category',
            field=models.CharField(choices=[('T-Shirt', 'T-Shirt'), ('Shirt', 'Shirt'), ('Blouse', 'Blouse'), ('Sweater', 'Sweater'), ('Hoodie', 'Hoodie'), ('Jeans', 'Jeans'), ('Pants', 'Pants'), ('Skirt', 'Skirt'), ('Shorts', 'Shorts'), ('Leggings', 'Leggings'), ('Dress', 'Dress'), ('Jacket', 'Jacket'), ('Swimwear', 'Swimwear'), ('Sleepwear', 'Sleepwear'), ('Shoes', 'Shoes'), ('Accessories', 'Accessories')], max_length=50),
        ),
        migrations.AlterField(
            model_name='product',
            name='seller_id',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='product',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=10),
        ),
    ]
