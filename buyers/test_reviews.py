from django.test import TestCase
from django.urls import reverse
from django.contrib.messages import get_messages
from decimal import Decimal

from accounts.models import User
from sellers.models import Product
from .models import SellerShippingAddress
from .models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, Review


class ReviewTests(TestCase):
    def setUp(self):
        """Set up test users, products, and orders."""
        # Create seller
        self.seller = User.objects.create_user(
            username='reviewer_seller',
            password='StrongPass123!',
            first_name='Seller',
            last_name='One',
            email='seller@example.com',
            role='seller',
        )
        
        # Create buyer
        self.buyer = User.objects.create_user(
            username='reviewer_buyer',
            password='StrongPass123!',
            first_name='Buyer',
            last_name='One',
            email='buyer@example.com',
            role='buyer',
        )
        
        # Create product
        self.product = Product.objects.create(
            seller_id=self.seller,
            product_name='Test Product',
            category='Clothing',
            price='50.00',
            stock=10,
            active=True,
            redirect_to=None,
            status='approved',
            description='A test product for reviews',
            deleted_at=None,
        )
        
        # Create seller shipping address
        self.seller_address = SellerShippingAddress.objects.create(
            seller=self.seller,
            label='Warehouse',
            recipient_name='Seller One',
            address_line_1='123 Seller Street',
            city='Cork',
            state='Munster',
            postal_code='T12TEST',
            country='Ireland',
            is_default=True,
        )
        
        # Create buyer shipping address
        self.buyer_address = BuyerShippingAddress.objects.create(
            buyer=self.buyer,
            recipient_name='Buyer One',
            address_line_1='456 Buyer Road',
            city='Dublin',
            state='Leinster',
            postal_code='D01TEST',
            country='Ireland',
        )
        
        # Create payment method
        self.payment_method = PaymentMethod.objects.create(
            buyer=self.buyer,
            card_brand='visa',
            last_four='1234',
            full_card_number='4111111111111234',
            expiry_month='12',
            expiry_year= '2030',
        )
        
        # Create completed order
        self.order = Order.objects.create(
            buyer=self.buyer,
            buyer_shipping_address=self.buyer_address,
            payment_method=self.payment_method,
            order_number='TEST-ORDER-001',
            subtotal='50.00',
            shipping_cost='6.99',
            tax_amount='3.50',
            grand_total='60.49',
        )
        
        # Create completed order item
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            seller_shipping_address=self.seller_address,
            product_name='Test Product',
            unit_price='50.00',
            quantity=1,
            line_total='50.00',
            item_status='completed',
        )
        
        # Create admin
        self.admin = User.objects.create_user(
            username='reviewer_admin',
            password='StrongPass123!',
            first_name='Admin',
            last_name='User',
            email='admin@example.com',
            role='admin',
        )

        # Log in buyer
        self.client.login(username='reviewer_buyer', password='StrongPass123!')
    
    def test_buyer_can_create_review(self):
        """Test that a buyer can create a review for a completed order item."""
        response = self.client.post(
            reverse('create_review', args=[self.order_item.id]),
            {
                'rating': 5,
                'title': 'Great Product!',
                'comment': 'This product exceeded my expectations.',
            },
            follow=True,
        )
        
        # Check that review was created
        self.assertTrue(Review.objects.filter(order_item=self.order_item).exists())
        review = Review.objects.get(order_item=self.order_item)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.title, 'Great Product!')
        self.assertEqual(review.comment, 'This product exceeded my expectations.')
        self.assertEqual(review.status, 'pending')
        self.assertEqual(review.buyer, self.buyer)
        self.assertEqual(review.product, self.product)
    
    def test_buyer_can_edit_review(self):
        """Test that a buyer can edit their own review."""
        # Create initial review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=3,
            title='Okay Product',
            comment='It was okay.',
            status='pending',
        )
        
        # Edit the review
        response = self.client.post(
            reverse('edit_review', args=[review.id]),
            {
                'rating': 4,
                'title': 'Good Product',
                'comment': 'Actually, it was pretty good!',
            },
            follow=True,
        )
        
        # Check that review was updated
        review.refresh_from_db()
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.title, 'Good Product')
        self.assertEqual(review.comment, 'Actually, it was pretty good!')
    
    def test_buyer_can_delete_review(self):
        """Test that a buyer can delete their own review."""
        # Create review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Great!',
            comment='Loved it!',
            status='pending',
        )
        
        review_id = review.id
        
        # Delete the review (POST to confirmation form)
        response = self.client.post(
            reverse('buyer_delete_review', args=[review_id]),
            follow=True,
        )
        
        # Check that review was deleted
        self.assertFalse(Review.objects.filter(id=review_id).exists())
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('deleted' in str(m).lower() for m in messages))
    
    def test_delete_review_redirects_to_order_history(self):
        """Test that deleting a review redirects to order history."""
        # Create review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Great!',
            comment='Loved it!',
            status='pending',
        )
        
        # Delete the review (POST to confirmation form)
        response = self.client.post(
            reverse('buyer_delete_review', args=[review.id]),
            follow=True,
        )
        
        # Check redirect
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Buyer Order History')
    
    def test_buyer_cannot_create_duplicate_review(self):
        """Test that a buyer cannot create two reviews for the same order item."""
        # Create first review
        Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Great!',
            comment='Loved it!',
            status='pending',
        )
        
        # Try to create second review (should fail or prevent via form)
        response = self.client.post(
            reverse('create_review', args=[self.order_item.id]),
            {
                'rating': 3,
                'title': 'Changed my mind',
                'comment': 'Actually not as good',
            },
        )
        
        # Should only have one review
        self.assertEqual(Review.objects.filter(order_item=self.order_item).count(), 1)
    
    def test_buyer_cannot_review_incomplete_order_item(self):
        """Test that a buyer cannot review an incomplete order item."""
        # Create incomplete order item
        incomplete_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            seller_shipping_address=self.seller_address,
            product_name='Test Product',
            unit_price='50.00',
            quantity=1,
            line_total='50.00',
            item_status='processing',  # Not completed
        )
        
        # Try to create review
        response = self.client.post(
            reverse('create_review', args=[incomplete_item.id]),
            {
                'rating': 5,
                'title': 'Great!',
                'comment': 'Loved it!',
            },
        )
        
        # Should not create review
        self.assertFalse(Review.objects.filter(order_item=incomplete_item).exists())
    
    def test_review_appears_in_order_history(self):
        """Test that a review appears in the buyer's order history."""
        # Create review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Excellent!',
            comment='Really loved this product!',
            status='pending',
        )
        
        # Get order history
        response = self.client.get(reverse('buyer_order_history'))
        
        # Check that review link is present
        self.assertContains(response, 'Edit Review')
        self.assertContains(response, 'Delete Review')
    
    def test_approved_review_shows_on_product_listing(self):
        """Test that approved reviews show on product listing."""
        # Create and approve review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Excellent!',
            comment='Really loved this product!',
            status='approved',
        )
        
        # Get homepage
        response = self.client.get(reverse('buyer_home'))
        
        # Should show review count
        self.assertContains(response, '(1 review)')
    
    def test_pending_review_not_shown_publicly(self):
        """Test that pending reviews don't show on product listing."""
        # Create pending review
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Excellent!',
            comment='Really loved this product!',
            status='pending',
        )
        
        # Get homepage while logged in
        response = self.client.get(reverse('buyer_home'))
        
        # Should not show pending review details (only approved reviews show)
        self.assertNotContains(response, 'Excellent!')
    
    def test_review_rating_display(self):
        """Test that review ratings are displayed correctly."""
        for rating in [1, 2, 3, 4, 5]:
            order_item = OrderItem.objects.create(
                order=self.order,
                product=self.product,
                seller=self.seller,
                seller_shipping_address=self.seller_address,
                product_name='Test Product',
                unit_price='50.00',
                quantity=1,
                line_total='50.00',
                item_status='completed',
            )
            
            review = Review.objects.create(
                order_item=order_item,
                buyer=self.buyer,
                product=self.product,
                rating=rating,
                title=f'{rating} Stars',
                comment=f'This is a {rating} star review',
                status='approved',
            )
            
            self.assertEqual(review.rating, rating)
            self.assertTrue(review.is_approved)

    def test_admin_rejects_review(self):
        """Test that an admin can reject a pending review."""
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=4,
            title='Good Product',
            comment='I liked it.',
            status='pending',
        )

        self.client.force_login(self.admin)
        response = self.client.post(reverse('reject_review', args=[review.id]))

        review.refresh_from_db()
        self.assertEqual(review.status, 'rejected')
        self.assertRedirects(response, reverse('review_moderation'))

    def test_admin_approves_review(self):
        """Test that an admin can approve a pending review."""
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Excellent!',
            comment='Really loved it.',
            status='pending',
        )

        self.client.force_login(self.admin)
        response = self.client.post(reverse('approve_review', args=[review.id]))

        review.refresh_from_db()
        self.assertEqual(review.status, 'approved')
        self.assertRedirects(response, reverse('review_moderation'))

    def test_admin_deletes_review(self):
        """Test that an admin can delete a review."""
        review = Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=2,
            title='Not great',
            comment='Disappointed.',
            status='pending',
        )
        review_id = review.id

        self.client.force_login(self.admin)
        response = self.client.post(reverse('delete_review', args=[review_id]))

        self.assertFalse(Review.objects.filter(id=review_id).exists())
        self.assertRedirects(response, reverse('review_moderation'))

    def test_seller_can_view_approved_reviews(self):
        """Test that a seller can see approved reviews for their products."""
        Review.objects.create(
            order_item=self.order_item,
            buyer=self.buyer,
            product=self.product,
            rating=5,
            title='Fantastic!',
            comment='Really loved this product!',
            status='approved',
        )

        self.client.force_login(self.seller)
        response = self.client.get(reverse('seller_reviews'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fantastic!')
        self.assertContains(response, 'Really loved this product!')
