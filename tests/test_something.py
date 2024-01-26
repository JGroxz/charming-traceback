import json
import re
from json import JSONDecodeError
from types import ModuleType

import pytest
from rich.console import Console


def test_install_traceback():
    from charming_traceback.installation import install
    install()

    with pytest.raises(RuntimeError) as e:
        raise RuntimeError()


def test_print_exception(console: Console):
    from charming_traceback import CharmingTraceback

    def function_with_exception():
        raise RuntimeError()

    try:
        function_with_exception()
    except RuntimeError:
        CharmingTraceback.print_exception(console=console)

    output = console.file.getvalue()  # type: ignore
    assert "RuntimeError" in output


@pytest.mark.parametrize(
    "suppress", [
        [json],  # <- must work when using actual modules
        ["json"],  # <- must work when using module names as strings
    ]
)
def test_suppress_traceback(console: Console, suppress: list[ModuleType | str]):
    from charming_traceback import CharmingTraceback

    try:
        json.loads("totally valid json string (no)")
    except JSONDecodeError:
        CharmingTraceback.print_exception(console=console, suppress=suppress)

    output = console.file.getvalue()  # type: ignore

    # JSONDecodeError from calling json.loads() produces stack entries belonging to json and json.decoder modules;
    # two of them should get suppressed:
    suppressed_matches = re.findall(r"╰─▶ \(suppressed\) File .*", output)
    assert len(suppressed_matches) == 2

    # ...while the last one must be always preserved to allow the user to see the actual error:
    preserved_matches = re.findall(r"╰─▶ File .*/json/decoder.py", output)
    assert len(preserved_matches) == 1
