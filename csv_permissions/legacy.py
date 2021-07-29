from functools import wraps
from typing import Optional
import warnings

from django.utils.module_loading import import_string

from csv_permissions.evaluators import make_evaluate_not_implemented
from csv_permissions.evaluators import resolve_all_evaluator
from csv_permissions.evaluators import resolve_empty_evaluator
from csv_permissions.evaluators import resolve_fallback_not_implemented_evaluator
from csv_permissions.evaluators import resolve_no_evaluator
from csv_permissions.evaluators import resolve_validate_is_global_model
from csv_permissions.evaluators import resolve_yes_evaluator
from csv_permissions.types import Evaluator
from csv_permissions.types import UnresolvedEvaluator


def resolve_legacy_warning_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    # we deliberately make bad permissions raise warnings instead of exceptions so that you can get
    # up & running quickly with scaffolding an app and then come back and fix the permissions later
    warnings.warn(
        "csv_permissions.legacy.legacy_resolve_evaluator() will be removed in future. "
        "You should copy legacy evaluators into your project.",
        DeprecationWarning,
    )
    return None


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


def resolve_legacy_validate_global_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if _PREDEFINED_ACTION_IS_GLOBAL.get(details.action, details.is_global) != details.is_global:
        model_name = None if details.model is None else details.model._meta.model_name
        raise ValueError(
            "Invalid action / global setting for"
            f" {details.app_config.label}.{model_name}.{details.action} (is_global should"
            f" not be {details.is_global})"
        )

    return None


def evaluate_own(own_function, user, obj=None) -> bool:
    if obj is None:
        raise ValueError("'own' cannot be used as a global permission.")

    return own_function(user, obj)


def resolve_own_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if not details.evaluator_name.startswith("own:") and details.evaluator_name != "own":
        return None

    if details.is_global:
        raise ValueError("'own' cannot be used as a global permission.")

    model_name = None if details.model is None else details.model._meta.model_name
    app_label = details.app_config.label

    if details.evaluator_name == "own":
        function_name = f"{model_name}_own"
    else:
        own = details.evaluator_name.split(":", 1)[-1].strip()
        if not own:
            message = "No function name specified for 'own:'. Remove ':' or specify a function to call."
            raise ValueError(message)

        function_name = f"{model_name}_own_{own}"

    try:
        permission_function = import_string(f"{details.app_config.name}.rules.{function_name}")
    except ImportError:
        message = f"No implementation of {function_name}() in {app_label}.rules"
        warnings.warn(message, stacklevel=2)
        return make_evaluate_not_implemented(message)

    @wraps(permission_function)
    def own_function(user, obj=None) -> bool:
        return evaluate_own(permission_function, user, obj)

    return own_function


def resolve_custom_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:

    if not details.evaluator_name.startswith("custom:"):
        return None

    app_label = details.app_config.label

    custom = details.evaluator_name.split(":", 1)[-1].strip()
    if not custom:
        raise ValueError("No custom function name specified.")

    function_name = custom

    try:
        evaluate_custom = import_string(f"{details.app_config.name}.rules.{function_name}")
    except ImportError:
        message = f"No implementation of {function_name}() in {app_label}.rules"
        warnings.warn(message, stacklevel=2)
        return make_evaluate_not_implemented(message)

    return evaluate_custom


resolve_evaluators = (
    resolve_legacy_warning_evaluator,
    resolve_legacy_validate_global_evaluator,
    resolve_validate_is_global_model,
    resolve_own_evaluator,
    resolve_custom_evaluator,
    resolve_all_evaluator,
    resolve_yes_evaluator,
    resolve_no_evaluator,
    resolve_empty_evaluator,
    resolve_fallback_not_implemented_evaluator,
)

