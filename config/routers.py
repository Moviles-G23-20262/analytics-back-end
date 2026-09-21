class ReadOnlyRouter:
    """
    Disallows write operations and database migrations on all models.
    """
    def db_for_read(self, model, **hints):
        return 'default'

    def db_for_write(self, model, **hints):
        raise PermissionError("This Django backend is read-only.")

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return False