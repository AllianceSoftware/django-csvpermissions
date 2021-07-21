from dataclasses import dataclass
from typing import Callable
from typing import Optional
from typing import Type

from django.apps import AppConfig
from django.db.models import Model

# a permission name
PermName = str

# a user type
UserType = str

# a callable to check whether a user has a permission for a given object
Evaluator = Callable[[Model, Optional[Model]], bool]

# function to resolve a permission name
ResolvePermNameFunc = Callable[[AppConfig, Type[Model], str, bool], str]


@dataclass(frozen=True)
class UnresolvedEvaluator:
    """This is a placeholder for a cell in a CSV file that has been
    read but not yet resolved to the evaluator function"""
    app_config: AppConfig
    model: Optional[Model]
    is_global: bool
    permission: PermName
    action: str
    evaluator_name: str


# function to resolve an evaluator function
ResolveEvaluatorFunc = Callable[[UnresolvedEvaluator], Evaluator]
