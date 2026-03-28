from decimal import Decimal
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from admin.models import UserActivity
from accounts.permissions import role_required
from sellers.models import Product

from .forms import BuyerShippingAddressForm, PaymentMethodForm
from .models import BuyerShippingAddress, CartItem, Order, OrderItem, PaymentMethod, SellerShippingAddress


CHECKOUT_SHIPPING_RATE = Decimal('6.99')
CHECKOUT_TAX_RATE = Decimal('0.07')


def _get_cart_items_with_totals(buyer):
    # Centralize the cart query so cart and checkout always use the same database-backed rows.
    cart_items = []
    total_price = Decimal('0.00')

    for cart_item in CartItem.objects.select_related('product').filter(buyer=buyer):
        display_product = cart_item.product.display_product
        item_total = display_product.price * Decimal(cart_item.quantity)
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
        line_total = display_product.price * Decimal(cart_item.quantity)
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
    context = {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
        'selected_category': selected_category,
        'category_choices': [choice[0] for choice in Product.CATEGORY_CHOICES],
    }
    return render(request, 'buyer_home.html',context)


@role_required('buyer')
def buyer_order_history(request):
    orders = Order.objects.filter(buyer=request.user).prefetch_related(
        'items__seller',
        'items__seller_shipping_address',
        'items__return_request',
    ).select_related(
        'buyer_shipping_address',
        'payment_method',
    ).order_by('-created_at')

    return render(request, 'buyer_order_history.html', {'orders': orders})


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

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            seller=seller,
                            seller_shipping_address=seller_shipping_address,
                            product_name=product.product_name,
                            unit_price=product.price,
                            quantity=row['quantity'],
                            line_total=round(row['item_total'], 2),
                        )

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

        