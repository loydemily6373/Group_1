from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin.models import ProductApprovalRequest, SellerApprovalRequest, UserActivity
from buyers.models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, SellerShippingAddress
from sellers.models import Product


class AdminIntegrationTests(TestCase):
    def setUp(self):
        # Create a real admin user so the custom admin pages can be exercised with the role guard.
        self.admin_user = User.objects.create_user(
            username='adminuser',
            password='StrongPass123!',
            first_name='Admin',
            last_name='User',
            email='admin@example.com',
            role='admin',
        )
        self.buyer_user = User.objects.create_user(
            username='buyeruser',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='User',
            email='buyer@example.com',
            role='buyer',
        )
        self.pending_seller = User.objects.create_user(
            username='sellercandidate',
            password='StrongPass123!',
            first_name='Seller',
            last_name='Candidate',
            email='sellercandidate@example.com',
            role='seller',
            is_active=False,
        )
        self.seller_request = SellerApprovalRequest.objects.create(
            user=self.pending_seller,
            first_name=self.pending_seller.first_name,
            last_name=self.pending_seller.last_name,
            email=self.pending_seller.email,
            approved=None,
        )
        self.product = Product.objects.create(
            seller_id=self.admin_user,
            product_name='Admin Review Item',
            category='Shirt',
            price='19.99',
            stock=3,
            active=False,
            redirect_to=None,
            status='pending',
            description='Pending product for admin review',
            deleted_at=None,
        )
        self.product_request = ProductApprovalRequest.objects.create(
            product_id=self.product,
            name=self.product.product_name,
            seller_ID=self.admin_user,
            seller_First_Name=self.admin_user.first_name,
            approved=None,
            status='pending',
        )

    def test_admin_can_open_product_requests(self):
        # The custom admin page should use the existing admin role protection.
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('product_requests'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Review Item')
        self.assertContains(response, str(self.product_request.id))

    def test_non_admin_cannot_open_product_requests(self):
        # Buyers should be blocked from the admin app routes.
        self.client.force_login(self.buyer_user)

        response = self.client.get(reverse('product_requests'))

        self.assertRedirects(response, reverse('buyer_home'))

    def test_approve_product_updates_real_product_record(self):
        # Approving from the admin app should update the shared Product model used elsewhere.
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('approve_product', args=[self.product_request.id]))

        self.assertRedirects(response, reverse('product_requests'))
        self.product.refresh_from_db()
        self.product_request.refresh_from_db()
        self.assertTrue(self.product.active)
        self.assertEqual(self.product.status, 'approved')
        self.assertTrue(self.product_request.approved)
        self.assertEqual(self.product_request.status, 'approved')

    def test_approving_edit_request_soft_deletes_original_and_sets_redirect(self):
        # Approving an edit should replace the original live product with the pending replacement.
        original_product = Product.objects.create(
            seller_id=self.admin_user,
            product_name='Original Live Product',
            category='Jacket',
            price='29.99',
            stock=4,
            active=True,
            redirect_to=None,
            status='approved',
            description='Original approved listing',
            deleted_at=None,
        )
        replacement_product = Product.objects.create(
            seller_id=self.admin_user,
            product_name='Replacement Product',
            category='Jacket',
            price='34.99',
            stock=6,
            active=False,
            redirect_to=None,
            status='pending',
            description='Pending replacement listing',
            deleted_at=None,
        )
        edit_request = ProductApprovalRequest.objects.create(
            product_id=replacement_product,
            original_product_id=original_product,
            name=replacement_product.product_name,
            seller_ID=self.admin_user,
            seller_First_Name=self.admin_user.first_name,
            approved=None,
            request_type='edit',
            status='pending',
        )

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('approve_product', args=[edit_request.id]))

        self.assertRedirects(response, reverse('product_requests'))
        original_product.refresh_from_db()
        replacement_product.refresh_from_db()
        edit_request.refresh_from_db()
        self.assertIsNotNone(original_product.deleted_at)
        self.assertFalse(original_product.active)
        self.assertEqual(original_product.redirect_to, replacement_product)
        self.assertTrue(replacement_product.active)
        self.assertEqual(replacement_product.status, 'approved')
        self.assertTrue(edit_request.approved)

    def test_approve_seller_activates_user_account(self):
        # Seller approval should unlock login access by activating the linked user.
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('approve_seller', args=[self.seller_request.id]))

        self.assertRedirects(response, reverse('seller_requests'))
        self.pending_seller.refresh_from_db()
        self.seller_request.refresh_from_db()
        self.assertTrue(self.pending_seller.is_active)
        self.assertTrue(self.seller_request.approved)

    def test_reject_seller_keeps_user_inactive(self):
        # Rejected seller accounts should stay inactive and unable to log in.
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('reject_seller', args=[self.seller_request.id]))

        self.assertRedirects(response, reverse('seller_requests'))
        self.pending_seller.refresh_from_db()
        self.seller_request.refresh_from_db()
        self.assertFalse(self.pending_seller.is_active)
        self.assertFalse(self.seller_request.approved)

    def test_admin_home_displays_live_user_activity_table(self):
        UserActivity.objects.create(
            user=self.buyer_user,
            username=self.buyer_user.username,
            role=self.buyer_user.role,
            login_count=3,
            purchase_count=2,
            completed_sales_count=0,
        )

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('admin_home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Live user activity for admin review')
        self.assertContains(response, 'buyeruser')
        self.assertContains(response, '3')
        self.assertContains(response, '2')


class UserActivityTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='activityadmin',
            password='StrongPass123!',
            first_name='Activity',
            last_name='Admin',
            email='activityadmin@example.com',
            role='admin',
        )
        self.buyer = User.objects.create_user(
            username='activitybuyer',
            password='StrongPass123!',
            first_name='Activity',
            last_name='Buyer',
            email='activitybuyer@example.com',
            role='buyer',
        )
        self.seller = User.objects.create_user(
            username='activityseller',
            password='StrongPass123!',
            first_name='Activity',
            last_name='Seller',
            email='activityseller@example.com',
            role='seller',
        )

    def test_login_creates_or_updates_user_activity(self):
        with patch('accounts.views.CustomTokenObtainPairSerializer') as serializer_class:
            serializer = serializer_class.return_value
            serializer.is_valid.return_value = True
            serializer.user = self.buyer
            serializer.validated_data = {'access': 'token', 'refresh': 'refresh'}

            response = self.client.post(reverse('account_token_api'), {
                'username': 'activitybuyer',
                'password': 'StrongPass123!',
            })

        self.assertEqual(response.status_code, 200)
        activity = UserActivity.objects.get(user=self.buyer)
        self.assertEqual(activity.username, 'activitybuyer')
        self.assertEqual(activity.role, 'buyer')
        self.assertEqual(activity.login_count, 1)

    def test_checkout_records_buyer_purchase_count(self):
        SellerShippingAddress.objects.create(
            seller=self.seller,
            label='Warehouse',
            recipient_name='Activity Seller',
            address_line_1='1 Seller Road',
            city='Dublin',
            state='Leinster',
            postal_code='D02SEL',
            country='Ireland',
            is_default=True,
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Checkout Activity Product',
            category='Jacket',
            price='25.00',
            stock=10,
            active=True,
            redirect_to=None,
            status='approved',
            description='Tracks purchases',
            deleted_at=None,
        )
        CartItem.objects.create(buyer=self.buyer, product=product, quantity=2)
        self.client.force_login(self.buyer)

        response = self.client.post(reverse('checkout'), {
            'address-label': 'Home',
            'address-recipient_name': 'Buyer Activity',
            'address-address_line_1': '1 Buyer Lane',
            'address-address_line_2': '',
            'address-city': 'Dublin',
            'address-state': 'Leinster',
            'address-postal_code': 'D01BUY',
            'address-country': 'Ireland',
            'address-phone_number': '0123456789',
            'payment-label': 'Card',
            'payment-cardholder_name': 'Buyer Activity',
            'payment-card_brand': 'visa',
            'payment-card_number': '4111111111111111',
            'payment-expiry_month': 12,
            'payment-expiry_year': 2030,
        })

        self.assertRedirects(response, reverse('cart_view'))
        activity = UserActivity.objects.get(user=self.buyer)
        self.assertEqual(activity.purchase_count, 2)

    def test_completed_order_item_records_seller_sales_count(self):
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=self.buyer,
            label='Home',
            recipient_name='Buyer Activity',
            address_line_1='1 Buyer Lane',
            city='Dublin',
            state='Leinster',
            postal_code='D01BUY',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=self.buyer,
            label='Card',
            cardholder_name='Buyer Activity',
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
            recipient_name='Seller Activity',
            address_line_1='1 Seller Road',
            city='Dublin',
            state='Leinster',
            postal_code='D02SEL',
            country='Ireland',
            is_default=True,
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Seller Activity Product',
            category='Hoodie',
            price='40.00',
            stock=5,
            active=True,
            redirect_to=None,
            status='approved',
            description='Tracks completed sales',
            deleted_at=None,
        )
        order = Order.objects.create(
            buyer=self.buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-ACTIVITY',
            subtotal='80.00',
            shipping_cost='6.99',
            tax_amount='5.60',
            grand_total='92.59',
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Seller Activity Product',
            unit_price='40.00',
            quantity=2,
            line_total='80.00',
            item_status='processing',
        )
        self.client.force_login(self.seller)

        response = self.client.post(reverse('update_order_item_status', args=[order_item.id]), {
            'item_status': 'completed',
        })

        self.assertRedirects(response, reverse('seller_order_history'))
        activity = UserActivity.objects.get(user=self.seller)
        self.assertEqual(activity.completed_sales_count, 2)