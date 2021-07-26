import contextlib
import tempfile
from typing import Iterable

from django.test import override_settings


@contextlib.contextmanager
def override_csv_permissions(csv_datas: Iterable[str]):
    """
    Creates temporary CSV files with the specified contents and then sets the
    """

    if isinstance(csv_datas, str):
        raise TypeError("csv_datas should be an iterable of file contents; did you forget to wrap it in [ ]?")

    csv_filepaths = []

    with contextlib.ExitStack() as stack:
        for csv_data in csv_datas:
            f = stack.enter_context(tempfile.NamedTemporaryFile("w"))
            csv_filepaths.append(f.name)
            f.writelines(csv_data.strip())
            f.seek(0)

        with override_settings(CSV_PERMISSIONS_PATHS=csv_filepaths):
            yield