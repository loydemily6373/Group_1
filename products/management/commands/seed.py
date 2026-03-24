from django.core.management.base import BaseCommand, CommandError

from products.seeding import clear_products, reset_products, seed_products


class Command(BaseCommand):
    help = 'Seed, clear, or reset the product test data.'

    def add_arguments(self, parser):
        # Match the standalone script behavior so both entry points stay consistent.
        parser.add_argument(
            'action',
            nargs='?',
            default='reset',
            choices=['seed', 'clear', 'reset'],
            help='Choose whether to seed, clear, or reset the product data.',
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'clear':
            deleted_count = clear_products()
            self.stdout.write(self.style.SUCCESS(
                f'Cleared existing product data. Deleted {deleted_count} database rows.'
            ))
        elif action == 'seed':
            seeded_count = seed_products()
            self.stdout.write(self.style.SUCCESS(
                f'Seeded {seeded_count} products into the database.'
            ))
        elif action == 'reset':
            deleted_count, seeded_count = reset_products()
            self.stdout.write(self.style.SUCCESS(
                f'Cleared existing product data. Deleted {deleted_count} database rows.'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Seeded {seeded_count} products into the database.'
            ))
        else:
            raise CommandError('Unsupported action. Use seed, clear, or reset.')