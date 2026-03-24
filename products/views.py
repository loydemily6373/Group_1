from collections import OrderedDict
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404

from accounts.permissions import role_required
from admin.models import ProductApprovalRequest
from buyers.forms import SellerShippingAddressForm
from buyers.models import OrderItem, SellerShippingAddress

from .models import Product
from .forms import ProductForm


def _update_parent_order_status(order):
    item_statuses = list(order.items.values_list('item_status', flat=True))
    if not item_statuses:
        return

    if all(status == 'completed' for status in item_statuses):
        order.status = 'completed'
    elif all(status in {'shipped', 'completed'} for status in item_statuses):
        order.status = 'shipped'
    elif any(status in {'processing', 'shipped', 'completed'} for status in item_statuses):
        order.status = 'processing'
    else:
        order.status = 'placed'

    order.save(update_fields=['status', 'updated_at'])


@role_required('seller')
def seller_home(request):
    # Seller pages now require the logged-in user to have the seller role.
    has_default_shipping_address = SellerShippingAddress.objects.filter(seller=request.user, is_default=True).exists()
    return render(request, 'products/seller_home.html', {'has_default_shipping_address': has_default_shipping_address})


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

    return render(request, 'products/seller_shipping_address.html', {
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
        })
        grouped_order['items'].append(order_item)
        grouped_order['seller_subtotal'] += order_item.line_total
        if order_item.item_status == 'completed':
            completed_earnings += order_item.line_total

    return render(request, 'products/seller_order_history.html', {
        'grouped_orders': grouped_orders.values(),
        'item_status_choices': OrderItem.ITEM_STATUS_CHOICES,
        'completed_earnings': completed_earnings,
    })


@role_required('seller')
def update_order_item_status(request, item_id):
    order_item = get_object_or_404(OrderItem.objects.select_related('order'), id=item_id, seller=request.user)

    if request.method == 'POST':
        allowed_statuses = {choice[0] for choice in OrderItem.ITEM_STATUS_CHOICES}
        new_status = request.POST.get('item_status')
        if new_status in allowed_statuses:
            order_item.item_status = new_status
            order_item.save(update_fields=['item_status'])
            _update_parent_order_status(order_item.order)

    return redirect('seller_order_history')


@role_required('seller')
def product_creation(request):
    has_default_shipping_address = SellerShippingAddress.objects.filter(seller=request.user, is_default=True).exists()

    if request.method == "POST":
        form = ProductForm(request.POST)
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
            return redirect('product_list')
    else:
        form = ProductForm()

    return render(request, 'products/product_creation.html', {
        'form': form,
        'has_default_shipping_address': has_default_shipping_address,
    })


@role_required('seller')
def product_list(request):
    # Sellers should only see their own non-deleted listings.
    products = Product.objects.filter(seller_id=request.user, deleted_at__isnull=True)
    return render(request, 'products/product_list.html', {'products': products})


@role_required('seller')
def product_edit(request, id):
    product = get_object_or_404(Product, id=id, seller_id=request.user, deleted_at__isnull=True)

    if request.method == "POST":
        # Approved products are edited through a replacement row so buyers keep seeing the current live listing.
        form = ProductForm(request.POST)
        if form.is_valid():
            if product.active and product.status == 'approved':
                replacement_product = Product.objects.create(
                    seller_id=request.user,
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
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)

    return render(request, 'products/product_edit.html', {
        'form': form,
        'product': product
    })


@role_required('seller')
def product_delete(request, id):
    product = get_object_or_404(Product, id=id, seller_id=request.user, deleted_at__isnull=True)

    if request.method == "POST":
        # Soft-delete the listing so related rows can still resolve historical information.
        product.soft_delete()
        return redirect('product_list')

    return render(request, 'products/product_delete.html', {'product': product})


