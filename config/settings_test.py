"""Settings for tests that run the real ORM queries against a throwaway SQLite database.

    python manage.py test analytics.test_average_ticket_db --settings=config.settings_test

The normal settings point at the project's single PostgreSQL database, which a test must never
touch; here the models read from an in-memory database instead.
"""
from .settings import *  # noqa: F401,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DATABASE_ROUTERS = []
