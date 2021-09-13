from typing import Dict
import warnings

from django.test.utils import TestContextDecorator

from test_csv_permissions.factory import UserFactory
from test_csv_permissions.models import User

USER1_TYPE = User.USER_TYPE_CUSTOMER
USER2_TYPE = User.USER_TYPE_STAFF


def User1Factory(**kwargs):
    return UserFactory.create(user_type=USER1_TYPE, **kwargs)


def User2Factory(**kwargs):
    return UserFactory.create(user_type=USER2_TYPE, **kwargs)


class warning_filter(TestContextDecorator):
    """
    Apply a warning.simplefilter()

    see https://docs.python.org/3/library/warnings.html#describing-warning-filters
    """

    action: str
    filters: Dict

    def __init__(self, action, **filters):
        self.action = action
        self.filters = filters
        super().__init__()

    def enable(self):
        self.context_manager = warnings.catch_warnings()
        self.context_manager.__enter__()
        warnings.filterwarnings(self.action, **self.filters)

    def disable(self):
        self.context_manager.__exit__(None, None, None)
