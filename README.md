# CSV Permissions Module for Django

CSV-based permissions for Django.

Read [Motivation / Rationale](doc/background.md) for why this project exists.


## System Requirements

* Tested with django 2.2 and 3.2
  * Pull requests accepted for other versions, but at minimum we test against current LTS versions
* Python >=3.6 (no python 3.5 support)

## CSV Permissions

The `csv_permissions` model works as follows:

* Every user is expected to have a `user_type` attribute (the equivalent of `django.contrib.auth`'s `Group`)

* A CSV file that defines a permission matrix is used to define what permissions each `user_type` has

### Installation

In your django settings:

* Add `csv_permissions` to `INSTALLED_APPS` (TODO: necessary?)

* Add `csv_permissions.permissions.CSVPermissionsBackend` to `AUTHENTICATION_BACKENDS` 
  
* Add a `CSV_PERMISSIONS_PATHS` which is an array/tuple of `str`/`pathlib.Path`
  pointing to the CSV files you want to use to define your permissions

#### Autoreload

`csv_permissions` caches the data read from the CSV permissions file on server start.
During development this means you have to manually restart the dev server when you make changes.
You can hook into django's autoreloader to automatically reload when the CSV file is changed:

In one of your [django app configs](https://docs.djangoproject.com/en/dev/ref/applications/#for-application-authors):

```python
def add_csv_permissions_watcher(sender, **kwargs):
    """In dev we want to reload if the csv permission file changes"""
    sender.extra_files.add(settings.CSV_PERMISSIONS_PATH)

class MySiteAppConfig(AppConfig):
    name = "my_site"
    verbose_name = "My Site"

    def ready(self):
        if settings.DEBUG:
            from django.utils.autoreload import autoreload_started

            autoreload_started.connect(add_csv_permissions_watcher)
```

If you're using [`runserver_plus`](https://django-extensions.readthedocs.io/en/latest/runserver_plus.html)
from `django-extensions` you can add your CSV files to
[`settings.RUNSERVER_PLUS_EXTRA_FILES`](https://django-extensions.readthedocs.io/en/latest/runserver_plus.html#configuration).   

  
### The CSV File

An example permission file:

```csv
Model,     App,           Action,            Is Global, admin, assistant, customer

# Comment lines and blank lines will be ignored

Publisher, library,       add,               no,        all,
Publisher, library,       view,              no,        all,
Publisher, library,       change,            no,        all,
Publisher, library,       delete,            no,        all,

Book,      library,       add,               no,        all,   all,
Book,      library,       view,              no,        all,   all,
Book,      library,       change,            no,        all,   all,
Book,      library,       delete,            no,        all,   all,

Loan,      library,       add,               no,        all,   all,       own,
Loan,      library,       view,              no,        all,   all,       own,
Loan,      library,       change,            no,        all,   all,
Loan,      library,       delete,            no,        all,   all,

# The model column can be blank:

,          library,       report_outstanding,yes,      yes,   yes,
,          library,       report_popularity, yes,      yes,   yes,
```

In the example above, a `User` whose `user_type=="admin"` would have the `add` permission
associated with the `library` app and 
`library.add_publisher` 

### Global Permissions

Unlike vanilla django permissions, by default `cvs_permissions` imposes a hard
distinction between global and per-object permissions.

* If you pass an object in a permission check against a permission with
    `Is Global==yes` in the CSV file then a `ValueError` will be raised.
* If you *don't* pass an object to a permission check against a permission with
  `Is Global==no` in the CSV file then a `ValueError` will be raised.

The `CSVPermissionsBackend` provides an `is_global_perm()` method to query
whether a permission is global or per-object:

```python
# example of querying whether a permission is global 
print(
    "foo-bar is a global permission"
    if CSVPermissionBackend().is_global("foo-bar")
    else "foo-bar is a per-object permission"
)
```

### Unrecognised Permissions

If `settings.CSV_PERMISSIONS_STRICT` is true then querying a permission
(or `user_type`) that is not in the CSV will raise a `LookupError`.

This is not set by default as it prevents the ability to use multiple
authentication backends for permission checks. If you are using `csv_permissions`
exclusively for permission checks then it can be helpful to catch typos.

### Permission names

By default `csv_permissions` will use the same permission name format as django: `<app label>.<action>_<model>`

You can optionally set `settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME` to the fully qualified name of a function to
resolve permission names to whatever pattern you want.

In `settings.py`:
```python
CSV_PERMISSIONS_RESOLVE_RULE_NAME = 'my_site.auth.resolve_rule_name'
```

In `my_site/auth.py`:
```python
from typing import Optional
from typing import Type

from django.apps import AppConfig
from django.apps import apps
from django.db.models import Model

def resolve_rule_name(app_config: AppConfig, model: Optional[Type[Model]], action: str, is_global: bool) -> str:
    # here's an implementation that is almost the same as django, but
    # uses - as a separator instead of _ and .
    #
    # we also need to handle with the case where a permission has no associated model
    if model is None:
        f"{app_config.label}-{action}"
    else:
        return f"{app_config.label}-{action}-{model._meta.model_name}"

```
