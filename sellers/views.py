from collections import OrderedDict
from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from accounts.permissions import role_required
from admin.models import ProductApprovalRequest, UserActivity
from buyers.forms import SellerShippingAddressForm
from buyers.models import OrderItem, SellerShippingAddress

from .models import Product, ReturnRequest
from .forms import ProductForm


def _update_parent_order_status(order):
    item_statuses = list(order.items.values_list('item_status', flat=True))
    if not item_statuses:
        return

    if all(status in {'completed', 'returned'} for status in item_statuses):
        order.status = 'completed'
    elif all(status in {'shipped', 'completed', 'returned'} for status in item_statuses):
        order.status = 'shipped'
    elif any(status in {'processing', 'shipped', 'completed', 'returned'} for status in item_statuses):
        order.status = 'processing'
    else:
        order.status = 'placed'

    order.save(update_fields=['status', 'updated_at'])


@role_required('seller')
def seller_home(request):
    from .models import Notification

    has_default_shipping_address = SellerShippingAddress.objects.filter(seller=request.user, is_default=True).exists()
    unseen_notifications = Notification.objects.filter(seller=request.user, is_seen=False).order_by('-created_at')
    products = Product.objects.filter(seller_id=request.user, deleted_at__isnull=True)

    return render(request, 'sellers/seller_home.html', {
        'has_default_shipping_address': has_default_shipping_address,
        'unseen_notifications': unseen_notifications,
        'products': products,
    })


@role_required('seller')
def seller_shipping_address(request):
    address = SellerShippingAddress.objects.filter(seller=request.user).order_by('-is_default', 'id').first()

    if request.method == 'POST':
        form = SellerShippingAddressForm(request.POST, instance=address)
        if form.is_valid():
            saved_address = form.save(commit=False)
            saved_address.seller = request.user
            saved_address.is_default = True
            saved_address.save()
            SellerShippingAddress.objects.filter(seller=request.user).exclude(id=saved_address.id).update(is_default=False)
            return redirect('seller_home')
    else:
        form = SellerShippingAddressForm(instance=address)

    return render(request, 'sellers/seller_shipping_address.html', {
        'form': form,
        'address': address,
    })


@role_required('seller')
def seller_order_history(request):
    order_items = OrderItem.objects.filter(seller=request.user).select_related(
        'order',
        'order__buyer',
        'order__buyer_shipping_address',
        'seller_shipping_address',
        'return_request',
    ).order_by('-order__created_at', 'id')

    grouped_orders = OrderedDict()
    completed_earnings = Decimal('0.00')
    for order_item in order_items:
        grouped_order = grouped_orders.setdefault(order_item.order_id, {
            'order': order_item.order,
            'buyer': order_item.order.buyer,
            'buyer_shipping_address': order_item.order.buyer_shipping_address,
            'items': [],
            'seller_subtotal': Decimal('0.00'),
            'earned_total': Decimal('0.00'),
        })
        grouped_order['items'].append(order_item)
        grouped_order['seller_subtotal'] += order_item.line_total
        if order_item.item_status == 'completed' and (
            order_item.return_request_record is None or order_item.return_request_record.status != 'approved'
        ):
            grouped_order['earned_total'] += order_item.line_total
            completed_earnings += order_item.line_total

    return render(request, 'sellers/seller_order_history.html', {
        'grouped_orders': grouped_orders.values(),
        'item_status_choices': OrderItem.ITEM_STATUS_CHOICES,
        'completed_earnings': completed_earnings,
    })


@role_required('seller')
def seller_return_requests(request):
    pending_requests = ReturnRequest.objects.filter(
        order_item__seller=request.user,
        status='pending',
    ).select_related(
        'order_item',
        'order_item__order',
        'order_item__order__buyer',
    ).order_by('-created_at')

    return render(request, 'sellers/seller_return_requests.html', {'pending_requests': pending_requests})


@role_required('seller')
def update_order_item_status(request, item_id):
    order_item = get_object_or_404(OrderItem.objects.select_related('order'), id=item_id, seller=request.user)

    if request.method == 'POST':
        allowed_statuses = {choice[0] for choice in OrderItem.ITEM_STATUS_CHOICES}
        new_status = request.POST.get('item_status')
        if new_status in allowed_statuses:
            previous_status = order_item.item_status
            order_item.item_status = new_status
            order_item.save(update_fields=['item_status'])
            if previous_status != 'completed' and new_status == 'completed':
                UserActivity.record_completed_sale(request.user, increment=order_item.quantity)
            _update_parent_order_status(order_item.order)

    return redirect('seller_order_history')


@role_required('buyer')
def request_return(request, item_id):
    order_item = get_object_or_404(
        OrderItem.objects.select_related('order', 'seller', 'return_request'),
        id=item_id,
        order__buyer=request.user,
    )

    if order_item.return_request_record is not None:
        messages.info(request, 'A return request already exists for this item.')
        return redirect('buyer_return_requests')

    if order_item.item_status != 'completed':
        messages.error(request, 'Returns can only be requested after the item is marked as completed.')
        return redirect('buyer_order_history')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if reason:
            ReturnRequest.objects.create(order_item=order_item, reason=reason)
            messages.success(request, 'Return request submitted successfully.')
            return redirect('buyer_return_requests')
        messages.error(request, 'Please provide a reason for the return request.')

    return render(request, 'sellers/return_form.html', {'order_item': order_item})


@role_required('buyer')
def buyer_return_requests(request):
    pending_requests = ReturnRequest.objects.filter(
        order_item__order__buyer=request.user,
        status='pending',
    ).select_related(
        'order_item',
        'order_item__order',
        'order_item__seller',
    ).order_by('-created_at')

    return render(request, 'sellers/buyer_return_requests.html', {'pending_requests': pending_requests})


@role_required('seller')
def product_creation(request):
    has_default_shipping_address = SellerShippingAddress.objects.filter(seller=request.user, is_default=True).exists()

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            # System-managed fields are assigned here so new products always enter the approval flow correctly.
            product = form.save(commit=False)
            product.seller_id = request.user
            product.active = False
            product.status = 'pending'
            product.deleted_at = None
            product.redirect_to = None
            product.save()

            # Every new seller product gets a matching approval request for the admin review queue.
            ProductApprovalRequest.submit_product(product=product, seller=request.user)
            return redirect('seller_home')
    else:
        form = ProductForm()

    return render(request, 'sellers/product_creation.html', {
        'form': form,
        'has_default_shipping_address': has_default_shipping_address,
    })


@role_required('seller')
def product_list(request):
    return redirect('seller_home')


@role_required('seller')
def product_edit(request, id):
    product = get_object_or_404(Product, id=id, seller_id=request.user, deleted_at__isnull=True)

    if request.method == "POST":
        # Approved products are edited through a replacement row so buyers keep seeing the current live listing.
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            if product.active and product.status == 'approved':
                replacement_product = Product.objects.create(
                    seller_id=request.user,
                    image=form.cleaned_data['image'] or product.image,
                    product_name=form.cleaned_data['product_name'],
                    category=form.cleaned_data['category'],
                    price=form.cleaned_data['price'],
                    stock=form.cleaned_data['stock'],
                    description=form.cleaned_data['description'],
                    active=False,
                    status='pending',
                    redirect_to=None,
                    deleted_at=None,
                )
                ProductApprovalRequest.submit_product(
                    product=replacement_product,
                    seller=request.user,
                    original_product=product,
                )
            else:
                editable_product = form.save(commit=False)
                editable_product.id = product.id
                editable_product.seller_id = request.user
                editable_product.active = False
                editable_product.status = 'pending'
                editable_product.redirect_to = product.redirect_to
                editable_product.deleted_at = None
                editable_product.save()
                ProductApprovalRequest.submit_product(product=editable_product, seller=request.user)
            return redirect('seller_home')
    else:
        form = ProductForm(instance=product)

    return render(request, 'sellers/product_edit.html', {
        'form': form,
        'product': product
    })


@role_required('seller')
def product_delete(request, id):
    product = get_object_or_404(Product, id=id, seller_id=request.user, deleted_at__isnull=True)

    if request.method == "POST":
        # Soft-delete the listing so related rows can still resolve historical information.
        product.soft_delete()
        return redirect('seller_home')

    return render(request, 'sellers/product_delete.html', {'product': product})

@role_required('seller')
def approve_return(request, return_id):
    return_request = get_object_or_404(ReturnRequest, id=return_id, order_item__seller=request.user)
    order_item = return_request.order_item

    if return_request.status != 'approved':
        product = order_item.product
        product.stock += order_item.quantity
        product.save(update_fields=['stock'])

        order_item.item_status = 'returned'
        order_item.save(update_fields=['item_status'])
        _update_parent_order_status(order_item.order)

    return_request.status = 'approved'
    return_request.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Return request approved.')
    return redirect('seller_return_requests')

@role_required('seller')
def reject_return(request, return_id):
    return_request = get_object_or_404(ReturnRequest, id=return_id, order_item__seller=request.user)
    return_request.status = 'rejected'
    return_request.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Return request rejected.')
    return redirect('seller_return_requests')


@role_required('seller')
def webhook_settings(request):
    from .models import WebhookURL

    webhook, _ = WebhookURL.objects.get_or_create(seller=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_url':
            new_url = request.POST.get('webhook_url', '').strip()
            if new_url:
                webhook.webhook_url = new_url
                webhook.save(update_fields=['webhook_url', 'updated_at'])
                messages.success(request, 'Webhook URL saved.')
            else:
                webhook.webhook_url = ''
                webhook.is_active = False
                webhook.save(update_fields=['webhook_url', 'is_active', 'updated_at'])
                messages.success(request, 'Webhook URL cleared and deactivated.')

        elif action == 'toggle':
            if not webhook.webhook_url:
                messages.error(request, 'Please save a webhook URL before activating.')
            else:
                webhook.is_active = not webhook.is_active
                webhook.save(update_fields=['is_active', 'updated_at'])
                status = 'activated' if webhook.is_active else 'deactivated'
                messages.success(request, f'Webhook {status} successfully.')

        return redirect('webhook_settings')

    return render(request, 'sellers/webhook_settings.html', {'webhook': webhook})


@role_required('seller')
def dismiss_notification(request, notification_id):
    """Mark a notification as seen/dismissed."""
    from .models import Notification
    
    notification = get_object_or_404(Notification, id=notification_id, seller=request.user)
    notification.is_seen = True
    notification.save(update_fields=['is_seen'])
    
    messages.success(request, 'Notification dismissed.')
    return redirect('seller_home')


@role_required('seller')
def manage_product_discounts(request):
    """Display all seller's products with discount management options."""
    products = Product.objects.filter(seller_id=request.user, deleted_at__isnull=True).order_by('product_name')
    
    context = {
        'products': products,
    }
    return render(request, 'sellers/manage_discounts.html', context)


@role_required('seller')
def apply_discount(request, product_id):
    """Apply or edit discount for a product."""
    from .forms import DiscountForm
    
    product = get_object_or_404(Product, id=product_id, seller_id=request.user, deleted_at__isnull=True)
    
    next_url = request.GET.get('next') or request.POST.get('next') or 'manage_product_discounts'
    if next_url not in ('manage_product_discounts', 'seller_home'):
        next_url = 'manage_product_discounts'

    if request.method == 'POST':
        form = DiscountForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'Discount applied to "{product.product_name}" successfully.')
            return redirect(next_url)
    else:
        form = DiscountForm(instance=product)

    context = {
        'form': form,
        'product': product,
        'next': next_url,
    }
    return render(request, 'sellers/apply_discount.html', context)


@role_required('seller')
def remove_discount(request, product_id):
    """Remove discount from a product."""
    product = get_object_or_404(Product, id=product_id, seller_id=request.user, deleted_at__isnull=True)

    next_url = request.GET.get('next') or request.POST.get('next') or 'manage_product_discounts'
    if next_url not in ('manage_product_discounts', 'seller_home'):
        next_url = 'manage_product_discounts'

    if request.method == 'POST':
        product.discount_percent = None
        product.discount_start_date = None
        product.discount_end_date = None
        product.save(update_fields=['discount_percent', 'discount_start_date', 'discount_end_date'])
        messages.success(request, f'Discount removed from "{product.product_name}".')
        return redirect(next_url)

    context = {
        'product': product,
        'next': next_url,
    }
    return render(request, 'sellers/remove_discount_confirm.html', context)


@role_required('seller')
def seller_reviews(request):
    """View all reviews for the seller's products."""
    from buyers.models import Review
    
    # Get all approved reviews for this seller's products
    reviews = Review.objects.filter(
        product__seller_id=request.user,
        status='approved'
    ).select_related('buyer', 'product').order_by('-created_at')
    
    # Calculate average rating
    from django.db.models import Avg
    avg_rating = Review.objects.filter(
        product__seller_id=request.user,
        status='approved'
    ).aggregate(Avg('rating'))['rating__avg'] or 0
    
    context = {
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'total_reviews': reviews.count(),
    }
    return render(request, 'sellers/seller_reviews.html', context)





