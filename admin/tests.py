from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin.models import ProductApprovalRequest, SellerApprovalRequest
from products.models import Product


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

        self.assertEqual(response.status_code, 403)

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