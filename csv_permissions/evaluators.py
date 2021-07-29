from typing import Optional
import warnings

from csv_permissions.types import Evaluator
from csv_permissions.types import UnresolvedEvaluator


def make_evaluate_not_implemented(message) -> Evaluator:
    """Creates a new evaluator that when invoked throws a NotImplementedError error
    with a given message"""
    def evaluate_not_implemented(user, obj=None) -> bool:
        raise NotImplementedError(message)
    return evaluate_not_implemented


def resolve_validate_is_global_model(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    """
    This doesn't actually resolve to any evaluators, it just validates that
    is_global=False permissions have a model
    """
    if details.model is None and not details.is_global:
        raise ValueError("Permissions without Models must be global.")
    return None


def evaluate_all(user, obj=None) -> bool:
    if obj is None:
        raise ValueError("'all' cannot be used as a global permission.")
    return True


def resolve_all_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if details.evaluator_name == "all":
        if details.is_global:
            raise ValueError("'all' cannot be used as a global permission.")
        return evaluate_all
    return None


def evaluate_yes(user, obj=None) -> bool:
    if obj is not None:
        raise ValueError("'yes' cannot be used as an object-level permission.")
    return True


def resolve_yes_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if details.evaluator_name == "yes":
        if not details.is_global:
            raise ValueError("'yes' cannot be used as an object-level permission.")
        return evaluate_yes
    return None


def evaluate_no(user, obj=None) -> bool:
    return False


def resolve_no_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if details.evaluator_name == "no":
        return evaluate_no
    return None


def resolve_empty_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    if details.evaluator_name == "":
        return evaluate_no
    return None


def resolve_fallback_not_implemented_evaluator(details: UnresolvedEvaluator) -> Optional[Evaluator]:
    """"Matches anything and throws a NotImplementedError """
    message = f"{repr(details.evaluator_name)} not implemented for {details.permission}"
    warnings.warn(message)
    return make_evaluate_not_implemented(message)


default_resolve_evaluators = (
    resolve_validate_is_global_model,
    resolve_all_evaluator,
    resolve_yes_evaluator,
    resolve_no_evaluator,
    resolve_empty_evaluator,
    resolve_fallback_not_implemented_evaluator,
)
