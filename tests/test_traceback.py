import json
import re
from json import JSONDecodeError
from types import ModuleType

import pytest
from rich.console import Console

from charming_traceback.traceback import Traceback


def test_installation():
    """
    Tests that the install() function correctly sets up sys.excepthook and asyncio loop exception handler.
    """

    import asyncio
    import sys
    from charming_traceback.installation import install

    old_sys_hook = sys.excepthook
    loop = asyncio.get_event_loop()
    old_loop_handler = loop.get_exception_handler()

    try:
        # install() should return the previously installed sys.excepthook
        prev = install()
        assert prev is old_sys_hook, (
            "install() must return the previous sys.excepthook so callers can restore it"
        )

        # sys.excepthook should be our installed handler
        assert callable(sys.excepthook), (
            "sys.excepthook should be a callable after install()"
        )
        assert sys.excepthook.__name__ == "excepthook", (
            "sys.excepthook should be the closure named 'excepthook' from installation.py"
        )
        assert sys.excepthook.__module__ == "charming_traceback.installation", (
            "sys.excepthook should originate from charming_traceback.installation"
        )

        # asyncio loop's exception handler should also be installed
        loop_handler = loop.get_exception_handler()
        assert loop_handler is not None, (
            "Asyncio loop exception handler should be set by install()"
        )
        assert callable(loop_handler), "Asyncio loop handler must be callable"
        assert loop_handler.__name__ == "asyncio_excepthook", (
            "Asyncio loop handler should be the closure named 'asyncio_excepthook'"
        )
        assert loop_handler.__module__ == "charming_traceback.installation", (
            "Asyncio loop handler should originate from charming_traceback.installation"
        )
    finally:
        # Restore original hooks to avoid leaking state into other tests
        sys.excepthook = old_sys_hook
        loop.set_exception_handler(old_loop_handler)


def test_output_formatting(console: Console):
    """
    Tests that the printed traceback info looks the way we expect it to.
    """

    from charming_traceback import Traceback

    def function_with_exception():
        raise RuntimeError()

    try:
        function_with_exception()
    except RuntimeError:
        Traceback.print_exception(console=console)

    output = console.file.getvalue()  # type: ignore
    assert "RuntimeError" in output, (
        "Traceback output should include the exception name 'RuntimeError'"
    )

    # Verify that the output contains the full path to this file where the exception was raised
    from pathlib import Path

    current_file = Path(__file__).resolve()
    # The path in our renderer is quoted, e.g. ╰─▶ File "/abs/path/to/test_traceback.py", line N
    pattern = r'╰─▶ File "' + re.escape(str(current_file)) + r'"'
    assert re.search(pattern, output), (
        f"Traceback output should include the full path to this test file: {current_file}"
    )


@pytest.mark.parametrize(
    "suppress",
    [
        [json],  # <- must work when using actual modules
        ["json"],  # <- must work when using module names as strings
    ],
)
def test_suppressed_output_formatting(
    console: Console, suppress: list[ModuleType | str]
):
    """
    Tests that frames from suppressed modules are correctly minimized in the traceback output.
    """

    from charming_traceback import Traceback

    try:
        json.loads("totally valid json string (no)")
    except JSONDecodeError:
        Traceback.print_exception(console=console, suppress=suppress)

    output = console.file.getvalue()  # type: ignore

    # JSONDecodeError from calling json.loads() produces stack entries belonging to json and json.decoder modules;
    # two of them should get suppressed:
    suppressed_matches = re.findall(r"╰─▶ \(suppressed\) File .*", output)
    assert len(suppressed_matches) == 2, (
        "Two frames from json/json.decoder should be suppressed to reduce noise"
    )

    # ...while the last one must be always preserved to allow the user to see the actual error:
    preserved_matches = re.findall(r"╰─▶ File .*/json/decoder.py", output)
    assert len(preserved_matches) == 1, (
        "The final json.decoder frame must be kept so the user can see the error location"
    )


def test_printing():
    """
    Just prints the traceback to the test console for us to visually inspect.
    """

    from charming_traceback import install

    install()

    def nested_function():
        raise ExceptionGroup(
            "A test group of exceptions.",
            [
                ValueError("This is a test error."),
                RuntimeError("This is just another test error."),
            ],
        )

    try:
        nested_function()
    except ExceptionGroup:
        try:
            raise RuntimeError("This is an extra outer exception.")
        except RuntimeError:
            console = Console(force_terminal=True)
            Traceback.print_exception(console=console)
