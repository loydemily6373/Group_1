import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from decimal import Decimal
from django.utils import timezone

from accounts.models import User
from sellers.models import Product

from .models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, SellerShippingAddress


TEST_PNG_BYTES = (
	b'\x89PNG\r\n\x1a\n'
	b'\x00\x00\x00\rIHDR'
	b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
	b'\x90wS\xde'
	b'\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00'
	b'\xc9\xfe\x92\xef'
	b'\x00\x00\x00\x00IEND\xaeB`\x82'
)


class DatabaseCartTests(TestCase):
	def setUp(self):
		# Build a real buyer and product so the database-backed cart can be exercised end to end.
		self.buyer = User.objects.create_user(
			username='buyer1',
			password='StrongPass123!',
			first_name='Buyer',
			last_name='One',
			email='buyer1@example.com',
			role='buyer',
		)
		self.product = Product.objects.create(
			seller_id=self.buyer,
			product_name='Jacket',
			category='Clothing',
			price='25.00',
			stock=10,
			active=True,
			redirect_to=None,
			status='approved',
			description='A warm jacket',
			deleted_at=None,
		)
		self.client.force_login(self.buyer)

	def test_add_to_cart_creates_database_row(self):
		# Adding to cart should persist a cart row for the logged-in buyer.
		response = self.client.get(reverse('add_to_cart', args=[self.product.id]))

		self.assertRedirects(response, reverse('buyer_home'))
		self.assertEqual(CartItem.objects.count(), 1)
		cart_item = CartItem.objects.get(buyer=self.buyer, product=self.product)
		self.assertEqual(cart_item.quantity, 1)

	def test_add_to_cart_increments_existing_row(self):
		# The same product should update quantity instead of creating duplicate rows.
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		self.client.get(reverse('add_to_cart', args=[self.product.id]))

		self.assertEqual(CartItem.objects.count(), 1)
		self.assertEqual(CartItem.objects.get(buyer=self.buyer, product=self.product).quantity, 2)

	def test_update_cart_changes_quantity_in_database(self):
		# Updating the form should write the new quantity to the database row.
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		response = self.client.post(reverse('update_cart', args=[self.product.id]), {'quantity': 3})

		self.assertRedirects(response, reverse('cart_view'))
		self.assertEqual(CartItem.objects.get(buyer=self.buyer, product=self.product).quantity, 3)

	def test_update_cart_zero_removes_row(self):
		# Quantity zero removes the row completely, matching the previous cart behavior.
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		self.client.post(reverse('update_cart', args=[self.product.id]), {'quantity': 0})

		self.assertFalse(CartItem.objects.filter(buyer=self.buyer, product=self.product).exists())

	def test_remove_link_on_cart_page_deletes_cart_item(self):
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		cart_response = self.client.get(reverse('cart_view'))

		self.assertEqual(cart_response.status_code, 200)
		self.assertContains(cart_response, reverse('remove_from_cart', args=[self.product.id]))
		self.assertContains(cart_response, 'Jacket')

		remove_response = self.client.get(reverse('remove_from_cart', args=[self.product.id]), follow=True)

		self.assertRedirects(remove_response, reverse('cart_view'))
		self.assertFalse(CartItem.objects.filter(buyer=self.buyer, product=self.product).exists())
		self.assertNotContains(remove_response, 'Jacket')

	def test_cart_page_displays_existing_cart_items(self):
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=2)

		response = self.client.get(reverse('cart_view'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Jacket')
		self.assertContains(response, '$25.00')
		self.assertContains(response, '$50.00')
		self.assertContains(response, 'value="2"', html=False)

	def test_checkout_reads_database_cart(self):
		# Checkout should calculate totals from persisted cart rows, not session data.
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=2)

		response = self.client.get(reverse('checkout'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Jacket')
		self.assertEqual(response.context['subtotal'], Decimal('50.00'))


class BuyerHomepageTests(TestCase):
	def setUp(self):
		self.buyer = User.objects.create_user(
			username='homebuyer',
			password='StrongPass123!',
			first_name='Home',
			last_name='Buyer',
			email='homebuyer@example.com',
			role='buyer',
		)
		self.client.force_login(self.buyer)
		self.seller = User.objects.create_user(
			username='homeseller',
			password='StrongPass123!',
			first_name='Home',
			last_name='Seller',
			email='homeseller@example.com',
			role='seller',
		)

	def test_buyer_homepage_shows_only_approved_products(self):
		visible_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Visible Approved Product',
			category='Jacket',
			price='25.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Should appear on the buyer homepage',
			deleted_at=None,
		)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Pending Product',
			category='Jacket',
			price='25.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='pending',
			description='Should not appear while pending approval',
			deleted_at=None,
		)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Rejected Product',
			category='Jacket',
			price='25.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='rejected',
			description='Should not appear after rejection',
			deleted_at=None,
		)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Inactive Approved Product',
			category='Jacket',
			price='25.00',
			stock=5,
			active=False,
			redirect_to=None,
			status='approved',
			description='Should not appear while inactive',
			deleted_at=None,
		)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Soft Deleted Approved Product',
			category='Jacket',
			price='25.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Should not appear once soft deleted',
			deleted_at=timezone.now() - timedelta(days=1),
		)

		response = self.client.get(reverse('buyer_home'))

		self.assertEqual(response.status_code, 200)
		self.assertQuerySetEqual(
			response.context['products'],
			[visible_product],
			transform=lambda product: product,
			ordered=False,
		)
		self.assertContains(response, 'Visible Approved Product')
		self.assertNotContains(response, 'Pending Product')
		self.assertNotContains(response, 'Rejected Product')
		self.assertNotContains(response, 'Inactive Approved Product')
		self.assertNotContains(response, 'Soft Deleted Approved Product')

	def test_buyer_homepage_paginates_to_ten_products_per_page(self):
		for index in range(12):
			Product.objects.create(
				seller_id=self.seller,
				product_name=f'Product {index}',
				category='Jacket',
				price='10.00',
				stock=5,
				active=True,
				redirect_to=None,
				status='approved',
				description='Paged product',
				deleted_at=None,
			)

		response = self.client.get(reverse('buyer_home'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.context['products']), 10)
		self.assertTrue(response.context['page_obj'].has_next())

	def test_buyer_homepage_second_page_shows_remaining_products(self):
		for index in range(12):
			Product.objects.create(
				seller_id=self.seller,
				product_name=f'Product {index}',
				category='Shoes',
				price='10.00',
				stock=5,
				active=True,
				redirect_to=None,
				status='approved',
				description='Paged product',
				deleted_at=None,
			)

		response = self.client.get(reverse('buyer_home'), {'page': 2})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.context['products']), 2)
		self.assertEqual(response.context['page_obj'].number, 2)

	def test_buyer_homepage_includes_category_search_data(self):
		Product.objects.create(
			seller_id=self.seller,
			product_name='Category Coat',
			category='Jacket',
			price='35.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Category searchable product',
			deleted_at=None,
		)

		response = self.client.get(reverse('buyer_home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'All categories')
		self.assertContains(response, 'Category: Jacket')

	def test_buyer_homepage_search_filters_across_catalogue(self):
		for index in range(11):
			Product.objects.create(
				seller_id=self.seller,
				product_name=f'Alpha Product {index}',
				category='Jacket',
				price='10.00',
				stock=5,
				active=True,
				redirect_to=None,
				status='approved',
				description='Searchable alpha product',
				deleted_at=None,
			)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Beta Product',
			category='Shoes',
			price='10.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Different search term',
			deleted_at=None,
		)

		response = self.client.get(reverse('buyer_home'), {'q': 'Alpha'})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['page_obj'].paginator.count, 11)
		self.assertEqual(len(response.context['products']), 10)
		self.assertContains(response, 'Showing 11 results')
		self.assertContains(response, 'for "Alpha"')

	def test_buyer_homepage_category_filter_works_server_side(self):
		Product.objects.create(
			seller_id=self.seller,
			product_name='Jacket Product',
			category='Jacket',
			price='10.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Jacket item',
			deleted_at=None,
		)
		Product.objects.create(
			seller_id=self.seller,
			product_name='Shoe Product',
			category='Shoes',
			price='10.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Shoe item',
			deleted_at=None,
		)

		response = self.client.get(reverse('buyer_home'), {'category': 'Shoes'})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['page_obj'].paginator.count, 1)
		self.assertContains(response, 'Shoe Product')
		self.assertNotContains(response, 'Jacket Product')

	@override_settings(MEDIA_ROOT=tempfile.gettempdir())
	def test_buyer_homepage_displays_product_image_when_available(self):
		upload = SimpleUploadedFile('homepage.png', TEST_PNG_BYTES, content_type='image/png')
		product = Product.objects.create(
			seller_id=self.seller,
			image=upload,
			product_name='Image Product',
			category='Jacket',
			price='10.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Image product',
			deleted_at=None,
		)

		response = self.client.get(reverse('buyer_home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'src="{product.image.url}"')

	def test_add_to_compare_adds_product_to_session(self):
		# Adding a product to compare should store it in the session.
		first_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Jacket',
			category='Jacket',
			price='45.00',
			stock=3,
			active=True,
			redirect_to=None,
			status='approved',
			description='Warm compare item',
			deleted_at=None,
		)

		response = self.client.get(reverse('add_to_compare', args=[first_product.id]))

		# Check that session contains the product ID
		self.assertIn('compare_products', self.client.session)
		self.assertIn(first_product.id, self.client.session['compare_products'])
		self.assertRedirects(response, reverse('buyer_home'))

	def test_add_to_compare_from_different_pages(self):
		# Products can be added to compare from different paginated pages.
		products = []
		for i in range(15):
			product = Product.objects.create(
				seller_id=self.seller,
				product_name=f'Product {i+1}',
				category='Jacket',
				price=f'{40 + i}.00',
				stock=5,
				active=True,
				redirect_to=None,
				status='approved',
				description=f'Product {i+1} description',
				deleted_at=None,
			)
			products.append(product)

		# Add product from first page
		self.client.get(reverse('add_to_compare', args=[products[0].id]))
		# Add product from second page
		self.client.get(reverse('add_to_compare', args=[products[12].id]))

		# Both should be in the session
		self.assertIn(products[0].id, self.client.session['compare_products'])
		self.assertIn(products[12].id, self.client.session['compare_products'])
		self.assertEqual(len(self.client.session['compare_products']), 2)

	def test_remove_from_compare_removes_product_from_session(self):
		# Removing a product from compare should update the session.
		first_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Jacket',
			category='Jacket',
			price='45.00',
			stock=3,
			active=True,
			redirect_to=None,
			status='approved',
			description='Warm compare item',
			deleted_at=None,
		)

		# Add product first
		self.client.get(reverse('add_to_compare', args=[first_product.id]))
		self.assertIn(first_product.id, self.client.session['compare_products'])

		# Remove product
		response = self.client.get(reverse('remove_from_compare', args=[first_product.id]))

		self.assertNotIn(first_product.id, self.client.session['compare_products'])
		self.assertEqual(len(self.client.session['compare_products']), 0)

	def test_compare_products_displays_all_added_products(self):
		# The compare page should display all products in the session.
		first_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Jacket',
			category='Jacket',
			price='45.00',
			stock=3,
			active=True,
			redirect_to=None,
			status='approved',
			description='Warm compare item',
			deleted_at=None,
		)
		second_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Shoes',
			category='Shoes',
			price='55.00',
			stock=4,
			active=True,
			redirect_to=None,
			status='approved',
			description='Light compare item',
			deleted_at=None,
		)

		# Add both products to compare
		self.client.get(reverse('add_to_compare', args=[first_product.id]))
		self.client.get(reverse('add_to_compare', args=[second_product.id]))

		response = self.client.get(reverse('compare_products'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Compare Products')
		self.assertContains(response, 'Compare Jacket')
		self.assertContains(response, 'Compare Shoes')
		self.assertIn(first_product.id, [p.id for p in response.context['products']])
		self.assertIn(second_product.id, [p.id for p in response.context['products']])

	def test_compare_products_redirects_when_empty(self):
		# Viewing the compare page with no items should redirect home with error.
		response = self.client.get(reverse('compare_products'), follow=True)

		self.assertRedirects(response, reverse('buyer_home'))
		self.assertContains(response, 'Add products to compare before viewing the comparison.')

	def test_clear_compare_clears_session(self):
		# Clearing comparison should remove all products from the session.
		first_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Jacket',
			category='Jacket',
			price='45.00',
			stock=3,
			active=True,
			redirect_to=None,
			status='approved',
			description='Warm compare item',
			deleted_at=None,
		)
		second_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Shoes',
			category='Shoes',
			price='55.00',
			stock=4,
			active=True,
			redirect_to=None,
			status='approved',
			description='Light compare item',
			deleted_at=None,
		)

		# Add products
		self.client.get(reverse('add_to_compare', args=[first_product.id]))
		self.client.get(reverse('add_to_compare', args=[second_product.id]))
		self.assertEqual(len(self.client.session['compare_products']), 2)

		# Clear comparison
		response = self.client.get(reverse('clear_compare'))

		self.assertRedirects(response, reverse('buyer_home'))
		self.assertEqual(len(self.client.session.get('compare_products', [])), 0)

	def test_buyer_homepage_shows_compare_count(self):
		# The homepage should display the count of products in the comparison.
		first_product = Product.objects.create(
			seller_id=self.seller,
			product_name='Compare Jacket',
			category='Jacket',
			price='45.00',
			stock=3,
			active=True,
			redirect_to=None,
			status='approved',
			description='Warm compare item',
			deleted_at=None,
		)

		response = self.client.get(reverse('buyer_home'))
		self.assertEqual(response.context['compare_count'], 0)
		self.assertNotContains(response, 'Products in comparison')

		# Add product
		self.client.get(reverse('add_to_compare', args=[first_product.id]))
		response = self.client.get(reverse('buyer_home'))

		self.assertEqual(response.context['compare_count'], 1)
		self.assertContains(response, 'Products in comparison')
		self.assertContains(response, '1/10')


class CheckoutFlowTests(TestCase):
	def setUp(self):
		self.buyer = User.objects.create_user(
			username='checkoutbuyer',
			password='StrongPass123!',
			first_name='Checkout',
			last_name='Buyer',
			email='checkoutbuyer@example.com',
			role='buyer',
		)
		self.seller = User.objects.create_user(
			username='checkoutseller',
			password='StrongPass123!',
			first_name='Checkout',
			last_name='Seller',
			email='checkoutseller@example.com',
			role='seller',
			is_active=True,
		)
		self.product = Product.objects.create(
			seller_id=self.seller,
			product_name='Running Jacket',
			category='Jacket',
			price='40.00',
			stock=5,
			active=True,
			redirect_to=None,
			status='approved',
			description='Windproof running jacket',
			deleted_at=None,
		)
		self.checkout_payload = {
			'address-label': 'Home',
			'address-recipient_name': 'Checkout Buyer',
			'address-address_line_1': '123 Test Street',
			'address-address_line_2': 'Unit 4',
			'address-city': 'Dublin',
			'address-state': 'Leinster',
			'address-postal_code': 'D01TEST',
			'address-country': 'Ireland',
			'address-phone_number': '0123456789',
			'payment-label': 'Main Card',
			'payment-cardholder_name': 'Checkout Buyer',
			'payment-card_brand': 'visa',
			'payment-card_number': '4111111111111111',
			'payment-expiry_month': 12,
			'payment-expiry_year': 2030,
		}
		self.client.force_login(self.buyer)

	def test_checkout_page_displays_shipping_and_payment_forms(self):
		SellerShippingAddress.objects.create(
			seller=self.seller,
			label='Warehouse',
			recipient_name='Checkout Seller',
			address_line_1='456 Seller Road',
			city='Cork',
			state='Munster',
			postal_code='T12SELL',
			country='Ireland',
			is_default=True,
		)
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		response = self.client.get(reverse('checkout'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Buyer Shipping Address')
		self.assertContains(response, 'Payment Method')
		self.assertContains(response, 'name="address-label"', html=False)
		self.assertContains(response, 'name="address-recipient_name"', html=False)
		self.assertContains(response, 'name="address-address_line_1"', html=False)
		self.assertContains(response, 'name="payment-label"', html=False)
		self.assertContains(response, 'name="payment-cardholder_name"', html=False)
		self.assertContains(response, 'name="payment-card_number"', html=False)
		self.assertIn('buyer_address_form', response.context)
		self.assertIn('payment_method_form', response.context)

	def test_checkout_creates_order_and_clears_cart(self):
		SellerShippingAddress.objects.create(
			seller=self.seller,
			label='Warehouse',
			recipient_name='Checkout Seller',
			address_line_1='456 Seller Road',
			city='Cork',
			state='Munster',
			postal_code='T12SELL',
			country='Ireland',
			is_default=True,
		)
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=2)

		response = self.client.post(reverse('checkout'), self.checkout_payload, follow=True)

		self.assertRedirects(response, reverse('cart_view'))
		self.assertContains(response, 'Order placed successfully')
		self.assertEqual(Order.objects.count(), 1)
		self.assertEqual(OrderItem.objects.count(), 1)
		order = Order.objects.get()
		order_item = OrderItem.objects.get(order=order)
		self.assertEqual(order.buyer, self.buyer)
		self.assertEqual(order.subtotal, Decimal('80.00'))
		self.assertEqual(order.shipping_cost, Decimal('6.99'))
		self.assertEqual(order.tax_amount, Decimal('5.60'))
		self.assertEqual(order.grand_total, Decimal('92.59'))
		self.assertEqual(order.buyer_shipping_address.recipient_name, 'Checkout Buyer')
		self.assertEqual(order_item.product_name, 'Running Jacket')
		self.assertEqual(order_item.seller, self.seller)
		self.assertEqual(order_item.seller_shipping_address.label, 'Warehouse')
		self.assertEqual(order_item.quantity, 2)
		self.assertEqual(order_item.line_total, Decimal('80.00'))
		self.assertFalse(CartItem.objects.filter(buyer=self.buyer).exists())
		self.product.refresh_from_db()
		self.assertEqual(self.product.stock, 3)
		self.assertEqual(BuyerShippingAddress.objects.count(), 1)
		payment_method = PaymentMethod.objects.get()
		self.assertEqual(payment_method.full_card_number, '4111111111111111')
		self.assertEqual(payment_method.last_four, '1111')

	def test_checkout_can_use_saved_address_and_payment_method(self):
		SellerShippingAddress.objects.create(
			seller=self.seller,
			label='Warehouse',
			recipient_name='Checkout Seller',
			address_line_1='456 Seller Road',
			city='Cork',
			state='Munster',
			postal_code='T12SELL',
			country='Ireland',
			is_default=True,
		)
		buyer_address = BuyerShippingAddress.objects.create(
			buyer=self.buyer,
			label='Saved Home',
			recipient_name='Checkout Buyer',
			address_line_1='123 Test Street',
			city='Dublin',
			state='Leinster',
			postal_code='D01TEST',
			country='Ireland',
			is_default=True,
		)
		payment_method = PaymentMethod.objects.create(
			buyer=self.buyer,
			label='Saved Card',
			cardholder_name='Checkout Buyer',
			card_brand='visa',
			full_card_number='4242424242424242',
			last_four='4242',
			expiry_month=12,
			expiry_year=2031,
			is_default=True,
		)
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		response = self.client.post(
			reverse('checkout'),
			{
				'buyer_address_id': buyer_address.id,
				'payment_method_id': payment_method.id,
			},
			follow=True,
		)

		self.assertRedirects(response, reverse('cart_view'))
		self.assertEqual(Order.objects.count(), 1)
		order = Order.objects.get()
		self.assertEqual(order.buyer_shipping_address, buyer_address)
		self.assertEqual(order.payment_method, payment_method)
		self.assertEqual(BuyerShippingAddress.objects.count(), 1)
		self.assertEqual(PaymentMethod.objects.count(), 1)
		self.assertEqual(order.payment_method.full_card_number, '4242424242424242')
		self.assertEqual(OrderItem.objects.get(order=order).seller_shipping_address.recipient_name, 'Checkout Seller')

	def test_checkout_blocks_when_seller_address_missing(self):
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		response = self.client.post(reverse('checkout'), self.checkout_payload)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'One or more sellers are missing saved shipping addresses')
		self.assertEqual(Order.objects.count(), 0)
		self.assertTrue(CartItem.objects.filter(buyer=self.buyer, product=self.product).exists())

	def test_checkout_creates_single_order_for_multiple_sellers(self):
		second_seller = User.objects.create_user(
			username='secondseller',
			password='StrongPass123!',
			first_name='Second',
			last_name='Seller',
			email='secondseller@example.com',
			role='seller',
			is_active=True,
		)
		second_product = Product.objects.create(
			seller_id=second_seller,
			product_name='Trail Shoes',
			category='Shoes',
			price='60.00',
			stock=4,
			active=True,
			redirect_to=None,
			status='approved',
			description='Trail running shoes',
			deleted_at=None,
		)
		first_address = SellerShippingAddress.objects.create(
			seller=self.seller,
			label='Warehouse',
			recipient_name='Checkout Seller',
			address_line_1='456 Seller Road',
			city='Cork',
			state='Munster',
			postal_code='T12SELL',
			country='Ireland',
			is_default=True,
		)
		second_address = SellerShippingAddress.objects.create(
			seller=second_seller,
			label='Second Warehouse',
			recipient_name='Second Seller',
			address_line_1='789 Market Lane',
			city='Galway',
			state='Connacht',
			postal_code='G01SELL',
			country='Ireland',
			is_default=True,
		)
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)
		CartItem.objects.create(buyer=self.buyer, product=second_product, quantity=1)

		response = self.client.post(reverse('checkout'), self.checkout_payload, follow=True)

		self.assertRedirects(response, reverse('cart_view'))
		self.assertEqual(Order.objects.count(), 1)
		order = Order.objects.get()
		self.assertEqual(order.subtotal, Decimal('100.00'))
		self.assertEqual(order.shipping_cost, Decimal('13.98'))
		self.assertEqual(order.tax_amount, Decimal('7.00'))
		self.assertEqual(order.grand_total, Decimal('120.98'))
		self.assertEqual(OrderItem.objects.filter(order=order).count(), 2)
		self.assertSetEqual(
			set(OrderItem.objects.filter(order=order).values_list('seller__username', flat=True)),
			{'checkoutseller', 'secondseller'},
		)
		self.assertSetEqual(
			set(OrderItem.objects.filter(order=order).values_list('seller_shipping_address_id', flat=True)),
			{first_address.id, second_address.id},
		)

	def test_buyer_order_history_lists_placed_order(self):
		SellerShippingAddress.objects.create(
			seller=self.seller,
			label='Warehouse',
			recipient_name='Checkout Seller',
			address_line_1='456 Seller Road',
			city='Cork',
			state='Munster',
			postal_code='T12SELL',
			country='Ireland',
			is_default=True,
		)
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=1)

		self.client.post(reverse('checkout'), self.checkout_payload, follow=True)
		response = self.client.get(reverse('buyer_order_history'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Buyer Order History')
		self.assertContains(response, 'Running Jacket')
		self.assertContains(response, 'checkoutseller')
