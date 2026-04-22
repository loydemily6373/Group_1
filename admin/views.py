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


@role_required('admin')
def review_moderation(request):
    """View all reviews pending approval and approved reviews."""
    from buyers.models import Review
    
    pending_reviews = Review.objects.filter(status='pending').select_related('buyer', 'product').order_by('-created_at')
    approved_reviews = Review.objects.filter(status='approved').select_related('buyer', 'product').order_by('-created_at')[:50]
    
    context = {
        'pending_reviews': pending_reviews,
        'approved_reviews': approved_reviews,
        'pending_count': pending_reviews.count(),
    }
    return render(request, 'admin_review_moderation.html', context)


@role_required('admin')
def approve_review(request, review_id):
    """Approve a review."""
    from buyers.models import Review
    
    review = get_object_or_404(Review, id=review_id)
    review.status = 'approved'
    review.save(update_fields=['status'])
    
    from django.contrib import messages
    messages.success(request, f'Review by {review.buyer.username} has been approved.')
    return redirect('review_moderation')


@role_required('admin')
def reject_review(request, review_id):
    """Reject a review."""
    from buyers.models import Review
    
    review = get_object_or_404(Review, id=review_id)
    review.status = 'rejected'
    review.save(update_fields=['status'])
    
    from django.contrib import messages
    messages.success(request, f'Review by {review.buyer.username} has been rejected.')
    return redirect('review_moderation')


@role_required('admin')
def delete_review(request, review_id):
    """Delete a review."""
    from buyers.models import Review
    from django.contrib import messages
    
    review = get_object_or_404(Review, id=review_id)
    buyer_name = review.buyer.username
    product_name = review.product.product_name
    review.delete()
    
    messages.success(request, f'Review by {buyer_name} for {product_name} has been deleted.')
    return redirect('review_moderation')
