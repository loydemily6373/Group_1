from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from admin.models import ProductApprovalRequest
from buyers.models import BuyerShippingAddress, Order, OrderItem, PaymentMethod, SellerShippingAddress

from .models import Product


class ProductWorkflowTests(TestCase):
    def setUp(self):
        # Create a seller account so product creation can be exercised through the real protected view.
        self.seller = User.objects.create_user(
            username='seller1',
            password='StrongPass123!',
            first_name='Seller',
            last_name='One',
            email='seller1@example.com',
            role='seller',
        )
        self.client.force_login(self.seller)

    def test_product_creation_creates_pending_product_and_approval_request(self):
        # New products should start inactive and automatically create an admin approval request.
        response = self.client.post(reverse('product_creation'), {
            'product_name': 'Seller Hoodie',
            'category': 'Hoodie',
            'price': '42.00',
            'stock': 7,
            'description': 'Soft fleece hoodie',
        })

        self.assertRedirects(response, reverse('product_list'))
        product = Product.objects.get(product_name='Seller Hoodie')
        approval_request = ProductApprovalRequest.objects.get(product_id=product)

        self.assertEqual(product.seller_id, self.seller)
        self.assertFalse(product.active)
        self.assertEqual(product.status, 'pending')
        self.assertIsNone(product.deleted_at)
        self.assertEqual(approval_request.status, 'pending')
        self.assertIsNone(approval_request.approved)

    def test_soft_delete_marks_product_inactive(self):
        # Deleting from the seller UI should soft-delete instead of removing the row entirely.
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Archived Jacket',
            category='Jacket',
            price='60.00',
            stock=2,
            description='Will be soft deleted',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )

        response = self.client.post(reverse('product_delete', args=[product.id]))

        self.assertRedirects(response, reverse('product_list'))
        product.refresh_from_db()
        self.assertFalse(product.active)
        self.assertIsNotNone(product.deleted_at)

    def test_display_product_uses_redirect_target_when_soft_deleted(self):
        # Related tables can show the replacement listing when a product has been soft deleted.
        replacement = Product.objects.create(
            seller_id=self.seller,
            product_name='Replacement Jacket',
            category='Jacket',
            price='75.00',
            stock=4,
            description='Replacement listing',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        original = Product.objects.create(
            seller_id=self.seller,
            product_name='Original Jacket',
            category='Jacket',
            price='70.00',
            stock=1,
            description='Original listing',
            active=False,
            status='rejected',
            redirect_to=replacement,
            deleted_at=timezone.now(),
        )

        self.assertEqual(original.display_product, replacement)

    def test_editing_approved_product_creates_pending_replacement_request(self):
        # Editing a live approved product should create a new pending replacement instead of changing the live row.
        live_product = Product.objects.create(
            seller_id=self.seller,
            product_name='Live Hoodie',
            category='Hoodie',
            price='55.00',
            stock=5,
            description='Current live listing',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )

        response = self.client.post(reverse('product_edit', args=[live_product.id]), {
            'product_name': 'Live Hoodie V2',
            'category': 'Hoodie',
            'price': '60.00',
            'stock': 9,
            'description': 'Updated pending version',
        })

        self.assertRedirects(response, reverse('product_list'))
        live_product.refresh_from_db()
        replacement = Product.objects.exclude(id=live_product.id).get(product_name='Live Hoodie V2')
        approval_request = ProductApprovalRequest.objects.get(product_id=replacement)

        self.assertTrue(live_product.active)
        self.assertEqual(live_product.status, 'approved')
        self.assertFalse(replacement.active)
        self.assertEqual(replacement.status, 'pending')
        self.assertEqual(approval_request.request_type, 'edit')
        self.assertEqual(approval_request.original_product_id, live_product)

    def test_seller_shipping_address_page_can_create_default_address(self):
        response = self.client.post(reverse('seller_shipping_address'), {
            'label': 'Primary Warehouse',
            'recipient_name': 'Seller One',
            'address_line_1': '123 Warehouse Road',
            'address_line_2': '',
            'city': 'Dublin',
            'state': 'Leinster',
            'postal_code': 'D01ADDR',
            'country': 'Ireland',
            'phone_number': '0123456789',
        })

        self.assertRedirects(response, reverse('seller_home'))
        self.assertTrue(SellerShippingAddress.objects.filter(seller=self.seller, is_default=True).exists())

    def test_product_creation_page_warns_when_default_shipping_address_missing(self):
        response = self.client.get(reverse('product_creation'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'buyers will not be able to check out items from your shop until you add a default shipping address')

    def test_seller_order_history_shows_only_seller_items(self):
        buyer = User.objects.create_user(
            username='buyer2',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Two',
            email='buyer2@example.com',
            role='buyer',
        )
        other_seller = User.objects.create_user(
            username='seller2',
            password='StrongPass123!',
            first_name='Seller',
            last_name='Two',
            email='seller2@example.com',
            role='seller',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Two',
            address_line_1='1 Buyer Lane',
            city='Cork',
            state='Munster',
            postal_code='T12BUY',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Two',
            card_brand='visa',
            full_card_number='4242424242424242',
            last_four='4242',
            expiry_month=12,
            expiry_year=2030,
            is_default=True,
        )
        seller_address = SellerShippingAddress.objects.create(
            seller=self.seller,
            label='Warehouse',
            recipient_name='Seller One',
            address_line_1='123 Warehouse Road',
            city='Dublin',
            state='Leinster',
            postal_code='D01SELL',
            country='Ireland',
            is_default=True,
        )
        other_seller_address = SellerShippingAddress.objects.create(
            seller=other_seller,
            label='Other Warehouse',
            recipient_name='Seller Two',
            address_line_1='9 Other Road',
            city='Galway',
            state='Connacht',
            postal_code='G01SEL2',
            country='Ireland',
            is_default=True,
        )
        order = Order.objects.create(
            buyer=buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-SELLER-HISTORY',
            subtotal='100.00',
            shipping_cost='13.98',
            tax_amount='7.00',
            grand_total='120.98',
        )
        seller_product = Product.objects.create(
            seller_id=self.seller,
            product_name='Seller Hoodie',
            category='Hoodie',
            price='40.00',
            stock=5,
            description='Seller history hoodie',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        other_product = Product.objects.create(
            seller_id=other_seller,
            product_name='Other Shoes',
            category='Shoes',
            price='60.00',
            stock=5,
            description='Other seller item',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        OrderItem.objects.create(
            order=order,
            product=seller_product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Seller Hoodie',
            unit_price='40.00',
            quantity=1,
            line_total='40.00',
        )
        OrderItem.objects.create(
            order=order,
            product=other_product,
            seller=other_seller,
            seller_shipping_address=other_seller_address,
            product_name='Other Shoes',
            unit_price='60.00',
            quantity=1,
            line_total='60.00',
        )

        response = self.client.get(reverse('seller_order_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Seller Hoodie')
        self.assertNotContains(response, 'Other Shoes')
        self.assertContains(response, 'Buyer Two')

    def test_seller_can_update_individual_order_item_status(self):
        buyer = User.objects.create_user(
            username='buyer3',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Three',
            email='buyer3@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Three',
            address_line_1='3 Buyer Lane',
            city='Cork',
            state='Munster',
            postal_code='T12BUY',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Three',
            card_brand='visa',
            full_card_number='4111111111111111',
            last_four='1111',
            expiry_month=12,
            expiry_year=2030,
            is_default=True,
        )
        seller_address = SellerShippingAddress.objects.create(
            seller=self.seller,
            label='Warehouse',
            recipient_name='Seller One',
            address_line_1='123 Warehouse Road',
            city='Dublin',
            state='Leinster',
            postal_code='D01SELL',
            country='Ireland',
            is_default=True,
        )
        order = Order.objects.create(
            buyer=buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-ITEM-STATUS',
            subtotal='40.00',
            shipping_cost='6.99',
            tax_amount='2.80',
            grand_total='49.79',
        )
        seller_product = Product.objects.create(
            seller_id=self.seller,
            product_name='Status Hoodie',
            category='Hoodie',
            price='40.00',
            stock=5,
            description='Status test hoodie',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=seller_product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Status Hoodie',
            item_status='placed',
            unit_price='40.00',
            quantity=1,
            line_total='40.00',
        )

        response = self.client.post(reverse('update_order_item_status', args=[order_item.id]), {'item_status': 'completed'})

        self.assertRedirects(response, reverse('seller_order_history'))
        order_item.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order_item.item_status, 'completed')
        self.assertEqual(order.status, 'completed')

    def test_seller_order_history_shows_completed_earnings_total(self):
        buyer = User.objects.create_user(
            username='buyer4',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Four',
            email='buyer4@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Four',
            address_line_1='4 Buyer Lane',
            city='Cork',
            state='Munster',
            postal_code='T12BUY',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Four',
            card_brand='visa',
            full_card_number='4000000000000002',
            last_four='0002',
            expiry_month=12,
            expiry_year=2030,
            is_default=True,
        )
        seller_address = SellerShippingAddress.objects.create(
            seller=self.seller,
            label='Warehouse',
            recipient_name='Seller One',
            address_line_1='123 Warehouse Road',
            city='Dublin',
            state='Leinster',
            postal_code='D01SELL',
            country='Ireland',
            is_default=True,
        )
        completed_order = Order.objects.create(
            buyer=buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-COMPLETE-1',
            subtotal='75.00',
            shipping_cost='6.99',
            tax_amount='5.25',
            grand_total='87.24',
            status='completed',
        )
        in_progress_order = Order.objects.create(
            buyer=buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-PROGRESS-1',
            subtotal='20.00',
            shipping_cost='6.99',
            tax_amount='1.40',
            grand_total='28.39',
            status='processing',
        )
        completed_product = Product.objects.create(
            seller_id=self.seller,
            product_name='Completed Tee',
            category='T-Shirt',
            price='75.00',
            stock=5,
            description='Completed test item',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        processing_product = Product.objects.create(
            seller_id=self.seller,
            product_name='Processing Tee',
            category='T-Shirt',
            price='20.00',
            stock=5,
            description='Processing test item',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        OrderItem.objects.create(
            order=completed_order,
            product=completed_product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Completed Tee',
            item_status='completed',
            unit_price='75.00',
            quantity=1,
            line_total='75.00',
        )
        OrderItem.objects.create(
            order=in_progress_order,
            product=processing_product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Processing Tee',
            item_status='processing',
            unit_price='20.00',
            quantity=1,
            line_total='20.00',
        )

        response = self.client.get(reverse('seller_order_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Completed Sales Earnings')
        self.assertContains(response, '$75.00')
