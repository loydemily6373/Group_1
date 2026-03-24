import os
import sys


# Point standalone script execution at this Django project's settings module.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from products.seeding import clear_products, reset_products, seed_products


def _print_clear_products():
    # Print a friendly message for standalone script usage.
    deleted_count = clear_products()
    print(f'Cleared existing product data. Deleted {deleted_count} database rows.')


def _print_seed_products():
    # Print a friendly message for standalone script usage.
    seeded_count = seed_products()
    print(f'Seeded {seeded_count} products into the database.')


def _print_reset_products():
    # Reset first so repeated test runs always start from the same data.
    deleted_count, seeded_count = reset_products()
    print(f'Cleared existing product data. Deleted {deleted_count} database rows.')
    print(f'Seeded {seeded_count} products into the database.')


def main():
    # Support explicit commands so you can either wipe data, seed data, or do both.
    command = sys.argv[1].lower() if len(sys.argv) > 1 else 'reset'

    if command == 'clear':
        _print_clear_products()
    elif command == 'seed':
        _print_seed_products()
    elif command == 'reset':
        _print_reset_products()
    else:
        print("Usage: python seed.py [seed|clear|reset]")
        sys.exit(1)


if __name__ == '__main__':
    main()