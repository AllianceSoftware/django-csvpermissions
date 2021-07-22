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

### Quick Start

In your django settings:

* Add `csv_permissions.permissions.CSVPermissionsBackend` to `AUTHENTICATION_BACKENDS` 
  
* set `CSV_PERMISSIONS_PATHS` which is an array/tuple of `str`/`pathlib.Path`
  pointing to the CSV files you want to use to define your permissions
  
* Set `CSV_PERMISSIONS_RESOLVE_EVALUATORS` to `"csv_permissions.evaluators.default_resolve_evaluators"`

#### Autoreload

`csv_permissions` caches the data read from the CSV permissions file on server start.
During development this means you have to manually restart the dev server when you make changes.
You can hook into django's autoreloader to automatically reload when the CSV file is changed:

In one of your [django app configs](https://docs.djangoproject.com/en/dev/ref/applications/#for-application-authors):

```python
def add_csv_permissions_watcher(sender: django.utils.autoreload.StatReloader, **kwargs):
    """In dev we want to reload if the csv permission file changes"""
    sender.extra_files.add(settings.CSV_PERMISSIONS_PATHS)

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

Publisher, library,       add,               yes,       yes,
Publisher, library,       view,              no,        all,
Publisher, library,       change,            no,        all,
Publisher, library,       delete,            no,        all,

Book,      library,       add,               yes,       yes,   yes,
Book,      library,       view,              no,        all,   all,
Book,      library,       change,            no,        all,   all,
Book,      library,       delete,            no,        all,   all,

Loan,      library,       add,               yes,       yes,   yes,       yes,
Loan,      library,       view,              no,        all,   all,       own,
Loan,      library,       change,            no,        all,   all,
Loan,      library,       delete,            no,        all,   all,

# The model column can be blank:

,          library,       report_outstanding,yes,      yes,   yes,
,          library,       report_popularity, yes,      yes,   yes,
```

The first 4 columns define the permission details:

**Model** is used to resolve the permission name but is otherwise not used. There is no checks that objects passed to the `has_perm()` actually match the correct type.

**App** is used to resolve the permission name and model.

**Action** is an arbitrary identifier that is used to resolve the permission name.

**Is Global** whether the permission is global or per-object (see "Global Permission" section below)

**Evaluators**

The next columns define permission "evaluators".

Built-in evaluators are:

* `all` - user has permission for all objects. Will raise an error  if an object is not passed to `has_perm()`
* `yes` - user has permission globally. Will raise an error if an object is passed to `has_perm()`.
* (empty cell) -- user does not have permission (global or per-object) 


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

### Custom Evaluators

By default putting other than a built-in evaluator in a CSV permissions file
will raise an error.

You add your own permission evaluators by defining "evaluator resolver"
functions which ingest a CSV cell value and returns a permission evaluator.
If the resolver does not recognise something it should return `None` and the
next resolver in the list will be called.

```python
# in settings.py
CSV_PERMISSIONS_RESOLVE_EVALUATORS = (
    # sanity checks
    'csv_permissions.evaluators.resolve_validation_evaluator',
    # custom validators (examples below)
    'my_app.evaluators.resolve_evaluators',
    # 'all'/'yes'/'' 
    'csv_permissions.evaluators.resolve_all_evaluator',
    'csv_permissions.evaluators.resolve_yes_evaluator',
    'csv_permissions.evaluators.resolve_empty_evaluator',
    # normally if nothing matches an exception will be thrown however it 
    # can be more convenient (especially in early phases of development )
    # to issue a warning during CSV parsing, and then throw a
    # NotImplementedError() when the permission is evaluated
    'csv_permissions.evaluators.resolve_fallback_not_implemented_evaluator',
)

# if you don't have any customisations you can point to a list/tuple
# that is defined elsewhere; this is a basic set:
#CSV_PERMISSIONS_RESOLVE_EVALUATORS = "csv_permissions.evaluators.default_resolve_evaluators"

# for compatibility with csv_permissions 0.1.0
#CSV_PERMISSIONS_RESOLVE_EVALUATORS = "csv_permissions.legacy.resolve_evaluators"

```

The following code will define some custom evaluators: 
- `'if_monday'` grants all access on mondays.
- `'all_caps'` grants access to all objects that have a `name` field containing
    all uppercase.

In `my_app.evaluators`:
```python
import datetime
from typing import Optional

from csv_permissions.types import Evaluator
from csv_permissions.types import UnresolvedEvaluator


def evaluate_if_monday(user, obj=None):
    return datetime.datetime.today().weekday() == 0

def evaluate_all_caps(user, obj=None):
    if obj is None:
        raise ValueError("'all_caps' cannot be used as a global permission.")
    
    try:
        return obj.name.isupper()
    except AttributeError:
        return False
     
def resolve_evaluators(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if details.evaluator_name == "if_monday":
        return evaluate_if_monday

    if details.evaluator_name == "all_caps":
        if details.is_global != False:
            raise ValueError("'all_caps' cannot be used as a global permission.")
        return evaluate_if_monday

    return None
```

* Note that evaluator names do not have to be static strings: you could implement
    something that understood `'all_caps:True'` and `'all_caps:False'` for example

### Unrecognised Permissions

If `settings.CSV_PERMISSIONS_STRICT` is true then querying a permission
(or `user_type`) that is not in the CSV will raise a `LookupError`.

This is not set by default as it prevents the ability to use multiple
authentication backends for permission checks. If you are using `csv_permissions`
exclusively for permission checks then it can be helpful to catch typos.

### Permission Names

By default `csv_permissions` will use the same permission name format as django: `<app label>.<action>_<model>`

You can optionally set `settings.CSV_PERMISSIONS_RESOLVE_PERM_NAME` to the fully qualified name of a function to
resolve permission names to whatever pattern you want.

In `settings.py`:
```python
CSV_PERMISSIONS_RESOLVE_PERM_NAME = 'my_site.auth.resolve_perm_name'
```

In `my_site/auth.py`:
```python
from typing import Optional
from typing import Type

from django.apps import AppConfig
from django.db.models import Model

def resolve_perm_name(app_config: AppConfig, model: Optional[Type[Model]], action: str, is_global: bool) -> str:
    # here's an implementation that is almost the same as django, but
    # uses - as a separator instead of _ and .
    #
    # we also need to handle with the case where a permission has no associated model
    if model is None:
        f"{app_config.label}-{action}"
    else:
        return f"{app_config.label}-{action}-{model._meta.model_name}"

```


### Full Settings Reference

**`CSV_PERMISSIONS_PATHS`**

Required. List/tuple of CSV file names to use for permissions.

**`CSV_PERMISSIONS_RESOLVE_EVALUATORS`**

Required. A list/tuple of functions to resolve evaluators, or a string
that will be resolved to a module attribute that is expected to contain a
list/tuple of functions to resolve evaluators.

[Details](#custom-evaluators)

**`CSV_PERMISSIONS_RESOLVE_PERM_NAME`**

Optional. string or function. Defaults to `'csv_permissions.permissions.default_resolve_perm_name'`.

[Details](#permission-names)

**`CSV_PERMISSIONS_STRICT`**

Optional. boolean. Defaults to `False`.

Will cause the CSVPermissionsBackend to throw an error if you try to query an
unrecognised permission or user type.

[Details](#unrecognised-permissions)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## Development

### Release Process

#### Poetry Config
* Add test repository
    * `poetry config repositories.testpypi https://test.pypi.org/legacy/`
    * Generate an account API token at https://test.pypi.org/manage/account/token/
    * `poetry config pypi-token.testpypi ${TOKEN}`
        * On macs this will be stored in the `login` keychain at `poetry-repository-testpypi`
* Main pypi repository
    * Generate an account API token at https://pypi.org/manage/account/token/
    * `poetry config pypi-token.pypi ${TOKEN}`
        * On macs this will be stored in the `login` keychain at `poetry-repository-pypi`

#### Publishing a New Release
    * Update CHANGELOG.md with details of changes and new version
    * Run `bin/build.py`. This will extract version from CHANGELOG.md, bump version in `pyproject.toml` and generate a build for publishing
    * Tag with new version and update the version branch:
        * `ver=$( poetry version --short ) && echo "Version: $ver"`
        * `git tag v/$ver`
        * `git push --tags`
    * To publish to test.pypi.org
        * `poetry publish --repository testpypi`
    * To publish to pypi.org
        * `poetry publish`


