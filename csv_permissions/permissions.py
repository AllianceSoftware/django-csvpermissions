from csv import DictReader
from typing import Iterable
from typing import Set

from dataclasses import dataclass
from functools import lru_cache
from functools import wraps
from pathlib import Path
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Type
import warnings

from django.apps import AppConfig
from django.apps import apps
from django.conf import settings
import django.contrib.auth
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model
from django.http import HttpRequest
from django.utils.module_loading import import_string

# a callable to check whether a has a permission for a given object
PermCheckCallable = Callable[[Model, Optional[Model]], bool]

# a permission name
PermName = str

# a user type
UserType = str

# function to resolve a permission name
ResolveRuleNameFunc = Callable[[AppConfig, Type[Model], str, bool], str]

#TODO: don't hardcode this
# mapping of predefined actions to is_global
_PREDEFINED_ACTION_IS_GLOBAL = {
    "list": True,
    "detail": False,
    "create": True,
    "add": True,
    "change": False,
    "update": False,
    "delete": False,
}


def _access_level_yes(user, obj=None) -> bool:
    if obj is not None:
        raise RuntimeError("'yes' cannot be used with object-level permissions.")

    return True


def _access_level_no(user, obj=None) -> bool:
    return False


def _access_level_all(user, obj=None) -> bool:
    if obj is None:
        raise RuntimeError("'all' cannot be used with global permissions.")

    return True


def _access_level_own(own_function, user, obj=None) -> bool:
    if obj is None:
        raise RuntimeError("'own' cannot be used with global permissions.")

    return own_function(user, obj)


def _access_level_custom(custom_function, user, obj=None) -> bool:
    return custom_function(user, obj)


def _resolve_function(
    app_config: AppConfig, access_level: str, function_name: str, is_global: bool
) -> PermCheckCallable:
    """
    Returns the callable for determining permissions based on access level.

    :param app_label: The Django app label for the permission.
    :param access_level: One of 'yes/''/'all'/'own'/'custom'
    :param function_name: The name of the permission function. If access_level is own or custom, it will be
    searched for in the rules module of app_label.
    :param is_global: A boolean indicating whether the access level applies at the global or object level.
    :return: The function to call to determine if a user has access.
    """

    app_label = app_config.label

    if access_level == "yes":
        if not is_global:
            raise RuntimeError("'yes' cannot be used with object-level permissions.")

        return _access_level_yes

    if access_level == "":
        return _access_level_no

    if access_level == "all":
        if is_global:
            raise RuntimeError("'all' cannot be used with global permissions.")

        return _access_level_all

    if access_level == "own":
        if is_global:
            raise RuntimeError("'own' cannot be used with global permissions.")

        try:
            app_config = apps.get_app_config(app_label)
            permission_function = import_string(f"{app_config.name}.rules.{function_name}")
        except ImportError:
            message = f"No implementation of {function_name}() in {app_label}.rules"
            warnings.warn(message, stacklevel=2)

            def _permission_function(user, obj=None) -> bool:
                raise NotImplementedError(message)

            _permission_function.__name__ = function_name
            permission_function = _permission_function

        @wraps(permission_function)
        def own_function(user, obj=None) -> bool:
            return _access_level_own(permission_function, user, obj)

        return own_function

    if access_level == "custom":
        try:
            app_config = apps.get_app_config(app_label)
            permission_function = import_string(f"{app_config.name}.rules.{function_name}")
        except ImportError:
            message = f"No implementation of {function_name}() in {app_label}.rules"
            warnings.warn(message, stacklevel=2)

            def _permission_function(user, obj=None):
                raise NotImplementedError(message)

            _permission_function.__name__ = function_name
            permission_function = _permission_function

        @wraps(permission_function)
        def custom_function(user, obj=None) -> bool:
            return _access_level_custom(permission_function, user, obj)

        return custom_function


def _default_resolve_rule_name(
    app_config: AppConfig, model: Type[Model], action: str, is_global: bool
) -> str:
    if model:
        default_codename = django.contrib.auth.get_permission_codename(action, model._meta)
        rule_name = f"{app_config.label}.{default_codename}"
    else:
        rule_name = f"{app_config.label}.{action}"
    return rule_name


# FIXME - @Levi to add doc / explanation to this. see https://gitlab.internal.alliancesoftware.com.au/alliance/template-django/-/merge_requests/150#note_91667
@dataclass
class PartiallyResolvedPermission:
    app_config: AppConfig
    model: Model
    action: str
    access_level: str


def _parse_csv(
    file_path: Path,
    resolve_rule_name_func: ResolveRuleNameFunc,
) -> Tuple[
    Dict[PermName, bool],
    Dict[PermName, Dict[UserType, PartiallyResolvedPermission]],
    Iterable[str],
]:
    """
    Parses the CSV of user_type permissions returns a list of permissions for further processing.

    CSV file format:
        entity, app_name, permission_name, is_global, user_type1, user_type2, .. user_typeN

    The possible values for permissions are:
        '' (no permission)
        'yes' (has permission)
        'own: some_func' record is part of that user's permission scope. some_func takes a record
              and returns true/false according to whether the user should have access or not. The
              specifics of how this works are dependent on the application. Functionally this is
              identical to 'custom' but is different in that it relates to multi-tenant applications
              rather than some other arbitrary business rule.
        'all' (has permission with no additional requirements)
        'custom: name_of_custom_rule_function' (has permission as defined by name_of_custom_rule_function)

    :param file_path: Path to the CSV from which to import.
    :param resolve_rule_name_func: function to resolve rule names (the function pointed to by
        settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME)`
    :return: A tuple of three elements:
        - A dict mapping permission name to bool of whether that permission is global or not
        - A dict mapping a permission to a dict of user_types to partially resolved permission details:
            permission_name: {
                user_type1: PartiallyResolvedPermission,
                ...
                user_typeN: PartiallyResolvedPermission,
            }
        - A list of user types
    """

    with file_path.open("r") as csv_file:
        reader = DictReader(csv_file, skipinitialspace=True)

        if reader.fieldnames[:4] != ["Model", "App", "Action", "Is Global"]:
            raise RuntimeError(f"Invalid csv_permissions CSV column headers found in {file_path}")

        user_types = reader.fieldnames[4:]
        if not user_types:
            raise RuntimeError(f"Invalid csv_permissions CSV column headers found in {file_path}")

        perm_is_global = {}
        perm_user_type_details = {}

        # We can't just count the number of permissions because we don't consider
        # a file with commented out lines to be empty so keep track with a flag
        was_empty = True
        for row in reader:
            was_empty = False
            if all(x is None or x.strip() == "" for x in row.values()):
                # ignore completely empty rows
                continue
            model_name_orig = row["Model"]  # note that capitalisation may differ to model._meta.model_name

            if any(model_name_orig.strip().startswith(comment_prefix) for comment_prefix in ("//", "#")):
                # Ignore lines beginning with comment chars
                continue

            app_config = apps.get_app_config(row["App"])
            model = app_config.get_model(model_name_orig) if model_name_orig else None

            action = row["Action"]
            if row["Is Global"] == "yes":
                is_global = True
            elif row["Is Global"] == "no":
                is_global = False
            else:
                raise RuntimeError("Invalid value for Is Global.")

            if _PREDEFINED_ACTION_IS_GLOBAL.get(action, is_global) != is_global:
                raise RuntimeError(
                    "Invalid action / global setting for"
                    f" {app_config.label}.{model_name_orig}.{action} (is_global should"
                    f" not be {is_global})"
                )

            rule_name = resolve_rule_name_func(app_config, model, action, is_global)

            if rule_name not in perm_is_global:
                perm_is_global[rule_name] = is_global
                perm_user_type_details[rule_name] = {}

            for user_type in user_types:
                access_level = row[user_type]

                perm_user_type_details[rule_name][user_type] = PartiallyResolvedPermission(
                    app_config=app_config,
                    model=model,
                    action=action,
                    access_level=access_level,
                )

        if was_empty:
            raise RuntimeError("Empty permissions file")

        return perm_is_global, perm_user_type_details, user_types


# should be at least as large as the number of CSV files we load. This gets called by every has_perm() so must be cached
@lru_cache(maxsize=32)
def _resolve_functions(
    file_paths: Tuple[Path, ...],
    resolve_rule_name: Optional[str],
) -> Tuple[
    Dict[PermName, Dict[UserType, PermCheckCallable]],
    Dict[PermName, bool],
    Set[str],
    Set[str]
]:
    """
    :param file_path: Path to the CSV from which to import.
    :resolve_rule_name: the settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME setting.
    :return: A tuple of:
            - dictionary mapping the permissions for each UserType to a function determining if the user has access.
            - dictionary mapping the permission to a boolean indicating whether the permission is object level or global level.
            - set of user types
            - set of permissions
    """

    if resolve_rule_name is None:
        resolve_rule_name = _default_resolve_rule_name
    else:
        resolve_rule_name = import_string(resolve_rule_name)


    permission_is_global: Dict[PermName, bool] = {}

    known_user_types: Set[UserType] = set()
    known_perms: Set[PermName] = set()

    permission_to_user_type_to_partially_resolved: Dict[PermName, Dict[UserType, PartiallyResolvedPermission]] = {}

    for file_path in file_paths:
        file_permission_is_global, perm_user_type_details, user_types = _parse_csv(file_path, resolve_rule_name)

        # merge global list of known user types/permissions
        known_user_types.update(set(user_types))
        known_perms.update(set(file_permission_is_global.keys()))

        # merge is_global settings
        for permission, is_global in file_permission_is_global.items():
            if permission in permission_is_global and permission_is_global[permission] != is_global:
                raise ValueError(f"'Is Global' for {permission} in {file_path} is inconsistent with a previous CSV file")
        permission_is_global.update(file_permission_is_global)

        # merge partially resolved permissions
        for permission, user_type_to_partially_resolved in perm_user_type_details.items():
            if permission not in permission_to_user_type_to_partially_resolved:
                permission_to_user_type_to_partially_resolved[permission] = {}
            for user_type, partially_resolved in user_type_to_partially_resolved.items():
                if user_type in permission_to_user_type_to_partially_resolved[permission]:
                    if partially_resolved != permission_to_user_type_to_partially_resolved[permission][user_type]:
                        raise ValueError(f"Permission {permission} for user type {user_type} in {file_path} is inconsistent with a previous CSV file")
                else:
                    permission_to_user_type_to_partially_resolved[permission][user_type] = partially_resolved


    permission_to_user_type_to_function: Dict[PermName, Dict[UserType, PermCheckCallable]] = {}

    # now take the partially resolved functions and resolve them
    for permission, user_type_to_partially_resolved in permission_to_user_type_to_partially_resolved.items():
        is_global = permission_is_global[permission]
        if permission not in permission_to_user_type_to_function:
            permission_to_user_type_to_function[permission] = {}
        for user_type, detail in user_type_to_partially_resolved.items():
            access_level = detail.access_level or ""
            if detail.model is None:
                model_name = None
                if not is_global:
                    raise RuntimeError("Permissions without Models must be global.")
            else:
                model_name = detail.model._meta.model_name

            function_name = ""
            if access_level.startswith("own:"):
                own = access_level.split(":", 1)[-1].strip()
                if not own:
                    message = (
                        "No function name specified for 'own:'. Remove ':' or specify a" " function to call."
                    )
                    raise RuntimeError(message)

                function_name = f"{model_name}_own_{own}"
                access_level = "own"

            elif access_level == "own":
                function_name = f"{model_name}_own"
                access_level = "own"

            elif access_level.startswith("custom:"):
                custom = access_level.split(":", 1)[-1].strip()
                if not custom:
                    raise RuntimeError("No custom function name specified.")

                function_name = custom
                access_level = "custom"

            elif access_level in ("all", "", "yes"):
                pass

            else:
                warnings.warn(f"{access_level} is not a valid access level.")
                continue

            try:
                permission_to_user_type_to_function[permission][user_type] = _resolve_function(
                    detail.app_config, access_level, function_name, is_global
                )
            except RuntimeError as e:
                raise RuntimeError(f"{e} Permission: {permission}")

    return permission_to_user_type_to_function, permission_is_global, known_user_types, known_perms


# note that django creates a new instance of an auth backend for every permission check!
class CSVPermissionsBackend:
    permission_lookup: Dict[PermName, Dict[UserType, PermCheckCallable]]
    permission_is_global: Dict[PermName, bool]
    known_user_types: Set[UserType]
    known_perms: Set[PermName]

    def __init__(self):
        try:
            permissions_paths = settings.CSV_PERMISSIONS_PATHS
        except AttributeError:
            try:
                deprecation_message = "settings.CSV_PERMISSIONS_PATH is deprecated in favor of settings.CSV_PERMISSIONS_PATHS"
                warnings.warn(deprecation_message, DeprecationWarning)
                permissions_paths = (settings.CSV_PERMISSIONS_PATH,)
            except AttributeError:
                raise ImproperlyConfigured("csv_permissions requires settings.CSV_PERMISSIONS_PATHS to be set")

        permissions_paths = tuple(Path(p) for p in permissions_paths)

        self.permission_lookup, self.permission_is_global, self.known_user_types, self.known_perms = _resolve_functions(
            permissions_paths,
            getattr(settings, "CSV_PERMISSIONS_RESOLVE_RULE_NAME", None)
        )

    def authenticate(self, request: HttpRequest, username: Optional[str] = None, password: Optional[str] = None):
        return None

    def is_global_perm(self, perm: str) -> bool:
        try:
            return self.permission_is_global[perm]
        except KeyError as ke:
            raise ValueError(f"Permission {perm} is not known") from ke

    def has_perm(self, user: Model, perm: str, obj: Model) -> bool:
        try:
            # TODO: don't hardcode this
            user_type = str(user.get_profile().user_type)
        except AttributeError:
            # Not logged in / No user profile
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
