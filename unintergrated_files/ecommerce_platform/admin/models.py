from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=200)
    seller = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    approved = models.BooleanField(null=True, blank=True)

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.name

class SellerRequest(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    approved = models.BooleanField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
