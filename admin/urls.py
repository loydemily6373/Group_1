from django.urls import path
from . import views

urlpatterns = [
    # for product requests page
    path('admin-product-requests/', views.product_requests, name='product_requests'),
    path('approve-product/<int:request_id>/', views.approve_product, name='approve_product'),
    path('reject-product/<int:request_id>/', views.reject_product, name='reject_product'),

    # for seller requests page
    path('admin-seller-requests/', views.seller_requests, name='seller_requests'),
    path('approve-seller/<int:request_id>/', views.approve_seller, name='approve_seller'),
    path('reject-seller/<int:request_id>/', views.reject_seller, name='reject_seller'),

    # for review moderation
    path('reviews/', views.review_moderation, name='review_moderation'),
    path('reviews/<int:review_id>/approve/', views.approve_review, name='approve_review'),
    path('reviews/<int:review_id>/reject/', views.reject_review, name='reject_review'),
    path('reviews/<int:review_id>/delete/', views.delete_review, name='delete_review'),
]