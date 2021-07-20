import contextlib
import tempfile
from typing import Iterable

from django.test import override_settings


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
