from django.apps import AppConfig


class SellersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sellers'
    label = 'products'
    verbose_name = 'Sellers'

    def ready(self):
        import sellers.signals