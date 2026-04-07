from django.shortcuts import render, redirect
from .models import Product
from .models import SellerRequest


# for product request page
def product_requests(request):
    products = Product.objects.all()
    return render(request, 'admin_product_request.html', 
                  {'products': products})

# approve/reject logic
def approve_product(request, product_id):
    product = Product.objects.get(id=product_id)
    product.approved = True
    product.save()
    return redirect('product_requests')

def reject_product(request, product_id):
    product = Product.objects.get(id=product_id)
    product.approved = False
    product.save()
    return redirect('product_requests')


# for seller request page
def seller_requests(request):
    requests = SellerRequest.objects.all()
    return render(request, 'admin_seller_request.html', 
                  {'requests': requests})

# approve/reject logic
def approve_seller(request, request_id):
    req = SellerRequest.objects.get(id=request_id)
    req.approved = True
    req.save()
    return redirect('seller_requests')

def reject_seller(request, request_id):
    req = SellerRequest.objects.get(id=request_id)
    req.approved = False
    req.save()
    return redirect('seller_requests')
