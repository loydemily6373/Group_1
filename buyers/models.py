from django.db import models


class BuyerShippingAddress(models.Model):
	# Buyers can reuse saved delivery addresses instead of entering them on every checkout.
	buyer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='buyer_shipping_addresses')
	label = models.CharField(max_length=100)
	recipient_name = models.CharField(max_length=150)
	address_line_1 = models.CharField(max_length=200)
	address_line_2 = models.CharField(max_length=200, blank=True)
	city = models.CharField(max_length=100)
	state = models.CharField(max_length=100)
	postal_code = models.CharField(max_length=20)
	country = models.CharField(max_length=100)
	phone_number = models.CharField(max_length=30, blank=True)
	is_default = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f"{self.buyer.username} - {self.label}"


class SellerShippingAddress(models.Model):
	# Orders use the seller's saved shipping origin so it can be recalled on future orders.
	seller = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='seller_shipping_addresses')
	label = models.CharField(max_length=100)
	recipient_name = models.CharField(max_length=150)
	address_line_1 = models.CharField(max_length=200)
	address_line_2 = models.CharField(max_length=200, blank=True)
	city = models.CharField(max_length=100)
	state = models.CharField(max_length=100)
	postal_code = models.CharField(max_length=20)
	country = models.CharField(max_length=100)
	phone_number = models.CharField(max_length=30, blank=True)
	is_default = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f"{self.seller.username} - {self.label}"


class PaymentMethod(models.Model):
	CARD_BRAND_CHOICES = [
		('visa', 'Visa'),
		('mastercard', 'Mastercard'),
		('amex', 'Amex'),
		('discover', 'Discover'),
		('other', 'Other'),
	]

	# Store reusable payment details for this project, including the full test card number and the last four digits.
	buyer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='payment_methods')
	label = models.CharField(max_length=100)
	cardholder_name = models.CharField(max_length=150)
	card_brand = models.CharField(max_length=20, choices=CARD_BRAND_CHOICES)
	full_card_number = models.CharField(max_length=19, blank=True, default='')
	last_four = models.CharField(max_length=4)
	expiry_month = models.PositiveSmallIntegerField()
	expiry_year = models.PositiveSmallIntegerField()
	provider_reference = models.CharField(max_length=100, blank=True)
	is_default = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f"{self.buyer.username} - {self.label} ending in {self.last_four}"


class Order(models.Model):
	STATUS_CHOICES = [
		('placed', 'Placed'),
		('processing', 'Processing'),
		('shipped', 'Shipped'),
		('completed', 'Completed'),
	]

	# The order represents the buyer's full checkout, even when items come from multiple sellers.
	buyer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='buyer_orders')
	buyer_shipping_address = models.ForeignKey(BuyerShippingAddress, on_delete=models.PROTECT, related_name='orders')
	payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='orders')
	order_number = models.CharField(max_length=30, unique=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='placed')
	subtotal = models.DecimalField(max_digits=10, decimal_places=2)
	shipping_cost = models.DecimalField(max_digits=10, decimal_places=2)
	tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
	grand_total = models.DecimalField(max_digits=10, decimal_places=2)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.order_number


class OrderItem(models.Model):
	ITEM_STATUS_CHOICES = [
		('placed', 'Placed'),
		('processing', 'Processing'),
		('shipped', 'Shipped'),
		('completed', 'Completed'),
		('returned', 'Returned'),
	]

	# Snapshot purchase details per seller so one order can contain items from multiple sellers.
	order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
	product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='order_items')
	seller = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='order_items')
	seller_shipping_address = models.ForeignKey(SellerShippingAddress, on_delete=models.PROTECT, related_name='order_items')
	product_name = models.CharField(max_length=200)
	item_status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default='placed')
	unit_price = models.DecimalField(max_digits=10, decimal_places=2)
	quantity = models.PositiveIntegerField()
	line_total = models.DecimalField(max_digits=10, decimal_places=2)

	@property
	def return_request_record(self):
		return getattr(self, 'return_request', None)

	@property
	def can_request_return(self):
		return self.item_status == 'completed' and self.return_request_record is None

	def __str__(self):
		return f"{self.order.order_number} - {self.product_name}"


class CartItem(models.Model):
	# Store each buyer's cart rows in the database so checkout can query them directly.
	buyer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='cart_items')
	product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='cart_items')
	quantity = models.PositiveIntegerField(default=1)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		# A buyer should only have one cart row per product; quantity tracks repeats.
		constraints = [
			models.UniqueConstraint(fields=['buyer', 'product'], name='unique_buyer_product_cart_item'),
		]

	def __str__(self):
		return f"{self.buyer.username} - {self.product.product_name} ({self.quantity})"

