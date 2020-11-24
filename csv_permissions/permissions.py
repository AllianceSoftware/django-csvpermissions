from csv import DictReader
from dataclasses import dataclass
from functools import lru_cache
from functools import wraps
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
from django.db.models import Model
from django.utils.module_loading import import_string

# a callable to check whether a has a permission for a given object
PermCheckCallable = Callable[[Model, Optional[Model]], bool]

# a permission name
PermName = str

# a group name
GroupName = str

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
    file_path: str,
) -> Tuple[Dict[PermName, bool], Dict[PermName, Dict[GroupName, PartiallyResolvedPermission]]]:
    """
    Parses the CSV of group permissions returns a list of permissions for further processing.

    CSV file format:
        entity, app_name, permission_name, is_global, group1, group2, .. groupN

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
    :return: A tuple of two elements:
        A dict mapping permission name to bool of whether that permission is global or not
        A dict mapping a permission to a dict of group names to partially resolved permission details:

        permission_name: {
            group1: PartiallyResolvedPermission,
            ...
            groupN: PartiallyResolvedPermission,
        }
    """

    try:
        CSV_PERMISSIONS_RESOLVE_RULE_NAME = settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME
        if CSV_PERMISSIONS_RESOLVE_RULE_NAME is None:
            raise AttributeError
    except AttributeError:
        CSV_PERMISSIONS_RESOLVE_RULE_NAME = _default_resolve_rule_name
    else:
        CSV_PERMISSIONS_RESOLVE_RULE_NAME = import_string(CSV_PERMISSIONS_RESOLVE_RULE_NAME)

    with open(file_path, "r") as csv_file:
        reader = DictReader(csv_file, skipinitialspace=True)

        if reader.fieldnames[:4] != ["Model", "App", "Action", "Is Global"]:
            raise RuntimeError(f"Invalid csv_permissions CSV column headers found in {file_path}")

        auth_groups = reader.fieldnames[4:]
        if not auth_groups:
            raise RuntimeError(f"Invalid csv_permissions CSV column headers found in {file_path}")

        perm_is_global = {}
        perm_group_details = {}

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

            rule_name = CSV_PERMISSIONS_RESOLVE_RULE_NAME(app_config, model, action, is_global)

            if rule_name not in perm_is_global:
                perm_is_global[rule_name] = is_global
                perm_group_details[rule_name] = {}

            for auth_group in auth_groups:
                access_level = row[auth_group]

                perm_group_details[rule_name][auth_group] = PartiallyResolvedPermission(
                    app_config=app_config,
                    model=model,
                    action=action,
                    access_level=access_level,
                )

        if was_empty:
            raise RuntimeError("Empty permissions file")

        return perm_is_global, perm_group_details


# should be at least as large as the number of CSV files we load. This gets called by every has_perm() so must be cached
@lru_cache(maxsize=32)
def _resolve_functions(
    file_path: str, resolve_rule_name: str
) -> Tuple[Dict[PermName, Dict[GroupName, PermCheckCallable]], Dict[PermName, bool]]:
    """
    :param file_path: Path to the CSV from which to import.
    :resolve_rule_name: the settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME setting. This is not actually used but is needed for lru_cache invalidation
    :return: A tuple of dictionaries:
            The first maps the permissions for each group to a function determining if the user has access.
            The second maps the permission to a boolean indicating whether the permission is object level or global level.
    """

    permission_is_global, perm_group_details = _parse_csv(file_path)

    permission_to_group_to_function = {perm: {} for perm in permission_is_global.keys()}
    for permission, is_global in permission_is_global.items():
        for group, detail in perm_group_details[permission].items():
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
                permission_to_group_to_function[permission][group] = _resolve_function(
                    detail.app_config, access_level, function_name, is_global
                )
            except RuntimeError as e:
                raise RuntimeError(f"{e} Permission: {permission}")

    return permission_to_group_to_function, permission_is_global


# note that django creates a new instance of an auth backend for every permission check!
class CSVPermissionsBackend:
    def __init__(self):
        self.permission_lookup, self.permission_is_global = _resolve_functions(
            settings.CSV_PERMISSIONS_PATH, settings.CSV_PERMISSIONS_RESOLVE_RULE_NAME
        )

    def authenticate(self, request, username=None, password=None):
        return None

    def is_global_perm(self, perm: str) -> bool:
        try:
            return self.permission_is_global[perm]
        except KeyError as ke:
            raise ValueError(f"Permission {perm} is not known") from ke

    def has_perm(self, user: Model, perm: str, obj: Model) -> bool:
        try:
            user_group = str(user.get_profile().user_type)
        except AttributeError:
            # Not logged in / No user profile
            return False

        try:
            func = self.permission_lookup[perm][user_group]
        except KeyError:
            # Permission or group doesn't exist in CSV
            return None

        return func(user, obj)
