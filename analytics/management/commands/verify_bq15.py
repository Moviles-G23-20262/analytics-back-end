"""Proves that BQ15 is computed from the project's database and nothing else.

    python manage.py verify_bq15

It reads (SELECT only) the completed exchanges straight from the database with plain SQL, calls the
/analytics/average-ticket/ endpoint the dashboard uses, and compares both. Run it before and after
completing an exchange in the app: `completedSales` goes up by one and the averages move.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client

DIRECT_SQL = '''
SELECT m."condition", COUNT(e.id), SUM(e.price)
FROM "Exchange" e
JOIN "Material" m ON m.id = e."materialId"
WHERE e.status = 'COMPLETED'
GROUP BY m."condition"
'''

LAST_SALES_SQL = '''
SELECT m.title, m."condition", e.price, e."completedAt"
FROM "Exchange" e
JOIN "Material" m ON m.id = e."materialId"
WHERE e.status = 'COMPLETED'
ORDER BY e."completedAt" DESC NULLS LAST
LIMIT %s
'''


class Command(BaseCommand):
    help = 'Compares the BQ15 endpoint with a direct SQL query over the same database (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--last', type=int, default=5, help='How many of the latest completed sales to list.')

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(DIRECT_SQL)
            rows = cursor.fetchall()
            cursor.execute(LAST_SALES_SQL, [options['last']])
            latest = cursor.fetchall()

        sales = sum(r[1] for r in rows)
        total = sum(float(r[2]) for r in rows)
        expected = {
            'globalAverage': int(round(total / sales)) if sales else None,
            'completedSales': sales,
            'byCondition': {r[0]: int(round(float(r[2]) / r[1])) for r in rows if r[0]},
        }

        response = Client().get('/analytics/average-ticket/', HTTP_HOST='localhost')
        if response.status_code != 200:
            raise CommandError(f'The endpoint answered HTTP {response.status_code}')
        body = response.json()

        self.stdout.write('Direct SQL (Exchange JOIN Material, status = COMPLETED):')
        self.stdout.write(f'  {json.dumps(expected, sort_keys=True)}')
        self.stdout.write('Endpoint /analytics/average-ticket/:')
        self.stdout.write(f'  {json.dumps({k: body.get(k) for k in expected}, sort_keys=True)}  (computed at {body.get("generatedAt")})')
        self.stdout.write(f'Latest {len(latest)} completed sales:')
        for title, condition, price, completed_at in latest:
            self.stdout.write(f'  {completed_at}  {condition or "-":9}  {int(price):>10,} COP  {title}')

        mismatches = [k for k in expected if body.get(k) != expected[k]]
        if mismatches:
            raise CommandError(f'MISMATCH in {", ".join(mismatches)}: the endpoint does not match the database')
        self.stdout.write(self.style.SUCCESS(f'OK: the endpoint matches the database ({sales} completed sales).'))
