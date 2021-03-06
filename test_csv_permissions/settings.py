from distutils.util import strtobool as _strtobool
import hashlib as _hashlib
import os as _os
from pathlib import Path as _Path
import random as _random
import warnings as _warnings

is_ci = _os.environ.get('CI_SERVER', 'no') == 'yes'

BASE_DIR = _Path(__file__).parent

# Select DB engine

if _strtobool(_os.environ.get('TOX', '0')):
    _engine = _os.environ['VIRTUAL_ENV'].split('-')[-1]
    assert _engine
    _engine = 'django.db.backends.' + _engine
elif _os.environ.get('PGDATABASE'):
    _engine = 'django.db.backends.postgresql'
else:
    _engine = 'django.db.backends.postgresql'

# DB default settings
_db_vars = {
    'NAME': ('DB_NAME', 'csv_permissions'),
    'HOST': ('DB_HOST', 'localhost'),
    'PORT': ('DB_PORT', '5432' if _engine == 'django.db.backends.postgresql' else '3306'),
    'USER': ('DB_USER', _os.environ.get('USER', '') if _engine == 'django.db.backends.postgresql' else None),
    'PASSWORD': ('DB_PASSWORD', None),
}

# override settings based on env vars
_db_vars = {var: _os.environ.get(env_var, default) for var, (env_var, default) in _db_vars.items()}
# remove blank settings (no-password is not treated the same as '')
_db_vars = {key: value for key, value in _db_vars.items() if value}

_db_vars['ENGINE'] = _engine

if _engine == 'django.db.backends.mysql':
    # extra mysql options
    _db_vars['OPTIONS'] = {
        'init_command': 'SET default_storage_engine=INNODB',
        'charset': 'utf8mb4',
    }
    if not is_ci:
        _db_vars['OPTIONS']['read_default_file'] = '~/.my.cnf'


# Django connects via the live DB in order to create/drop the test DB
# If the live DB doesn't exist then it bails out before even trying to
# create the test DB, so this doesn't really work
# if is_ci:
#     db_vars['TEST'] = {
#         'NAME': db_vars['NAME'],
#     }

DATABASES = {'default': _db_vars}

INSTALLED_APPS = (
    'csv_permissions',
    'authtools',

    'test_csv_permissions',

    'django_db_constraints',

    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
)

AUTH_USER_MODEL = 'authtools.User'

AUTHENTICATION_BACKENDS = [
    "csv_permissions.permissions.CSVPermissionsBackend",
    'django.contrib.auth.backends.ModelBackend',
]

MIDDLEWARE = ()

TEMPLATE_DIRS = (
    # os.path.join(BASE_DIR, 'compat/tests/templates/')
)

TEMPLATES = (
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': TEMPLATE_DIRS,
    },
)

STATIC_ROOT = _Path(BASE_DIR, 'static')

SECRET_KEY = _hashlib.sha256(str(_random.SystemRandom().getrandbits(256)).encode('ascii')).hexdigest()

# -------------------------------------
# Test case performance
PASSWORD_HASHERS = (
        #'django_plainpasswordhasher.PlainPasswordHasher', # very fast but extremely insecure
        "django.contrib.auth.hashers.SHA1PasswordHasher",  # fast but insecure
    )

DATABASES["default"]["TEST"] = {
    # Test case serializion is only used for emulating rollbacks in test cases if the DB doesn't support it.
    # Both postgres & mysql+innodb support real transactions so this does nothing except slow things down.
    # Additionally, if you override _default_manager to have extra restrictions then this can cause issues
    #   since BaseDatabaseCreation.serialize_db_to_string() uses _default_manager and not _base_manager
    "SERIALIZE": False
}

# -------------------------------------
# Custom settings
QUERY_COUNT_WARNING_THRESHOLD = 40

_warnings.simplefilter('always')
