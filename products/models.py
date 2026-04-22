from sellers.models import *

from django.utils import timezone

class Product(models.Model):

    discount_percent = models.FloatField(null=True, blank=True)
    discount_start_date = models.DateTimeField(null=True, blank=True)
    discount_end = models.DateTimeField(null=True, blank=True)


    def is_discount_active(self):
        if self.discount_percent and self.discount_start_date and self.discount_end_date:
            now = timezone.now()
            return self.discount_start_date <= now <= self.discount_end_date
        return False

    def get_discounted_price(self):
        if self.is_discount_active():
            return self.price * (1 - self.discount_percent / 100)
        return self.price
    
    def __str__(self):
        return self.name

    
