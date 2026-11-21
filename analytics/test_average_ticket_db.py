"""BQ15 end to end against a database: Exchange rows -> ORM query -> /analytics/average-ticket/.

The unit tests in test_average_ticket.py only check the arithmetic and the SQL text. These run the
real query over real rows, so a change in the rows has to show up in the endpoint:

    python manage.py test analytics.test_average_ticket_db --settings=config.settings_test
"""
import uuid
from decimal import Decimal

from django.db import connection
from django.test import Client, TestCase

# The class exists only under config.settings_test. With the normal settings (PostgreSQL) a
# TestCase would make the test runner create a test database ON THE PROJECT'S SERVER, even if the
# class were skipped, so it is not defined at all there.
if connection.vendor == 'sqlite':

    class AverageTicketEndpointTestCase(TestCase):

        @classmethod
        def setUpTestData(cls):
            with connection.cursor() as c:
                # Only the columns the BQ15 query reads; the real tables have more.
                c.execute('CREATE TABLE "Material" (id TEXT PRIMARY KEY, condition TEXT)')
                c.execute('CREATE TABLE "Exchange" (id TEXT PRIMARY KEY, "materialId" TEXT, price NUMERIC, status TEXT)')

        def sale(self, condition, price, status='COMPLETED'):
            material_id, exchange_id = str(uuid.uuid4()), str(uuid.uuid4())
            with connection.cursor() as c:
                c.execute('INSERT INTO "Material" (id, condition) VALUES (%s, %s)', [material_id, condition])
                c.execute(
                    'INSERT INTO "Exchange" (id, "materialId", price, status) VALUES (%s, %s, %s, %s)',
                    [exchange_id, material_id, str(Decimal(price)), status],
                )

        def get(self):
            response = Client().get('/analytics/average-ticket/')
            self.assertEqual(response.status_code, 200)
            return response

        def direct_sql(self):
            # The same question asked straight to the database, without Django's ORM.
            with connection.cursor() as c:
                c.execute(
                    'SELECT m.condition, COUNT(e.id), SUM(e.price) FROM "Exchange" e '
                    'JOIN "Material" m ON m.id = e."materialId" WHERE e.status = %s GROUP BY m.condition',
                    ['COMPLETED'],
                )
                rows = c.fetchall()
            sales = sum(r[1] for r in rows)
            total = sum(float(r[2]) for r in rows)
            return {
                'sales': sales,
                'global': int(round(total / sales)) if sales else None,
                'by_condition': {r[0]: int(round(float(r[2]) / r[1])) for r in rows if r[0]},
            }

        def test_without_completed_sales_it_says_so_instead_of_inventing_numbers(self):
            self.sale('NEW', '50000', status='PENDING')
            self.sale('GOOD', '20000', status='CANCELLED')

            body = self.get().json()

            self.assertEqual((body['globalAverage'], body['byCondition'], body['completedSales']), (None, {}, 0))

        def test_the_endpoint_matches_the_direct_sql_over_the_same_rows(self):
            self.sale('NEW', '60000')
            self.sale('NEW', '40000')
            self.sale('GOOD', '30000')
            self.sale('FAIR', '10000')
            self.sale('NEW', '999999', status='PENDING')  # not a sale yet
            self.sale('GOOD', '888888', status='CANCELLED')  # never happened

            body = self.get().json()
            expected = self.direct_sql()

            self.assertEqual(body['completedSales'], expected['sales'])
            self.assertEqual(body['completedSales'], 4)
            self.assertEqual(body['globalAverage'], expected['global'])
            self.assertEqual(body['globalAverage'], 35000)  # (60 + 40 + 30 + 10) / 4
            self.assertEqual(body['byCondition'], expected['by_condition'])
            self.assertEqual(body['byCondition'], {'NEW': 50000, 'GOOD': 30000, 'FAIR': 10000})

        def test_completing_one_more_exchange_changes_the_answer(self):
            self.sale('NEW', '60000')
            before = self.get().json()
            self.assertEqual((before['globalAverage'], before['completedSales']), (60000, 1))

            self.sale('FAIR', '20000')  # an exchange the app just completed
            after = self.get().json()

            self.assertEqual((after['globalAverage'], after['completedSales']), (40000, 2))
            self.assertEqual(after['byCondition'], {'NEW': 60000, 'FAIR': 20000})

        def test_the_answer_is_never_cached_and_says_when_it_was_computed(self):
            response = self.get()

            self.assertIn('max-age=0', response['Cache-Control'])
            self.assertIn('no-cache', response['Cache-Control'])
            self.assertTrue(response.json()['generatedAt'])
