from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Initialize PgVector extension for PostgreSQL'

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
            self.stdout.write(self.style.SUCCESS('PgVector extension installed successfully'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'PgVector installation skipped (likely SQLite or no permission): {e}'
            ))
