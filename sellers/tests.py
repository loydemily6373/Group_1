import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from admin.models import ProductApprovalRequest
from buyers.models import BuyerShippingAddress, Order, OrderItem, PaymentMethod, SellerShippingAddress

from .models import Product, ReturnRequest
from .seeding import SEED_PRODUCTS, clear_products, seed_products


TEST_PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n'
    b'\x00\x00\x00\rIHDR'
    b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
    b'\x90wS\xde'
    b'\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00'
    b'\xc9\xfe\x92\xef'
    b'\x00\x00\x00\x00IEND\xaeB`\x82'
)


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

    def test_product_creation_accepts_image_upload(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile('hoodie.png', TEST_PNG_BYTES, content_type='image/png')

                response = self.client.post(reverse('product_creation'), {
                    'image': upload,
                    'product_name': 'Image Hoodie',
                    'category': 'Hoodie',
                    'price': '42.00',
                    'stock': 7,
                    'description': 'Soft fleece hoodie with image',
                })

                self.assertRedirects(response, reverse('product_list'))
                product = Product.objects.get(product_name='Image Hoodie')
                self.assertTrue(bool(product.image))
                self.assertIn('status_icons/', product.image.name)

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

    def test_buyer_can_create_return_request_for_completed_item(self):
        buyer = User.objects.create_user(
            username='buyer_return',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Return',
            email='buyerreturn@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Return',
            address_line_1='10 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D10RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Return',
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
            order_number='ORD-RETURN-1',
            subtotal='40.00',
            shipping_cost='6.99',
            tax_amount='2.80',
            grand_total='49.79',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Return Hoodie',
            category='Hoodie',
            price='40.00',
            stock=5,
            description='Returnable hoodie',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Return Hoodie',
            item_status='completed',
            unit_price='40.00',
            quantity=1,
            line_total='40.00',
        )

        self.client.force_login(buyer)
        response = self.client.post(reverse('request_return', args=[order_item.id]), {'reason': 'Item did not fit.'})

        self.assertRedirects(response, reverse('buyer_return_requests'))
        return_request = ReturnRequest.objects.get(order_item=order_item)
        self.assertEqual(return_request.status, 'pending')
        self.assertEqual(return_request.reason, 'Item did not fit.')

    def test_request_return_page_displays_form_for_completed_order_item(self):
        buyer = User.objects.create_user(
            username='buyer_return_form',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='ReturnForm',
            email='buyerreturnform@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Return Form',
            address_line_1='15 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D15RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Return Form',
            card_brand='visa',
            full_card_number='4666666666666666',
            last_four='6666',
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
            order_number='ORD-RETURN-FORM',
            subtotal='45.00',
            shipping_cost='6.99',
            tax_amount='3.15',
            grand_total='55.14',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Return Form Hoodie',
            category='Hoodie',
            price='45.00',
            stock=5,
            description='Return form hoodie',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Return Form Hoodie',
            item_status='completed',
            unit_price='45.00',
            quantity=1,
            line_total='45.00',
        )

        self.client.force_login(buyer)
        response = self.client.get(reverse('request_return', args=[order_item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Request Return')
        self.assertContains(response, 'Order #ORD-RETURN-FORM')
        self.assertContains(response, 'Return Form Hoodie')
        self.assertContains(response, 'name="reason"', html=False)
        self.assertContains(response, 'Submit Request')

    def test_buyer_and_seller_can_view_pending_return_requests(self):
        buyer = User.objects.create_user(
            username='buyer_pending_return',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Pending',
            email='buyerpending@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Pending',
            address_line_1='11 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D11RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Pending',
            card_brand='visa',
            full_card_number='4222222222222',
            last_four='2222',
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
            order_number='ORD-RETURN-2',
            subtotal='30.00',
            shipping_cost='6.99',
            tax_amount='2.10',
            grand_total='39.09',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Pending Return Tee',
            category='T-Shirt',
            price='30.00',
            stock=5,
            description='Pending return tee',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Pending Return Tee',
            item_status='completed',
            unit_price='30.00',
            quantity=1,
            line_total='30.00',
        )
        ReturnRequest.objects.create(order_item=order_item, reason='Wrong size')

        self.client.force_login(buyer)
        buyer_response = self.client.get(reverse('buyer_return_requests'))
        self.assertEqual(buyer_response.status_code, 200)
        self.assertContains(buyer_response, 'Pending Return Tee')

        self.client.force_login(self.seller)
        seller_response = self.client.get(reverse('seller_return_requests'))
        self.assertEqual(seller_response.status_code, 200)
        self.assertContains(seller_response, 'Pending Return Tee')
        self.assertContains(seller_response, 'Wrong size')

    def test_seller_can_approve_return_request(self):
        buyer = User.objects.create_user(
            username='buyer_return_approve',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Approve',
            email='buyerapprove@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Approve',
            address_line_1='12 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D12RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Approve',
            card_brand='visa',
            full_card_number='4333333333333333',
            last_four='3333',
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
            order_number='ORD-RETURN-3',
            subtotal='25.00',
            shipping_cost='6.99',
            tax_amount='1.75',
            grand_total='33.74',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Approve Return Cap',
            category='Accessories',
            price='25.00',
            stock=5,
            description='Return cap',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Approve Return Cap',
            item_status='completed',
            unit_price='25.00',
            quantity=1,
            line_total='25.00',
        )
        return_request = ReturnRequest.objects.create(order_item=order_item, reason='Changed mind')

        original_stock = product.stock

        response = self.client.post(reverse('approve_return', args=[return_request.id]))

        self.assertRedirects(response, reverse('seller_return_requests'))
        return_request.refresh_from_db()
        order_item.refresh_from_db()
        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(return_request.status, 'approved')
        self.assertEqual(order_item.item_status, 'returned')
        self.assertEqual(order.status, 'completed')
        self.assertEqual(product.stock, original_stock + 1)

    def test_seller_order_history_does_not_count_approved_return_in_completed_earnings(self):
        buyer = User.objects.create_user(
            username='buyer_return_earnings',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='ReturnEarnings',
            email='buyerreturnearnings@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Return Earnings',
            address_line_1='13 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D13RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Return Earnings',
            card_brand='visa',
            full_card_number='4444333322221111',
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
            order_number='ORD-RETURN-EARNINGS',
            subtotal='50.00',
            shipping_cost='6.99',
            tax_amount='3.50',
            grand_total='60.49',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Returned Sweatshirt',
            category='Sweater',
            price='50.00',
            stock=2,
            description='Returned sweatshirt',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Returned Sweatshirt',
            item_status='returned',
            unit_price='50.00',
            quantity=1,
            line_total='50.00',
        )
        ReturnRequest.objects.create(order_item=order_item, reason='Damaged item', status='approved')

        response = self.client.get(reverse('seller_order_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Completed Sales Earnings')
        self.assertContains(response, '$0.00')
        self.assertContains(response, 'Earned After Returns:')

    def test_approving_return_updates_history_badges_and_earnings(self):
        buyer = User.objects.create_user(
            username='buyer_badge_return',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='Badge',
            email='buyerbadge@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Buyer Badge',
            address_line_1='14 Buyer Street',
            city='Dublin',
            state='Leinster',
            postal_code='D14RET',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Buyer Badge',
            card_brand='visa',
            full_card_number='4555555555555555',
            last_four='5555',
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
            order_number='ORD-RETURN-BADGE',
            subtotal='35.00',
            shipping_cost='6.99',
            tax_amount='2.45',
            grand_total='44.44',
            status='completed',
        )
        product = Product.objects.create(
            seller_id=self.seller,
            product_name='Badge Return Hoodie',
            category='Hoodie',
            price='35.00',
            stock=1,
            description='Badge return hoodie',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=self.seller,
            seller_shipping_address=seller_address,
            product_name='Badge Return Hoodie',
            item_status='completed',
            unit_price='35.00',
            quantity=1,
            line_total='35.00',
        )
        return_request = ReturnRequest.objects.create(order_item=order_item, reason='Damaged seam')

        self.client.post(reverse('approve_return', args=[return_request.id]))
        seller_history = self.client.get(reverse('seller_order_history'))

        self.assertEqual(seller_history.status_code, 200)
        self.assertContains(seller_history, 'status-returned')
        self.assertContains(seller_history, 'status-approved')
        self.assertContains(seller_history, 'Total earned from completed order items after approved returns: $0.00')
        self.assertContains(seller_history, 'Earned After Returns:</strong> $0.00')

    # XSS test
    def test_xss_in_product_name(self):
        self.client.login(username='testuser', password='password')
        response = self.client.post(reverse('product_creation'), {
			'name': '<script>alert("hack")</script>',
			'price': 10
		})
        self.assertNotContains(response, '<script>')

    # verifying Django's built-in CSRF protection
    def test_csrf_protection_product_creation(self):
        client = Client(enforce_csrf_checks=True)

        client.login(username='selleruser', password='password')

        response = client.post(reverse('product_creation'), {
            'name': 'Test Product',
            'price': 10
        })

        self.assertEqual(response.status_code, 403)


class ProductSeedDataTests(TestCase):
    def test_seed_data_contains_thirty_products(self):
        self.assertEqual(len(SEED_PRODUCTS), 30)

    def test_seed_data_covers_every_category(self):
        seeded_categories = {product['category'] for product in SEED_PRODUCTS}
        model_categories = {value for value, _ in Product.CATEGORY_CHOICES}

        self.assertSetEqual(seeded_categories, model_categories)

    def test_seed_products_repairs_existing_seed_seller_password(self):
        User.objects.create(
            username='seed_seller',
            password='',
            first_name='',
            last_name='',
            email='',
            role='buyer',
        )

        seed_products()

        seller = User.objects.get(username='seed_seller')
        self.assertTrue(seller.check_password('SeedSeller123!'))
        self.assertEqual(seller.role, 'seller')
        self.assertEqual(seller.email, 'seed_seller@example.com')

    def test_clear_products_removes_related_orders_and_product_requests(self):
        seller = User.objects.create_user(
            username='seedclear-seller',
            password='StrongPass123!',
            first_name='Seed',
            last_name='Seller',
            email='seedclear-seller@example.com',
            role='seller',
        )
        buyer = User.objects.create_user(
            username='seedclear-buyer',
            password='StrongPass123!',
            first_name='Seed',
            last_name='Buyer',
            email='seedclear-buyer@example.com',
            role='buyer',
        )
        buyer_address = BuyerShippingAddress.objects.create(
            buyer=buyer,
            label='Home',
            recipient_name='Seed Buyer',
            address_line_1='1 Test Street',
            city='Dublin',
            state='Leinster',
            postal_code='D01TEST',
            country='Ireland',
            is_default=True,
        )
        payment_method = PaymentMethod.objects.create(
            buyer=buyer,
            label='Card',
            cardholder_name='Seed Buyer',
            card_brand='visa',
            full_card_number='4111111111111111',
            last_four='1111',
            expiry_month=12,
            expiry_year=2030,
            is_default=True,
        )
        seller_address = SellerShippingAddress.objects.create(
            seller=seller,
            label='Warehouse',
            recipient_name='Seed Seller',
            address_line_1='1 Warehouse Way',
            city='Dublin',
            state='Leinster',
            postal_code='D02TEST',
            country='Ireland',
            is_default=True,
        )
        product = Product.objects.create(
            seller_id=seller,
            product_name='Seed Cleanup Product',
            category='Jacket',
            price='49.99',
            stock=5,
            description='Cleanup test product',
            active=True,
            status='approved',
            redirect_to=None,
            deleted_at=None,
        )
        ProductApprovalRequest.submit_product(product=product, seller=seller)
        order = Order.objects.create(
            buyer=buyer,
            buyer_shipping_address=buyer_address,
            payment_method=payment_method,
            order_number='ORD-SEED-CLEAR',
            subtotal='49.99',
            shipping_cost='6.99',
            tax_amount='3.50',
            grand_total='60.48',
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            seller=seller,
            seller_shipping_address=seller_address,
            product_name='Seed Cleanup Product',
            unit_price='49.99',
            quantity=1,
            line_total='49.99',
        )

        deleted_count = clear_products()

        self.assertGreater(deleted_count, 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(ProductApprovalRequest.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)

    def test_seed_products_creates_images_for_seeded_products(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                seeded_count = seed_products()

                self.assertEqual(seeded_count, len(SEED_PRODUCTS))
                first_product = Product.objects.exclude(image='').exclude(image__isnull=True).first()
                self.assertIsNotNone(first_product)
                self.assertTrue(first_product.image.name.endswith('.png'))
