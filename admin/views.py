from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import role_required

from .models import ProductApprovalRequest, SellerApprovalRequest


# for product request page
@role_required('admin')
def product_requests(request):
    # Review the dedicated approval rows so admin sees pending decisions rather than every product row.
    product_requests = ProductApprovalRequest.objects.select_related(
        'product_id',
        'product_id__redirect_to',
        'seller_ID',
        'original_product_id',
        'original_product_id__redirect_to',
    ).order_by('name')
    return render(request, 'admin_product_request.html', 
                  {'product_requests': product_requests})

# approve/reject logic
@role_required('admin')
def approve_product(request, request_id):
    approval_request = get_object_or_404(ProductApprovalRequest, id=request_id)
    approval_request.apply_decision(True)
    return redirect('product_requests')

@role_required('admin')
def reject_product(request, request_id):
    approval_request = get_object_or_404(ProductApprovalRequest, id=request_id)
    approval_request.apply_decision(False)
    return redirect('product_requests')


# for seller request page
@role_required('admin')
def seller_requests(request):
    requests = SellerApprovalRequest.objects.select_related('user').all()
    return render(request, 'admin_seller_request.html', 
                  {'requests': requests})

# approve/reject logic
@role_required('admin')
def approve_seller(request, request_id):
    req = get_object_or_404(SellerApprovalRequest, id=request_id)
    req.apply_decision(True)
    return redirect('seller_requests')

@role_required('admin')
def reject_seller(request, request_id):
    req = get_object_or_404(SellerApprovalRequest, id=request_id)
    req.apply_decision(False)
    return redirect('seller_requests')
