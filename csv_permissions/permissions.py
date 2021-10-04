import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Type
from typing import Union
import warnings

from django.apps import AppConfig
from django.apps import apps
from django.conf import settings
import django.contrib.auth
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model
from django.http import HttpRequest
from django.utils.module_loading import import_string

from .types import Evaluator
from .types import PermName
from .types import ResolveEvaluatorFunc
from .types import ResolvePermNameFunc
from .types import UnresolvedEvaluator
from .types import UserType


def default_resolve_perm_name(
    app_config: AppConfig, model: Type[Model], action: str, is_global: bool
) -> str:
    if model:
        default_codename = django.contrib.auth.get_permission_codename(action, model._meta)
        permission_name = f"{app_config.label}.{default_codename}"
    else:
        permission_name = f"{app_config.label}.{action}"
    return permission_name


def default_get_user_type(user: Model) -> Optional[str]:
    # note that AnonymousUser won't have a user_type so we need to deal with that gracefully
    return getattr(user, "user_type", None)


def _parse_csv(
    file_path: Path,
    resolve_permission_name_func: ResolvePermNameFunc,
) -> Tuple[
    Dict[PermName, bool],
    Dict[PermName, Dict[UserType, UnresolvedEvaluator]],
    Iterable[str],
]:
    """
    Parses the CSV of user_type permissions returns data for further processing.

    See README.md for the CSV file format

    :return: A tuple of three elements:
        - A dict mapping permission name to bool of whether that permission is global or not
        - A dict mapping a permission to a dict of user_types to partially resolved permission details:
            permission_name: {
                user_type1: UnresolvedEvaluator,
                ...
                user_typeN: UnresolvedEvaluator,
            }
        - A list of user types
    """

    with open(file_path, "r") as csv_file:
        reader = csv.reader(csv_file, skipinitialspace=True)

        # get first row of headers
        fieldnames = next(reader)
        fieldnames = [x.strip() for x in fieldnames]

        prelim_headers = ["Model", "App", "Action", "Is Global"]
        prelim_header_count = len(prelim_headers)

        if fieldnames[:prelim_header_count] != prelim_headers:
            raise ValueError(f"Invalid csv_permissions CSV column headers found in {file_path}")

        user_type_headers = fieldnames[prelim_header_count:]

        nonempty_user_type_headers = [user_type for user_type in user_type_headers if user_type != ""]
        if len(set(nonempty_user_type_headers)) != len(nonempty_user_type_headers):
            duplicates = [x for x in nonempty_user_type_headers if nonempty_user_type_headers.count(x) >= 2]
            raise ValueError(f"Duplicate csv_permissions CSV column header ({duplicates[0]}) found in {file_path}")

        if len(nonempty_user_type_headers) == 0:
            raise ValueError(f"Missing user_type headers in {file_path}")

        perm_is_global = {}
        perm_user_type_unresolved: Dict[PermName, Dict[UserType, UnresolvedEvaluator]] = {}

        # We can't just count the number of permissions read because we don't consider
        # a file with commented out lines to be empty so keep track with a flag
        was_empty = True

        for line_number, row in enumerate(reader):
            row = [cell.strip() for cell in row]

            was_empty = False
            if all(x == "" for x in row):
                # ignore completely empty rows
                continue

            if any(row[0].strip().startswith(comment_prefix) for comment_prefix in ("//", "#", ';')):
                # Ignore lines beginning with comment chars
                continue

            if len(row) < prelim_header_count:
                raise ValueError(f"Incomplete line {line_number} in {csv_file}")

            # note that model capitalisation may differ to model._meta.model_name
            model_name_orig, app_label, action, is_global = row[:prelim_header_count]

            app_config = apps.get_app_config(app_label)
            model = app_config.get_model(model_name_orig) if model_name_orig else None

            if is_global == "yes":
                is_global = True
            elif is_global == "no":
                is_global = False
            else:
                raise ValueError("Invalid value for Is Global: should be 'yes' or 'no'.")

            permission = resolve_permission_name_func(app_config, model, action, is_global)

            if permission not in perm_is_global:
                perm_is_global[permission] = is_global
                perm_user_type_unresolved[permission] = {}

            for i, user_type in enumerate(user_type_headers):
                try:
                    evaluator_name = row[prelim_header_count + i]
                except IndexError:
                    continue

                if user_type == "":
                    # if a column has an empty user type then that's allowed but only if the entire column is empty
                    if evaluator_name != "":
                        raise ValueError(f"Columns with an empty user_type must be completely empty")
                else:
                    perm_user_type_unresolved[permission][user_type] = UnresolvedEvaluator(
                        app_config=app_config,
                        model=model,
                        is_global=is_global,
                        permission=permission,
                        action=action,
                        user_type=user_type,
                        evaluator_name=evaluator_name,
                        source_csv=file_path,
                    )

        if was_empty:
            raise ValueError("Empty permissions file")

        return perm_is_global, perm_user_type_unresolved, nonempty_user_type_headers


# should be at least as large as the number of CSV files we load. This gets called by every has_perm() so must be cached
@lru_cache(maxsize=32)
def _resolve_functions(
    file_paths: Iterable[Path],
    resolve_permission_name: Optional[str],
    resolve_evaluators: Iterable[Union[str, ResolveEvaluatorFunc]],
) -> Tuple[
    Dict[PermName, Dict[UserType, Evaluator]],
    Dict[PermName, bool],
    Set[str],
    Set[str]
]:
    """
    :param file_paths: Path to the CSV files to read.
    :resolve_permission_name: the settings.CSV_PERMISSIONS_RESOLVE_PERM_NAME setting.
    :resolve_evaluators: the settings.CSV_PERMISSIONS_RESOLVE_EVALUATORS setting.
    :return: A tuple of:
            - dictionary mapping the permissions for each UserType to a function determining if the user has access.
            - dictionary mapping the permission to a boolean indicating whether the permission is object level or global level.
            - set of user types
            - set of permissions
    """

    if resolve_permission_name is None:
        resolve_permission_name = default_resolve_perm_name
    else:
        resolve_permission_name = import_string(resolve_permission_name)

    resolve_evaluators = tuple(
        import_string(resolve_evaluator) if isinstance(resolve_evaluator, str) else resolve_evaluator
        for resolve_evaluator
        in resolve_evaluators
    )

    permission_is_global: Dict[PermName, bool] = {}
    permission_is_global_source_csv: Dict[PermName, Path] = {}

    known_user_types: Set[UserType] = set()
    known_perms: Set[PermName] = set()

    permission_to_user_type_to_unresolved: Dict[PermName, Dict[UserType, UnresolvedEvaluator]] = {}

    for file_path in file_paths:
        file_permission_is_global, new_permission_to_user_type_to_unresolved, user_types = \
            _parse_csv(file_path, resolve_permission_name)

        # merge global list of known user types/permissions
        known_user_types.update(set(user_types))
        known_perms.update(set(file_permission_is_global.keys()))

        # merge is_global settings
        for permission, is_global in file_permission_is_global.items():
            if permission in permission_is_global and permission_is_global[permission] != is_global:
                # we don't specifically keep track of which previous file set the is_global;
                # look back through all of the unresolved permissions to find where it came from
                # (this is slowish but only happens in the failure case)
                raise ValueError(
                    f"'Is Global' for {permission} in {file_path} is inconsistent "
                    f"with a previous CSV file ({permission_is_global_source_csv[permission]})"
                )
        permission_is_global.update(file_permission_is_global)
        permission_is_global_source_csv.update({perm: file_path for perm in file_permission_is_global.keys()})

        # merge unresolved permissions
        for permission, new_user_type_to_unresolved in new_permission_to_user_type_to_unresolved.items():
            if permission not in permission_to_user_type_to_unresolved:
                permission_to_user_type_to_unresolved[permission] = {}
            for user_type, new_unresolved in new_user_type_to_unresolved.items():
                if user_type not in permission_to_user_type_to_unresolved[permission]:
                    permission_to_user_type_to_unresolved[permission][user_type] = new_unresolved
                else:
                    # both the new and an older CSV file include this cell
                    existing_unresolved = permission_to_user_type_to_unresolved[permission][user_type]
                    if new_unresolved == existing_unresolved:
                        # they are the same so do nothing (leaves the old one in place)
                        pass
                    elif existing_unresolved.evaluator_name == "":
                        # old CSV cell was empty, use new one
                        permission_to_user_type_to_unresolved[permission][user_type] = new_unresolved
                    elif new_unresolved.evaluator_name == "":
                        # new CSV cell is empty, use old one
                        pass
                    else:
                        # they were not the same and neither was empty. This means they're inconsistent
                        raise ValueError(
                            f"Permission {permission} for user type {user_type} in "
                            f"{file_path} is inconsistent with a previous CSV file "
                            f"({existing_unresolved.source_csv})"
                        )


    # now take the partially resolved functions and resolve them
    permission_to_user_type_to_evaluator: Dict[PermName, Dict[UserType, Evaluator]] = {}
    for permission, user_type_to_unresolved in permission_to_user_type_to_unresolved.items():
        if permission not in permission_to_user_type_to_evaluator:
            permission_to_user_type_to_evaluator[permission] = {}
        for user_type, detail in user_type_to_unresolved.items():
            try:
                for resolve_evaluator in resolve_evaluators:
                    evaluator = resolve_evaluator(detail)
                    if evaluator is not None:
                        permission_to_user_type_to_evaluator[permission][user_type] = evaluator
                        break
                else:
                    raise ValueError(f"Could not resolve {permission} for {user_type} to anything")
            except Exception as e:
                raise RuntimeError(f"Error resolving {permission} for {user_type}: {detail.evaluator_name} ({e})") from e

    return permission_to_user_type_to_evaluator, permission_is_global, known_user_types, known_perms


# note that django creates a new instance of an auth backend for every permission check!
class CSVPermissionsBackend:
    permission_lookup: Dict[PermName, Dict[UserType, Evaluator]]
    permission_is_global: Dict[PermName, bool]
    known_user_types: Set[UserType]
    known_perms: Set[PermName]

    def __init__(self):
        try:
            permissions_paths = settings.CSV_PERMISSIONS_PATHS
        except AttributeError:
            try:
                settings.CSV_PERMISSIONS_PATHS = (settings.CSV_PERMISSIONS_PATH,)
            except AttributeError:
                raise ImproperlyConfigured("csv_permissions requires settings.CSV_PERMISSIONS_PATHS to be set")
            else:
                permissions_paths = settings.CSV_PERMISSIONS_PATHS
                del settings.CSV_PERMISSIONS_PATH

        # make sure it's immutable so that it's hashable and _resolve_functions() can have @lru_cache() applied
        if not isinstance(permissions_paths, tuple):
            if isinstance(permissions_paths, (str, Path)):
                raise ImproperlyConfigured("settings.CSV_PERMISSIONS_PATHS should be an iterable of paths")
            permissions_paths = tuple(permissions_paths)
            settings.CSV_PERMISSIONS_PATHS = permissions_paths

        try:
            resolve_perm_name = settings.CSV_PERMISSIONS_RESOLVE_PERM_NAME
        except AttributeError:
            try:
                settings.CSV_PERMISSIONS_RESOLVE_PERM_NAME = settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME
            except AttributeError:
                resolve_perm_name = None
            else:
                warnings.warn(
                    "settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME is deprecated in favor of settings.CSV_PERMISSIONS_RESOLVE_PERM_NAME",
                    DeprecationWarning
                )
                resolve_perm_name = settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME

        try:
            resolve_evaluators = settings.CSV_PERMISSIONS_RESOLVE_EVALUATORS
        except AttributeError:
            raise ImproperlyConfigured(
                'settings.CSV_PERMISSIONS_RESOLVE_EVALUATORS must be defined. '
                'For legacy 0.1.0 compatibility use "csv_permissions.legacy.legacy_resolve_evaluator".'
            )
        else:
            if isinstance(resolve_evaluators, str):
                resolve_evaluators = import_string(resolve_evaluators)
            resolve_evaluators = tuple(resolve_evaluators)

        self.permission_lookup, self.permission_is_global, self.known_user_types, self.known_perms = _resolve_functions(
            permissions_paths,
            resolve_perm_name,
            resolve_evaluators,
        )

    def authenticate(self, request: HttpRequest, username: Optional[str] = None, password: Optional[str] = None):
        return None

    def is_global_perm(self, perm: str) -> bool:
        try:
            return self.permission_is_global[perm]
        except KeyError as ke:
            raise ValueError(f"Permission {perm} is not known") from ke

    def has_perm(self, user: Model, perm: str, obj: Model) -> bool:
        if user is None:
            return False

        get_user_type = getattr(settings, 'CSV_PERMISSIONS_GET_USER_TYPE', default_get_user_type)
        if isinstance(get_user_type, str):
            settings.CSV_PERMISSIONS_GET_USER_TYPE = import_string(settings.CSV_PERMISSIONS_GET_USER_TYPE)
            get_user_type = settings.CSV_PERMISSIONS_GET_USER_TYPE

        user_type = get_user_type(user)
        if user_type is None:
            # if there is no user_type then it's probably an AnonymousUser, but might also be a
            # user using a different permissions backend; either way they're not covered by csv_permissions
            return False

        if getattr(settings, "CSV_PERMISSIONS_STRICT", False):
            if perm not in self.known_perms:
                raise LookupError(f"Permission {repr(perm)} is not known")
            if user_type not in self.known_user_types:
                raise LookupError(f"User Type {repr(user_type)} is not known")

        try:
            func = self.permission_lookup[perm][user_type]
        except KeyError:
            # If we get here it means that
            #  - the permission/user type is not known at all and CSV_PERMISSIONS_STRICT is not set
            # or
            #  - the permission & user types are known but because there are multiple CSV files that
            #    particular combination doesn't appear in any CSV file
            #
            # in either case we allow django to try other backends
            return False

        return func(user, obj)
