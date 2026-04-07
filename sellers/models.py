import uuid

from django.db import models
from django.utils import timezone
from .validators import validate_image_file


# Create your models here.
def upload_icon_to(_, filename): 
    #Leaving filenames as they are can be a risk, lets just rename them.
    ext = filename.rsplit('.', 1)[-1].lower()
    return f"status_icons/{uuid.uuid4().hex}.{ext}"


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
    image = models.ImageField(upload_to=upload_icon_to, validators=[validate_image_file], blank=True, null=True)
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


class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Each purchased item can have at most one return request, which keeps buyer and seller history aligned.
    order_item = models.OneToOneField('buyers.OrderItem', on_delete=models.CASCADE, related_name='return_request')
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Return for {self.order_item.order.order_number} - {self.order_item.product_name}"

