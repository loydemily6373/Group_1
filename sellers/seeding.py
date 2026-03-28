from decimal import Decimal

from django.core.files.base import ContentFile

from admin.models import ProductApprovalRequest
from accounts.models import User
from buyers.models import Order, SellerShippingAddress

from .models import Product


SEED_IMAGE_BYTES = (
    b'\x89PNG\r\n\x1a\n'
    b'\x00\x00\x00\rIHDR'
    b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
    b'\x90wS\xde'
    b'\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00'
    b'\xc9\xfe\x92\xef'
    b'\x00\x00\x00\x00IEND\xaeB`\x82'
)


# Keep the seed data in one place so both the standalone script and management command share it.
CATEGORY_SEED_PRODUCTS = [
    {'product_name': 'Relaxed Fit Tee', 'category': 'T-Shirt', 'price': Decimal('19.99'), 'stock': 18, 'status': 'approved', 'description': 'Soft cotton t-shirt with a relaxed everyday fit.'},
    {'product_name': 'Oxford Work Shirt', 'category': 'Shirt', 'price': Decimal('34.50'), 'stock': 14, 'status': 'approved', 'description': 'Classic oxford shirt suited for smart casual outfits.'},
    {'product_name': 'Silk Button Blouse', 'category': 'Blouse', 'price': Decimal('42.00'), 'stock': 11, 'status': 'approved', 'description': 'Lightweight blouse with a clean drape and polished finish.'},
    {'product_name': 'Chunky Cable Sweater', 'category': 'Sweater', 'price': Decimal('49.95'), 'stock': 10, 'status': 'approved', 'description': 'Heavy knit sweater built for colder weather.'},
    {'product_name': 'Zip Front Hoodie', 'category': 'Hoodie', 'price': Decimal('36.75'), 'stock': 20, 'status': 'approved', 'description': 'Fleece-lined hoodie with a durable zip front.'},
    {'product_name': 'Straight Leg Jeans', 'category': 'Jeans', 'price': Decimal('54.00'), 'stock': 16, 'status': 'approved', 'description': 'Mid-wash jeans with a straight silhouette.'},
    {'product_name': 'Tailored Office Pants', 'category': 'Pants', 'price': Decimal('46.20'), 'stock': 13, 'status': 'approved', 'description': 'Structured trousers designed for all-day wear.'},
    {'product_name': 'Pleated Midi Skirt', 'category': 'Skirt', 'price': Decimal('38.90'), 'stock': 12, 'status': 'approved', 'description': 'Flowing midi skirt with soft pleated detailing.'},
    {'product_name': 'Utility Cargo Shorts', 'category': 'Shorts', 'price': Decimal('27.40'), 'stock': 17, 'status': 'approved', 'description': 'Casual cargo shorts with roomy side pockets.'},
    {'product_name': 'Studio Stretch Leggings', 'category': 'Leggings', 'price': Decimal('29.99'), 'stock': 22, 'status': 'approved', 'description': 'High-stretch leggings for training or lounging.'},
    {'product_name': 'Floral Wrap Dress', 'category': 'Dress', 'price': Decimal('58.00'), 'stock': 9, 'status': 'approved', 'description': 'Printed wrap dress with a lightweight feel.'},
    {'product_name': 'Vintage Denim Jacket', 'category': 'Jacket', 'price': Decimal('59.99'), 'stock': 12, 'status': 'approved', 'description': 'Classic washed denim jacket with a relaxed fit.'},
    {'product_name': 'Coastal Swim Set', 'category': 'Swimwear', 'price': Decimal('31.50'), 'stock': 15, 'status': 'approved', 'description': 'Quick-dry swimwear set for beach weekends.'},
    {'product_name': 'Cotton Sleep Set', 'category': 'Sleepwear', 'price': Decimal('24.80'), 'stock': 19, 'status': 'approved', 'description': 'Breathable sleepwear set with a soft finish.'},
    {'product_name': 'Canvas High-Top Sneakers', 'category': 'Shoes', 'price': Decimal('44.50'), 'stock': 20, 'status': 'approved', 'description': 'Lightweight everyday sneakers with durable canvas uppers.'},
    {'product_name': 'Leather Crossbody Bag', 'category': 'Accessories', 'price': Decimal('78.00'), 'stock': 8, 'status': 'approved', 'description': 'Compact crossbody bag with adjustable strap and zip closure.'},
]

EXTRA_SEED_PRODUCTS = [
    {'product_name': 'Graphic Street Tee', 'category': 'T-Shirt', 'price': Decimal('21.50'), 'stock': 25, 'status': 'approved', 'description': 'Statement t-shirt with a bold front graphic.'},
    {'product_name': 'Resort Linen Shirt', 'category': 'Shirt', 'price': Decimal('39.95'), 'stock': 10, 'status': 'approved', 'description': 'Breathable linen shirt ideal for warmer weather.'},
    {'product_name': 'Office Silk Blouse', 'category': 'Blouse', 'price': Decimal('44.10'), 'stock': 9, 'status': 'approved', 'description': 'Refined blouse with a smooth office-ready finish.'},
    {'product_name': 'Oversized Knit Sweater', 'category': 'Sweater', 'price': Decimal('39.95'), 'stock': 15, 'status': 'approved', 'description': 'Soft heavyweight knit sweater designed for cooler weather.'},
    {'product_name': 'Minimalist Pullover Hoodie', 'category': 'Hoodie', 'price': Decimal('41.25'), 'stock': 14, 'status': 'approved', 'description': 'Clean pullover hoodie with a minimal chest logo.'},
    {'product_name': 'Black Skinny Jeans', 'category': 'Jeans', 'price': Decimal('52.75'), 'stock': 12, 'status': 'approved', 'description': 'Stretch black denim with a slim cut.'},
    {'product_name': 'Relaxed Weekend Pants', 'category': 'Pants', 'price': Decimal('35.00'), 'stock': 16, 'status': 'approved', 'description': 'Comfort-first casual pants for weekend wear.'},
    {'product_name': 'Corduroy Mini Skirt', 'category': 'Skirt', 'price': Decimal('33.30'), 'stock': 7, 'status': 'approved', 'description': 'Textured corduroy skirt with a structured shape.'},
    {'product_name': 'Running Trail Shorts', 'category': 'Shorts', 'price': Decimal('26.60'), 'stock': 18, 'status': 'approved', 'description': 'Lightweight shorts designed for trail sessions.'},
    {'product_name': 'Essential Training Leggings', 'category': 'Leggings', 'price': Decimal('34.00'), 'stock': 13, 'status': 'approved', 'description': 'Training leggings with supportive compression.'},
    {'product_name': 'Evening Slip Dress', 'category': 'Dress', 'price': Decimal('64.00'), 'stock': 6, 'status': 'approved', 'description': 'Elegant slip dress with a soft sheen.'},
    {'product_name': 'Rainproof Utility Jacket', 'category': 'Jacket', 'price': Decimal('72.00'), 'stock': 11, 'status': 'approved', 'description': 'Weather-ready jacket with sealed seams.'},
    {'product_name': 'Minimalist Analog Watch', 'category': 'Accessories', 'price': Decimal('64.25'), 'stock': 10, 'status': 'pending', 'description': 'Simple matte-finish watch with a clean dial and slim profile.'},
    {'product_name': 'Running Trail Shoes', 'category': 'Shoes', 'price': Decimal('89.99'), 'stock': 0, 'status': 'approved', 'description': 'Grip-focused trail shoes built for uneven outdoor surfaces.'},
]

SEED_PRODUCTS = CATEGORY_SEED_PRODUCTS + EXTRA_SEED_PRODUCTS


def clear_products():
    # Order items protect products, so clear related checkout and approval data before removing products.
    deleted_total = 0

    deleted_count, _ = ProductApprovalRequest.objects.all().delete()
    deleted_total += deleted_count

    deleted_count, _ = Order.objects.all().delete()
    deleted_total += deleted_count

    for product in Product.objects.exclude(image='').exclude(image__isnull=True):
        product.image.delete(save=False)

    deleted_count, _ = Product.objects.all().delete()
    deleted_total += deleted_count
    return deleted_total


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
    update_fields = []

    # Always enforce the known seed credentials so the account is usable even if it already existed in a bad state.
    if not seller.check_password('SeedSeller123!'):
        seller.set_password('SeedSeller123!')
        update_fields.append('password')

    if seller.role != 'seller':
        seller.role = 'seller'
        update_fields.append('role')

    if not seller.email:
        seller.email = 'seed_seller@example.com'
        update_fields.append('email')

    if not seller.first_name:
        seller.first_name = 'Seed'
        update_fields.append('first_name')

    if not seller.last_name:
        seller.last_name = 'Seller'
        update_fields.append('last_name')

    if update_fields:
        seller.save(update_fields=update_fields)

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
    # Create all test products with placeholder images so the catalogue UI can be exercised end to end.
    seller = _get_seed_seller()

    for index, product_data in enumerate(SEED_PRODUCTS, start=1):
        product = Product.objects.create(
            seller_id=seller,
            active=True,
            redirect_to=None,
            deleted_at=None,
            **product_data,
        )
        product.image.save(
            f'seed-product-{index}.png',
            ContentFile(SEED_IMAGE_BYTES),
            save=True,
        )

    return len(SEED_PRODUCTS)


def reset_products():
    # Reset first so repeated test runs always start from the same data.
    deleted_count = clear_products()
    seeded_count = seed_products()
    return deleted_count, seeded_count