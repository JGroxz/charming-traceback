import io

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call():
    print()  # <- newline at the start of the logs to make them more readable
    yield


@pytest.fixture()
def console():
    """Rich console which writes to a StringIO."""
    from rich.console import Console

    return Console(file=io.StringIO(), width=300, color_system=None)
