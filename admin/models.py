from django.db import models


class ProductApprovalRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('create', 'Create'),
        ('edit', 'Edit'),
    ]

    # Store the real product being reviewed so an approval decision can update that shared row.
    product_id = models.ForeignKey('products.Product', on_delete=models.CASCADE)
    original_product_id = models.ForeignKey('products.Product', null=True, blank=True, on_delete=models.SET_NULL, related_name='replacement_approval_requests')
    name = models.CharField(max_length=200)
    seller_ID = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    seller_First_Name = models.CharField(max_length=100)
    approved = models.BooleanField(null=True, blank=True)
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES, default='create')

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    @classmethod
    def submit_product(cls, product, seller, original_product=None):
        # Reuse the same pending request for a product when possible, but preserve edit/create context.
        approval_request, _ = cls.objects.update_or_create(
            product_id=product,
            defaults={
                'original_product_id': original_product,
                'seller_ID': seller,
                'seller_First_Name': seller.first_name,
                'approved': None,
                'request_type': 'edit' if original_product else 'create',
                'status': 'pending',
            },
        )
        return approval_request

    def save(self, *args, **kwargs):
        # Keep the request snapshot fields in sync with the linked product and seller records.
        if self.product_id_id:
            self.name = self.product_id.product_name
        if self.seller_ID_id:
            self.seller_First_Name = self.seller_ID.first_name
        super().save(*args, **kwargs)

    def apply_decision(self, approved):
        # Persist the admin decision on both the request row and the real marketplace product.
        self.approved = approved
        self.status = 'approved' if approved else 'rejected'

        # The product schema now uses active/status, so admin decisions update those fields directly.
        self.product_id.active = approved
        self.product_id.status = self.status
        self.product_id.save(update_fields=['active', 'status'])

        # Approving an edit replaces the original listing with the reviewed product while preserving history.
        if approved and self.request_type == 'edit' and self.original_product_id_id:
            self.original_product_id.soft_delete(redirect_to=self.product_id)

        self.save(update_fields=['name', 'seller_First_Name', 'approved', 'request_type', 'status'])

    def __str__(self):
        return self.name


class SellerApprovalRequest(models.Model):
    # Link the approval row to the real user account created during signup.
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='seller_approval_requests')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    approved = models.BooleanField(null=True, blank=True)

    @classmethod
    def submit_user(cls, user):
        # Keep one pending seller approval request per seller account.
        request, _ = cls.objects.update_or_create(
            user=user,
            defaults={
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'approved': None,
            },
        )
        return request

    def apply_decision(self, approved):
        # Approving a seller account activates the linked user so they can log in and access seller pages.
        self.approved = approved
        if self.user_id:
            self.user.is_active = approved
            self.user.save(update_fields=['is_active'])
        self.save(update_fields=['approved'])

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
