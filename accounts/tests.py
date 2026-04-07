from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from admin.models import SellerApprovalRequest
from buyers.models import SellerShippingAddress

from .models import User


class AuthenticationFlowTests(TestCase):
	def setUp(self):
		# Use DRF's APIClient so we can test both JSON endpoints and rendered pages.
		self.client = APIClient()

	def test_signup_page_renders(self):
		response = self.client.get(reverse('signup'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)

	def test_index_login_link_opens_login_page_with_form(self):
		index_response = self.client.get(reverse('index'))

		self.assertEqual(index_response.status_code, status.HTTP_200_OK)
		self.assertContains(index_response, 'href="%s"' % reverse('login'))
		self.assertContains(index_response, 'Log In')

		login_response = self.client.get(reverse('login'))

		self.assertEqual(login_response.status_code, status.HTTP_200_OK)
		self.assertContains(login_response, '<form id="loginForm">', html=False)
		self.assertContains(login_response, 'id="username"', html=False)
		self.assertContains(login_response, 'id="password"', html=False)

	def test_register_api_creates_buyer_account(self):
		# A normal buyer signup should succeed and persist the extra profile fields.
		payload = {
			'username': 'buyer_user',
			'password': 'StrongPass123!',
			'first_name': 'Buyer',
			'last_name': 'User',
			'email': 'buyer@example.com',
			'role': 'buyer',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		created_user = User.objects.get(username='buyer_user')
		self.assertEqual(created_user.role, 'buyer')
		self.assertEqual(created_user.email, 'buyer@example.com')
		self.assertTrue(created_user.is_active)

	def test_register_api_rejects_duplicate_username(self):
		User.objects.create_user(
			username='buyer_user',
			password='StrongPass123!',
			first_name='Existing',
			last_name='User',
			email='existing@example.com',
			role='buyer',
		)

		payload = {
			'username': 'buyer_user',
			'password': 'StrongPass123!',
			'first_name': 'Duplicate',
			'last_name': 'User',
			'email': 'duplicate@example.com',
			'role': 'buyer',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('username', response.data)
		self.assertEqual(User.objects.filter(username='buyer_user').count(), 1)

	def test_register_api_rejects_weak_password(self):
		payload = {
			'username': 'weak_password_user',
			'password': 'weakpass',
			'first_name': 'Weak',
			'last_name': 'Password',
			'email': 'weak@example.com',
			'role': 'buyer',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('password', response.data)
		self.assertFalse(User.objects.filter(username='weak_password_user').exists())

	def test_register_api_creates_inactive_seller_and_request(self):
		# Seller signups should create the user account but hold login access until admin approval.
		payload = {
			'username': 'seller_user',
			'password': 'StrongPass123!',
			'first_name': 'Seller',
			'last_name': 'User',
			'email': 'seller@example.com',
			'role': 'seller',
			'seller_address_label': 'Main Warehouse',
			'seller_recipient_name': 'Seller User',
			'seller_address_line_1': '123 Seller Street',
			'seller_address_line_2': 'Unit 2',
			'seller_city': 'Dublin',
			'seller_state': 'Leinster',
			'seller_postal_code': 'D01SELL',
			'seller_country': 'Ireland',
			'seller_phone_number': '0123456789',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		created_user = User.objects.get(username='seller_user')
		seller_request = SellerApprovalRequest.objects.get(user=created_user)
		seller_address = SellerShippingAddress.objects.get(seller=created_user)
		self.assertFalse(created_user.is_active)
		self.assertEqual(created_user.role, 'seller')
		self.assertEqual(seller_request.approved, None)
		self.assertEqual(seller_address.label, 'Main Warehouse')
		self.assertTrue(seller_address.is_default)

	def test_register_api_rejects_seller_signup_without_address(self):
		payload = {
			'username': 'seller_without_address',
			'password': 'StrongPass123!',
			'first_name': 'Seller',
			'last_name': 'MissingAddress',
			'email': 'seller_without_address@example.com',
			'role': 'seller',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('seller_address_label', response.data)
		self.assertFalse(User.objects.filter(username='seller_without_address').exists())

	def test_register_api_rejects_admin_signup(self):
		# Public registration should never allow someone to create an admin account.
		payload = {
			'username': 'admin_attempt',
			'password': 'StrongPass123!',
			'first_name': 'Bad',
			'last_name': 'Actor',
			'email': 'bad@example.com',
			'role': 'admin',
		}

		response = self.client.post(reverse('account_register_api'), payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertFalse(User.objects.filter(username='admin_attempt').exists())

	def test_login_api_returns_tokens_and_role(self):
		# The login API should return tokens, role data, and create a session for page protection.
		User.objects.create_user(
			username='existing_buyer',
			password='StrongPass123!',
			first_name='Existing',
			last_name='Buyer',
			email='existing@example.com',
			role='buyer',
		)

		response = self.client.post(
			reverse('account_token_api'),
			{'username': 'existing_buyer', 'password': 'StrongPass123!'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('access', response.data)
		self.assertIn('refresh', response.data)
		self.assertEqual(response.data['role'], 'buyer')
		# Reuse the same test client to confirm the login endpoint also authenticated the browser session.
		buyer_page = self.client.get(reverse('buyer_home'))
		self.assertEqual(buyer_page.status_code, status.HTTP_200_OK)

	def test_inactive_seller_cannot_log_in(self):
		# Seller accounts should remain blocked from login until an admin approves them.
		User.objects.create_user(
			username='pending_seller',
			password='StrongPass123!',
			first_name='Pending',
			last_name='Seller',
			email='pending@example.com',
			role='seller',
			is_active=False,
		)

		response = self.client.post(
			reverse('account_token_api'),
			{'username': 'pending_seller', 'password': 'StrongPass123!'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
		self.assertEqual(
			response.data['detail'],
			'Your seller account is waiting for admin approval before you can log in.'
		)

	def test_wrong_role_cannot_open_buyer_page(self):
		# Logged-in sellers should be blocked from buyer-only pages.
		seller_user = User.objects.create_user(
			username='existing_seller',
			password='StrongPass123!',
			first_name='Existing',
			last_name='Seller',
			email='seller@example.com',
			role='seller',
		)

		self.client.force_login(seller_user)
		response = self.client.get(reverse('buyer_home'))

		self.assertRedirects(response, reverse('seller_home'))

	def test_wrong_role_cannot_open_seller_page(self):
		# Logged-in buyers should be blocked from seller-only pages.
		buyer_user = User.objects.create_user(
			username='existing_buyer',
			password='StrongPass123!',
			first_name='Existing',
			last_name='Buyer',
			email='buyer@example.com',
			role='buyer',
		)

		self.client.force_login(buyer_user)
		response = self.client.get(reverse('seller_home'))

		self.assertRedirects(response, reverse('buyer_home'))

	def test_wrong_role_cannot_open_admin_page(self):
		# Logged-in non-admin users should be blocked from admin-only pages.
		buyer_user = User.objects.create_user(
			username='buyer_for_admin_check',
			password='StrongPass123!',
			first_name='Buyer',
			last_name='User',
			email='buyer-admin-check@example.com',
			role='buyer',
		)

		self.client.force_login(buyer_user)
		response = self.client.get(reverse('admin_home'))

		self.assertRedirects(response, reverse('buyer_home'))

	def test_logout_view_clears_session_and_redirects_home(self):
		buyer_user = User.objects.create_user(
			username='logout_buyer',
			password='StrongPass123!',
			first_name='Logout',
			last_name='Buyer',
			email='logoutbuyer@example.com',
			role='buyer',
		)

		self.client.force_login(buyer_user)
		response = self.client.get(reverse('account_logout'))

		self.assertRedirects(response, reverse('index'))
		protected_page = self.client.get(reverse('buyer_home'))
		self.assertEqual(protected_page.status_code, status.HTTP_302_FOUND)

	# SQL injection test
	def test_sql_injection_login(self):
		response = self.client.post(
			reverse('account_token_api'),
			{
				'username': "' OR 1=1 --",
				'password': 'anything',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
		self.assertNotIn('_auth_user_id', self.client.session)

	def test_invalid_login_rejected(self):
		response = self.client.post(reverse('login'), {
			'username': 'wronguser',
			'password': 'wrongpass'
		})

		self.assertEqual(response.status_code, 200)
