from decimal import Decimal
import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Avg, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from admin.models import UserActivity
from accounts.permissions import role_required
from sellers.models import Product
from sellers.webhooks import send_order_webhook

from .forms import BuyerShippingAddressForm, PaymentMethodForm
from .models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, SellerShippingAddress, Review


CHECKOUT_SHIPPING_RATE = Decimal('6.99')
CHECKOUT_TAX_RATE = Decimal('0.07')


def _get_cart_items_with_totals(buyer):
    # Centralize the cart query so cart and checkout always use the same database-backed rows.
    cart_items = []
    total_price = Decimal('0.00')

    for cart_item in CartItem.objects.select_related('product').filter(buyer=buyer):
        display_product = cart_item.product.display_product
        item_total = Decimal(str(display_product.get_discounted_price())) * Decimal(cart_item.quantity)
        total_price += item_total
        cart_items.append({
            'product': display_product,
            'quantity': cart_item.quantity,
            'item_total': item_total,
        })

    return cart_items, total_price


def _get_checkout_cart_rows(buyer):
    # Keep checkout-specific data together so validation and order creation use the same product rows.
    cart_rows = []

    for cart_item in CartItem.objects.select_related(
        'product',
        'product__seller_id',
        'product__redirect_to',
        'product__redirect_to__seller_id',
    ).filter(buyer=buyer):
        display_product = cart_item.product.display_product
        line_total = Decimal(str(display_product.get_discounted_price())) * Decimal(cart_item.quantity)
        cart_rows.append({
            'cart_item': cart_item,
            'product': display_product,
            'seller': display_product.seller_id,
            'quantity': cart_item.quantity,
            'item_total': line_total,
        })

    return cart_rows


def _group_rows_by_seller(cart_rows):
    grouped_rows = {}
    for row in cart_rows:
        grouped_rows.setdefault(row['seller'].id, {'seller': row['seller'], 'rows': []})['rows'].append(row)
    return list(grouped_rows.values())


def _get_default_seller_address(seller):
    return SellerShippingAddress.objects.filter(seller=seller).order_by('-is_default', 'id').first()


def _build_checkout_context(buyer, buyer_address_form=None, payment_method_form=None):
    cart_rows = _get_checkout_cart_rows(buyer)
    seller_groups = _group_rows_by_seller(cart_rows)
    subtotal = sum((row['item_total'] for row in cart_rows), Decimal('0.00'))
    shipping_cost = CHECKOUT_SHIPPING_RATE * Decimal(len(seller_groups)) if seller_groups else Decimal('0.00')
    tax_amount = subtotal * CHECKOUT_TAX_RATE
    grand_total = subtotal + shipping_cost + tax_amount

    seller_summaries = []
    missing_seller_addresses = []
    for seller_group in seller_groups:
        shipping_address = _get_default_seller_address(seller_group['seller'])
        seller_summaries.append({
            'seller': seller_group['seller'],
            'shipping_address': shipping_address,
            'items': seller_group['rows'],
        })
        if shipping_address is None:
            missing_seller_addresses.append(seller_group['seller'])

    return {
        'cart_rows': cart_rows,
        'cart_items': cart_rows,
        'seller_groups': seller_groups,
        'seller_summaries': seller_summaries,
        'buyer_addresses': BuyerShippingAddress.objects.filter(buyer=buyer).order_by('-is_default', 'label'),
        'payment_methods': PaymentMethod.objects.filter(buyer=buyer).order_by('-is_default', 'label'),
        'buyer_address_form': buyer_address_form or BuyerShippingAddressForm(prefix='address'),
        'payment_method_form': payment_method_form or PaymentMethodForm(prefix='payment'),
        'missing_seller_addresses': missing_seller_addresses,
        'subtotal': round(subtotal, 2),
        'shipping_cost': round(shipping_cost, 2),
        'tax_amount': round(tax_amount, 2),
        'grand_total': round(grand_total, 2),
    }


def _resolve_buyer_shipping_address(request):
    selected_address_id = request.POST.get('buyer_address_id')
    if selected_address_id:
        return get_object_or_404(BuyerShippingAddress, id=selected_address_id, buyer=request.user), BuyerShippingAddressForm(prefix='address')

    buyer_address_form = BuyerShippingAddressForm(request.POST, prefix='address')
    if not buyer_address_form.is_valid():
        return None, buyer_address_form

    buyer_address = buyer_address_form.save(commit=False)
    buyer_address.buyer = request.user
    buyer_address.is_default = not BuyerShippingAddress.objects.filter(buyer=request.user).exists()
    buyer_address.save()
    return buyer_address, buyer_address_form


def _resolve_payment_method(request):
    selected_payment_method_id = request.POST.get('payment_method_id')
    if selected_payment_method_id:
        return get_object_or_404(PaymentMethod, id=selected_payment_method_id, buyer=request.user), PaymentMethodForm(prefix='payment')

    payment_method_form = PaymentMethodForm(request.POST, prefix='payment')
    if not payment_method_form.is_valid():
        return None, payment_method_form

    payment_method = PaymentMethod.objects.create(
        buyer=request.user,
        label=payment_method_form.cleaned_data['label'],
        cardholder_name=payment_method_form.cleaned_data['cardholder_name'],
        card_brand=payment_method_form.cleaned_data['card_brand'],
        full_card_number=payment_method_form.cleaned_data['card_number'],
        last_four=payment_method_form.cleaned_data['card_number'][-4:],
        expiry_month=payment_method_form.cleaned_data['expiry_month'],
        expiry_year=payment_method_form.cleaned_data['expiry_year'],
        is_default=not PaymentMethod.objects.filter(buyer=request.user).exists(),
    )
    return payment_method, payment_method_form


def _generate_order_number():
    return f"ORD-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"


def _build_buyer_catalogue_url(search_query='', selected_category='', page_number=''):
    query_params = []

    if search_query:
        query_params.append(('q', search_query))
    if selected_category:
        query_params.append(('category', selected_category))
    if page_number:
        query_params.append(('page', page_number))

    base_url = reverse('buyer_home')
    if not query_params:
        return base_url
    return f"{base_url}?{urlencode(query_params)}"


def _get_compare_session(request):
    """Get the list of product IDs in the comparison session."""
    if 'compare_products' not in request.session:
        request.session['compare_products'] = []
    return request.session['compare_products']


def _add_to_compare_session(request, product_id):
    """Add a product ID to the comparison session. Limits to 10 items."""
    compare_list = _get_compare_session(request)
    product_id = int(product_id)
    if product_id not in compare_list and len(compare_list) < 10:
        compare_list.append(product_id)
        request.session['compare_products'] = compare_list
        request.session.modified = True
        return True
    return False


def _remove_from_compare_session(request, product_id):
    """Remove a product ID from the comparison session."""
    compare_list = _get_compare_session(request)
    product_id = int(product_id)
    if product_id in compare_list:
        compare_list.remove(product_id)
        request.session['compare_products'] = compare_list
        request.session.modified = True
        return True
    return False


def _clear_compare_session(request):
    """Clear all products from the comparison session."""
    if 'compare_products' in request.session:
        del request.session['compare_products']
        request.session.modified = True


@role_required('buyer')
def buyer_homepage(request):
    # Restrict buyer pages to logged-in buyers now that login also creates a session.
    search_query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()

    products = Product.objects.filter(active=True, status='approved', deleted_at__isnull=True)

    if search_query:
        products = products.filter(
            Q(product_name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__icontains=search_query)
        )

    if selected_category:
        products = products.filter(category=selected_category)

    products = products.order_by('id')
    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Add review statistics to each product.
    # Reviews may have been written against an older version of a product that was later
    # soft-deleted and replaced by this one (redirect_to chain), so include those too.
    products_with_reviews = []
    for product in page_obj.object_list:
        previous_ids = list(
            Product.objects.filter(redirect_to=product).values_list('id', flat=True)
        )
        all_ids = [product.id] + previous_ids

        review_stats = Review.objects.filter(
            product_id__in=all_ids,
            status='approved'
        ).aggregate(
            avg_rating=Avg('rating'),
            review_count=Count('id')
        )

        reviews = Review.objects.filter(
            product_id__in=all_ids,
            status='approved'
        ).select_related('buyer').order_by('-created_at')[:3]

        product_data = {
            'product': product,
            'avg_rating': review_stats['avg_rating'],
            'review_count': review_stats['review_count'] or 0,
            'reviews': reviews,
        }
        products_with_reviews.append(product_data)
    
    compare_list = _get_compare_session(request)
    context = {
        'products': products_with_reviews,
        'page_obj': page_obj,
        'current_page': page_obj.number,
        'search_query': search_query,
        'selected_category': selected_category,
        'category_choices': [choice[0] for choice in Product.CATEGORY_CHOICES],
        'compare_list': compare_list,
        'compare_count': len(compare_list),
    }
    return render(request, 'buyer_home.html',context)


@role_required('buyer')
def compare_products(request):
    compare_list = _get_compare_session(request)

    if len(compare_list) == 0:
        messages.error(request, 'Add products to compare before viewing the comparison.')
        return redirect('buyer_home')

    compared_products = list(
        Product.objects.filter(
            id__in=compare_list,
            active=True,
            status='approved',
            deleted_at__isnull=True,
        ).select_related('seller_id')
    )

    compared_products_by_id = {product.id: product for product in compared_products}
    ordered_products = [
        compared_products_by_id[product_id]
        for product_id in compare_list
        if product_id in compared_products_by_id
    ]

    # Remove products that are no longer available
    available_ids = [p.id for p in ordered_products]
    _clear_compare_session(request)
    for product_id in available_ids:
        _add_to_compare_session(request, product_id)

    if len(ordered_products) == 0:
        messages.error(request, 'No valid products available for comparison.')
        return redirect('buyer_home')

    return render(request, 'buyer_compare.html', {'products': ordered_products})


@role_required('buyer')
def buyer_order_history(request):
    orders = Order.objects.filter(buyer=request.user).prefetch_related(
        'items__seller',
        'items__seller_shipping_address',
        'items__return_request',
        'items__review',
    ).select_related(
        'buyer_shipping_address',
        'payment_method',
    ).order_by('-created_at')

    return render(request, 'buyer_order_history.html', {'orders': orders})


@role_required('buyer')
def add_to_compare(request, product_id):
    """Add a product to the comparison session and redirect back to the referring page."""
    product = get_object_or_404(Product, id=product_id, active=True, status='approved', deleted_at__isnull=True)
    
    added = _add_to_compare_session(request, product_id)
    if added:
        messages.success(request, f'{product.product_name} added to comparison.')
    else:
        compare_list = _get_compare_session(request)
        if len(compare_list) >= 10:
            messages.warning(request, 'You can compare up to 10 products at a time.')
        else:
            messages.info(request, f'{product.product_name} is already in your comparison.')
    
    return redirect(request.META.get('HTTP_REFERER', 'buyer_home'))


@role_required('buyer')
def remove_from_compare(request, product_id):
    """Remove a product from the comparison session."""
    product = get_object_or_404(Product, id=product_id)
    
    removed = _remove_from_compare_session(request, product_id)
    if removed:
        messages.success(request, f'{product.product_name} removed from comparison.')
    else:
        messages.info(request, f'{product.product_name} is not in your comparison.')
    
    return redirect(request.META.get('HTTP_REFERER', 'compare_products'))


@role_required('buyer')
def clear_compare(request):
    """Clear all products from the comparison session."""
    _clear_compare_session(request)
    messages.success(request, 'Comparison list cleared.')
    return redirect('buyer_home')


@role_required('buyer')
def add_to_cart(request, product_id):
    # Buyers should only be able to add currently approved active products to their cart.
    product = get_object_or_404(Product, id=product_id, active=True, status='approved', deleted_at__isnull=True)
    # Increment an existing cart row instead of storing transient session data.
    cart_item, created = CartItem.objects.get_or_create(
        buyer=request.user,
        product=product,
        defaults={'quantity': 1},
    )

    if not created:
        cart_item.quantity += 1
        cart_item.save(update_fields=['quantity', 'updated_at'])

    # Use the named route so the redirect still works if the local URL changes later.
    return redirect('buyer_home')


@role_required('buyer')
def update_cart(request, product_id):
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 0))
        cart_item = get_object_or_404(CartItem, buyer=request.user, product_id=product_id)

        # Quantity 0 removes the row completely, which keeps the cart table clean.
        if quantity > 0:
            cart_item.quantity = quantity
            cart_item.save(update_fields=['quantity', 'updated_at'])
        else:
            cart_item.delete()
    
    return redirect('cart_view')


@role_required('buyer')
def remove_from_cart(request, product_id):
    # Delete only the current buyer's cart row for the chosen product.
    CartItem.objects.filter(buyer=request.user, product_id=product_id).delete()
    return redirect('cart_view')


@role_required('buyer')
def cart_view(request):
    cart_items, total_price = _get_cart_items_with_totals(request.user)
        
    context = {
        'cart_items': cart_items,
        'total_price': total_price
        }
    return render(request, 'buyer_cart.html', context)


@role_required('buyer')
def checkout_view(request):
    context = _build_checkout_context(request.user)

    if not context['cart_rows']:
        return redirect("cart_view")

    if request.method == 'POST':
        if context['missing_seller_addresses']:
            messages.error(request, 'One or more sellers are missing saved shipping addresses, so this order cannot be placed yet.')
            return render(request, 'checkout.html', context)

        buyer_shipping_address, buyer_address_form = _resolve_buyer_shipping_address(request)
        payment_method, payment_method_form = _resolve_payment_method(request)

        if buyer_shipping_address is None or payment_method is None:
            context = _build_checkout_context(
                request.user,
                buyer_address_form=buyer_address_form,
                payment_method_form=payment_method_form,
            )
            return render(request, 'checkout.html', context)

        created_order_numbers = []
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    buyer=request.user,
                    buyer_shipping_address=buyer_shipping_address,
                    payment_method=payment_method,
                    order_number=_generate_order_number(),
                    subtotal=context['subtotal'],
                    shipping_cost=context['shipping_cost'],
                    tax_amount=context['tax_amount'],
                    grand_total=context['grand_total'],
                )

                for seller_group in context['seller_groups']:
                    seller = seller_group['seller']
                    seller_shipping_address = _get_default_seller_address(seller)
                    if seller_shipping_address is None:
                        raise ValueError('Missing seller shipping address.')

                    for row in seller_group['rows']:
                        product = row['product']
                        if product.deleted_at is not None or not product.active or product.status != 'approved':
                            raise ValueError('A product in your cart is no longer available for checkout.')
                        if product.stock < row['quantity']:
                            raise ValueError(f"Not enough stock for {product.product_name}.")

                        order_item = OrderItem.objects.create(
                            order=order,
                            product=product,
                            seller=seller,
                            seller_shipping_address=seller_shipping_address,
                            product_name=product.product_name,
                            unit_price=product.get_discounted_price(),
                            discount_percent_applied=product.discount_percent if product.is_discount_active else None,
                            quantity=row['quantity'],
                            line_total=round(row['item_total'], 2),
                        )

                        # Send webhook notification to the seller
                        send_order_webhook(order_item)

                        UserActivity.record_purchase(request.user, increment=row['quantity'])

                        product.stock -= row['quantity']
                        product.save(update_fields=['stock'])
                        row['cart_item'].delete()

                created_order_numbers.append(order.order_number)
        except ValueError as error:
            messages.error(request, str(error))
            context = _build_checkout_context(request.user)
            return render(request, 'checkout.html', context)

        messages.success(request, f"Order placed successfully: {', '.join(created_order_numbers)}")
        return redirect('cart_view')

    return render(request,'checkout.html', context)


@role_required('buyer')
def create_review(request, order_item_id):
	"""Create a new review for a completed order item."""
	from .models import Review
	from .forms import ReviewForm
	
	order_item = get_object_or_404(OrderItem, id=order_item_id, order__buyer=request.user, item_status='completed')
	
	# Check if review already exists
	if hasattr(order_item, 'review'):
		messages.info(request, 'You have already reviewed this item.')
		return redirect('buyer_order_history')
	
	if request.method == 'POST':
		form = ReviewForm(request.POST)
		if form.is_valid():
			review = form.save(commit=False)
			review.order_item = order_item
			review.buyer = request.user
			review.product = order_item.product
			review.save()
			messages.success(request, 'Your review has been submitted and is pending approval.')
			return redirect('buyer_order_history')
	else:
		form = ReviewForm()
	
	return render(request, 'review_form.html', {
		'form': form,
		'order_item': order_item,
		'action': 'Create Review'
	})


@role_required('buyer')
def edit_review(request, review_id):
	"""Edit an existing review."""
	from .models import Review
	from .forms import ReviewForm
	
	review = get_object_or_404(Review, id=review_id, buyer=request.user)
	
	if request.method == 'POST':
		form = ReviewForm(request.POST, instance=review)
		if form.is_valid():
			form.save()
			messages.success(request, 'Your review has been updated.')
			return redirect('buyer_order_history')
	else:
		form = ReviewForm(instance=review)
	
	return render(request, 'review_form.html', {
		'form': form,
		'review': review,
		'action': 'Edit Review'
	})


@role_required('buyer')
def buyer_delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, buyer=request.user)
    
    if request.method == 'POST':
        product_name = review.product.product_name
        review.delete()
        messages.success(request, f'Your review for "{product_name}" has been deleted.')
        return redirect('buyer_order_history')
    
    # Show confirmation page
    context = {
        'review': review,
        'product_name': review.product.product_name,
        'cancel_url': reverse('buyer_order_history'),
    }
    return render(request, 'review_delete_confirm.html', context)