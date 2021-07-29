import contextlib
from pathlib import Path
import tempfile
from typing import Iterable
from typing import Tuple

from django.test import override_settings

try:
    # deprecated but still exists as of 3.9
    from typing import ContextManager
except ImportError:
    # 3.9 onwards
    from contextlib import AbstractContextManager as ContextManager


@contextlib.contextmanager
def override_csv_permissions(csv_datas: Iterable[str]) -> ContextManager[Tuple[Path, ...]]:
    """
    Creates temporary CSV files with the specified contents and then sets CSV_PERMISSIONS_PATHS

    returns a list of the fil
    """

    if isinstance(csv_datas, str):
        raise TypeError("csv_datas should be an iterable of file contents; did you forget to wrap it in [ ]?")

    csv_filepaths = ()

    with contextlib.ExitStack() as stack:
        for csv_data in csv_datas:
            f = stack.enter_context(tempfile.NamedTemporaryFile("w"))
            csv_filepaths += (f.name, )
            f.writelines(csv_data.strip())
            f.seek(0)

        with override_settings(CSV_PERMISSIONS_PATHS=csv_filepaths):
            yield csv_filepaths