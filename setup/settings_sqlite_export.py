"""
Settings só para exportar dados do SQLite de produção.

1) Copia o db.sqlite3 para data/exports/db_work.sqlite3
2) python manage.py migrate --settings=setup.settings_sqlite_export
3) python manage.py dumpdata --settings=setup.settings_sqlite_export ...
"""
from setup.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'exports' / 'db_work.sqlite3',
    }
}

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
