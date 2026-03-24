from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from accounts.models import User
from products.models import Product

from .models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, SellerShippingAddress


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

	def test_checkout_reads_database_cart(self):
		# Checkout should calculate totals from persisted cart rows, not session data.
		CartItem.objects.create(buyer=self.buyer, product=self.product, quantity=2)

		response = self.client.get(reverse('checkout'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Jacket')
		self.assertEqual(response.context['subtotal'], Decimal('50.00'))


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
