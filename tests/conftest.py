import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call():
    print()  # <- newline at the start of the logs to make them more readable
    yield
