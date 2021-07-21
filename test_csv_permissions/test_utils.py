import contextlib
import tempfile
from typing import Dict
from typing import Iterable
import warnings

from django.test import override_settings
from django.test.utils import TestContextDecorator

from test_csv_permissions.factory import CustomerUserFactory
from test_csv_permissions.factory import StaffUserFactory
from test_csv_permissions.models import CustomerProfile
from test_csv_permissions.models import StaffProfile

User1Model = CustomerProfile
USER1_TYPE = CustomerProfile.user_type
User1Factory = lambda *args, **kwargs: CustomerUserFactory.create(*args, **kwargs)  # noqa: E731

User2Model = StaffProfile
USER2_TYPE = StaffProfile.user_type
User2Factory = lambda *args, **kwargs: StaffUserFactory.create(*args, **kwargs)  # noqa: E731


@contextlib.contextmanager
def override_csv_permissions(csv_datas: Iterable[str]):
    """
    Creates temporary CSV files with the specified contents and then sets the
    """

    csv_filepaths = []

    with contextlib.ExitStack() as stack:
        for csv_data in csv_datas:
            f = stack.enter_context(tempfile.NamedTemporaryFile("w"))
            csv_filepaths.append(f.name)
            f.writelines(csv_data)
            f.seek(0)

        with override_settings(CSV_PERMISSIONS_PATHS=csv_filepaths):
            yield


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
