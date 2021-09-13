# CSV Permissions Module for Django

CSV-based permissions for Django.

Read [Motivation / Rationale](doc/background.md) for why this project exists.


## System Requirements

* Tested with django 2.2 and 3.2
  * Pull requests accepted for other versions, but at minimum we test against current LTS versions
* Python >=3.6 (no python 3.5 support)

## CSV Permissions

The `csv_permissions` model works as follows:

* Every user has a "user type" (the equivalent of `django.contrib.auth`'s `Group`)

* A CSV file that defines a permission matrix is used to define what permissions each `user_type` has

### Quick Start

In your django settings:

* Add `csv_permissions.permissions.CSVPermissionsBackend` to `AUTHENTICATION_BACKENDS` 
  
* set `CSV_PERMISSIONS_PATHS` which is an array/tuple of `str`/`pathlib.Path`
    pointing to the CSV files you want to use to define your permissions.
    Multiple files will be merged.
    The CSV files order does not matter: an error will be raised if the files are
    inconsistent.
    If a permission or user type is missing from one CSV file then this is not considered
    inconsistent, but a blank cell vs a filled cell is inconsistent.
  
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

# The horizontal column alignment is just for readability:
#  leading/trailing spaces will be stripped from each cell

Publisher, library,       add,               yes,       yes,   no,        no
Publisher, library,       view,              no,        all,   no,        no
Publisher, library,       change,            no,        all,   no,        no
Publisher, library,       delete,            no,        all,   no,        no

Book,      library,       add,               yes,       yes,   yes,       no
Book,      library,       view,              no,        all,   all,       no
Book,      library,       change,            no,        all,   all,       no
Book,      library,       delete,            no,        all,   all,       no

Loan,      library,       add,               yes,       yes,   yes,       yes
Loan,      library,       view,              no,        all,   all,       no
Loan,      library,       change,            no,        all,   all,       no
Loan,      library,       delete,            no,        all,   all,       no

# The model column can be blank. Note that the customer column here is also
# empty; see below for the difference between this and "no"

,          library,       report_outstanding,yes,      yes,   yes,
,          library,       report_popularity, yes,      yes,   yes,
```

The first 4 columns define the permission details.
These will be used to resolve the permission code name (see [Permission Names](#permission-names)). 

**Model** is used to resolve the permission name but is otherwise not used. There is no checks that objects passed to the `has_perm()` actually match the correct type.

**App** is used to resolve the permission name and model.

**Action** is an arbitrary identifier that is used to resolve the permission name.

**Is Global** whether the permission is global or per-object (see "Global Permission" section below).
    Right now you must provide a model if `Is Global` is false however this restriction may be
    relaxed in future. 

**Evaluators**

The next columns define permission "evaluators" for each [user type](#user-type)

Built-in evaluators are:

* `all` - user has permission for all objects. Will raise an error if an object is not passed to `has_perm()`
* `yes` - user has permission globally. Will raise an error if an object is passed to `has_perm()`.
* `no` -- user does not have permission (global or per-object)
* (empty cell) -- user permission is not defined.
    If another CSV file defines this user/permission pair then that will be used.
    If no CSV file defines this user/permission pair then the evaluator will be
    treated as `""` and by default the `resolve_empty_evaluator` will treat this as no permission granted. 

The distinction between `all` and `yes` is that `all` is a per-object
permission and `yes` is a [global permission](#global-permissions). 

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

By default putting anything other than a built-in evaluator in a CSV permissions file
will raise an error.

You add your own permission evaluators by defining "evaluator resolver"
functions which ingest a CSV cell value and returns a permission evaluator.
If the resolver does not recognise something it should return `None` and the
next resolver in the list will be called.

```python
# in settings.py
CSV_PERMISSIONS_RESOLVE_EVALUATORS = (
    # sanity check that non-global permissions have a model
    'csv_permissions.evaluators.resolve_validate_is_global_model',
    # custom validators (examples below)
    'my_app.evaluators.resolve_evaluators',
    # 'all'/'yes'/'no' 
    'csv_permissions.evaluators.resolve_all_evaluator',
    'csv_permissions.evaluators.resolve_yes_evaluator',
    'csv_permissions.evaluators.resolve_no_evaluator',
    # If you remove the empty evaluator then "" will fall through to the
    # remaining evaluator(s). This can be used in combination with
    # CSV_PERMISSIONS_STRICT to ensure that there are no blank cells in a CSV
    # file. Note that cells not present in any file due to different headers
    # still won't be processed.     
    'csv_permissions.evaluators.resolve_empty_evaluator',
    # normally if nothing matches an exception will be thrown however it 
    # can be more convenient (especially in early phases of development )
    # to issue a warning during CSV parsing, and then throw a
    # NotImplementedError() when the permission is evaluated
    'csv_permissions.evaluators.resolve_fallback_not_implemented_evaluator',
)

# if you don't have any customisations you can point to a list/tuple
# that is defined elsewhere; if you don't set it then this is the default setting:
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
        return evaluate_all_caps

    return None
```

* Note that evaluator names do not have to be static strings: you could implement
    something that understood `'all_caps:True'` and `'all_caps:False'` for example

### User Type

User Types are the `csv_permissions` equivalent of django's user Group.
A user has a single user type, and from that is granted the set of permissions
that this user type has in the CSV file.

The default user type is obtained from the user's `user_type` attribute.

If this doesn't exist or you need custom logic then you can set
`settings.CSV_PERMISSIONS_GET_USER_TYPE` to a function that takes a
user and returns the user type. If the function returns `None` or an empty
string then the user will have no permissions.

Custom example where the user type field is stored on a user Profile record
instead of the User record:

In `settings.py`:

```python
CSV_PERMISSIONS_GET_USER_TYPE = 'my_site.auth.get_user_type'
```

In `my_site/auth.py`:

```python
from typing import Optional

from django.contrib.auth import get_user_model

User = get_user_model()

def default_get_user_type(user: User) -> Optional[str]:
    try:
        return user.get_attached_profile().user_type
    except AttributeError:
        # user might be an AnonymousUser
        # user_type==None will be treated as a user with no permissions
        # if you do want to grant AnonymousUser selective permissions then return a placeholder string
        return None
```


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
    if model is None:
        return f"{app_config.label}-{action}"
    else:
        return f"{app_config.label}-{action}-{model._meta.model_name}"

```

Note the handling of the case where a permission has no model.
Examples of this can be seen in the `report_outstanding` and `report_popularity`
permissions in the [sample CSV file](#the-csv-file).


### Full Settings Reference

**`CSV_PERMISSIONS_GET_USER_TYPE`**

Optional. Function to get the user type from a user. Defaults to returning `user.user_type`.

[Details](#user-type)

**`CSV_PERMISSIONS_PATHS`** 

Required. List/tuple of CSV file names to use for permissions.

Alternately as a shorthand if you only have one CSV file you can instead set
`CSV_PERMISSIONS_PATH` to that single file.  

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

Note that due to pip/poetry/distutils issues you can't easily install dev versions directly from github with pip (works fine with poetry though)
* https://github.com/python-poetry/poetry/issues/761#issuecomment-521124268
    * proposed solution appears to work but actually installs the package as "UNKNOWN"
* https://github.com/python-poetry/poetry/issues/3153#issuecomment-727196619
    * dephell might have worked but there's no homebrew package & it's no longer maintained

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


