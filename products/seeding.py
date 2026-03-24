from decimal import Decimal

from accounts.models import User
from buyers.models import SellerShippingAddress

from .models import Product


# Keep the seed data in one place so both the standalone script and management command share it.
SEED_PRODUCTS = [
    {
        'product_name': 'Vintage Denim Jacket',
        'category': 'Jacket',
        'price': Decimal('59.99'),
        'stock': 12,
        'status': 'approved',
        'description': 'Classic washed denim jacket with a relaxed fit.',
    },
    {
        'product_name': 'Canvas High-Top Sneakers',
        'category': 'Shoes',
        'price': Decimal('44.50'),
        'stock': 20,
        'status': 'approved',
        'description': 'Lightweight everyday sneakers with durable canvas uppers.',
    },
    {
        'product_name': 'Leather Crossbody Bag',
        'category': 'Accessories',
        'price': Decimal('78.00'),
        'stock': 8,
        'status': 'approved',
        'description': 'Compact crossbody bag with adjustable strap and zip closure.',
    },
    {
        'product_name': 'Oversized Knit Sweater',
        'category': 'Sweater',
        'price': Decimal('39.95'),
        'stock': 15,
        'status': 'approved',
        'description': 'Soft heavyweight knit sweater designed for cooler weather.',
    },
    {
        'product_name': 'Minimalist Analog Watch',
        'category': 'Accessories',
        'price': Decimal('64.25'),
        'stock': 10,
        'status': 'pending',
        'description': 'Simple matte-finish watch with a clean dial and slim profile.',
    },
    {
        'product_name': 'Running Trail Shoes',
        'category': 'Shoes',
        'price': Decimal('89.99'),
        'stock': 0,
        'status': 'approved',
        'description': 'Grip-focused trail shoes built for uneven outdoor surfaces.',
    },
]


def clear_products():
    # Deleting Product rows also removes dependent cart and sale rows through cascading foreign keys.
    deleted_count, _ = Product.objects.all().delete()
    return deleted_count


def _get_seed_seller():
    # Seeded products need a valid seller now that the schema stores seller ownership.
    seller, _ = User.objects.get_or_create(
        username='seed_seller',
        defaults={
            'first_name': 'Seed',
            'last_name': 'Seller',
            'email': 'seed_seller@example.com',
            'role': 'seller',
        },
    )
    if not seller.has_usable_password():
        seller.set_password('SeedSeller123!')
        seller.save(update_fields=['password'])
    elif not seller.role:
        seller.role = 'seller'
        seller.save(update_fields=['role'])
    SellerShippingAddress.objects.get_or_create(
        seller=seller,
        label='Seed Warehouse',
        defaults={
            'recipient_name': 'Seed Seller',
            'address_line_1': '1 Seed Warehouse Way',
            'city': 'Dublin',
            'state': 'Leinster',
            'postal_code': 'D01SEED',
            'country': 'Ireland',
            'is_default': True,
        },
    )
    return seller


def seed_products():
    # Create all test products in a single pass so the database is ready for UI testing.
    seller = _get_seed_seller()
    products = [
        Product(
            seller_id=seller,
            active=True,
            redirect_to=None,
            deleted_at=None,
            **product_data,
        )
        for product_data in SEED_PRODUCTS
    ]
    Product.objects.bulk_create(products)
    return len(products)


def reset_products():
    # Reset first so repeated test runs always start from the same data.
    deleted_count = clear_products()
    seeded_count = seed_products()
    return deleted_count, seeded_count