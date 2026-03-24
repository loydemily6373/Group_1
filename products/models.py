from django.db import models
from django.utils import timezone

# Create your models here.


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('T-Shirt', 'T-Shirt'),
        ('Shirt', 'Shirt'),
        ('Blouse', 'Blouse'),
        ('Sweater', 'Sweater'),
        ('Hoodie', 'Hoodie'),
        ('Jeans', 'Jeans'),
        ('Pants', 'Pants'),
        ('Skirt', 'Skirt'),
        ('Shorts', 'Shorts'),
        ('Leggings', 'Leggings'),
        ('Dress', 'Dress'),
        ('Jacket', 'Jacket'),
        ('Swimwear', 'Swimwear'),
        ('Sleepwear', 'Sleepwear'),
        ('Shoes', 'Shoes'),
        ('Accessories', 'Accessories'),
    ]

    seller_id = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    # When a product is soft deleted, related pages can follow this pointer to a replacement product.
    redirect_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='redirected_products')
    product_name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField()
    description = models.TextField()
    active= models.BooleanField(null=True, blank=True)

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    @property
    def display_product(self):
        # Return the replacement product when this row has been soft deleted and a redirect target exists.
        if self.deleted_at and self.redirect_to_id:
            return self.redirect_to
        return self

    def soft_delete(self, redirect_to=None):
        # Keep the row for historical references, but hide it from active browsing.
        self.redirect_to = redirect_to
        self.active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['redirect_to', 'active', 'deleted_at'])

    def __str__(self):
        return self.product_name


