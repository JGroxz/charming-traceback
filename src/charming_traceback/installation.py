import asyncio
import sys
from types import ModuleType, TracebackType
from typing import Callable, Any, Iterable

from rich.console import Console
from rich.traceback import LOCALS_MAX_LENGTH, LOCALS_MAX_STRING

from charming_traceback.traceback import Traceback


def install(
    *,
    console: Console | None = None,
    width: int | None = 100,
    code_width: int | None = 88,
    extra_lines: int = 1,
    theme: str | None = None,
    word_wrap: bool = False,
    show_locals: bool = False,
    locals_max_length: int = LOCALS_MAX_LENGTH,
    locals_max_string: int = LOCALS_MAX_STRING,
    locals_hide_dunder: bool = True,
    locals_hide_sunder: bool | None = None,
    indent_guides: bool = True,
    suppress: Iterable[str | ModuleType] = (),
    max_frames: int = 100,
) -> Callable[[type[BaseException], BaseException, TracebackType | None], Any]:
    """
    Install a rich traceback handler.

    Once installed, any tracebacks will be printed with syntax highlighting and rich formatting.

    Args:
        console (Console | None, optional): Console to write exception to. Default uses internal Console instance.
        width (int | None, optional): Width (in characters) of traceback. Defaults to 100.
        code_width (int | None, optional): Code width (in characters) of traceback. Defaults to 88.
        extra_lines (int, optional): Extra lines of code. Defaults to 1.
        theme (str | None, optional): Pygments theme to use in traceback. Defaults to ``None`` which will pick
            a theme appropriate for the platform.
        word_wrap (bool, optional): Enable word wrapping of long lines. Defaults to False.
        show_locals (bool, optional): Enable display of local variables. Defaults to False.
        locals_max_length (int, optional): Maximum length of containers before abbreviating, or None for no abbreviation.
            Defaults to 10.
        locals_max_string (int, optional): Maximum length of string before truncating, or None to disable. Defaults to 80.
        locals_hide_dunder (bool, optional): Hide locals prefixed with double underscore. Defaults to True.
        locals_hide_sunder (bool, optional): Hide locals prefixed with single underscore. Defaults to False.
        indent_guides (bool, optional): Enable indent guides in code and locals. Defaults to True.
        suppress (Sequence[str | ModuleType]): Optional sequence of modules, module names or paths to exclude from traceback.
        max_frames (int, optional): Maximum number of frames to display. Defaults to 100.

    Returns:
        Callable: The previous exception handler that was replaced.

    """
    traceback_console = (
        Console(soft_wrap=True, file=sys.stderr) if (console is None) else console
    )

    locals_hide_sunder = (
        True
        if (traceback_console.is_jupyter and locals_hide_sunder is None)
        else locals_hide_sunder
    )

    def excepthook(
        type_: type[BaseException],
        value: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        exception_traceback = Traceback.from_exception(
            type_,
            value,
            traceback,
            width=width,
            code_width=code_width,
            extra_lines=extra_lines,
            theme=theme,
            word_wrap=word_wrap,
            show_locals=show_locals,
            locals_max_length=locals_max_length,
            locals_max_string=locals_max_string,
            locals_hide_dunder=locals_hide_dunder,
            locals_hide_sunder=bool(locals_hide_sunder),
            indent_guides=indent_guides,
            suppress=suppress,
            max_frames=max_frames,
        )
        traceback_console.print(
            exception_traceback,
            crop=False,  # <- no crop to always show full file path, even in narrow consoles
        )

    def ipy_excepthook_closure(ip: Any) -> None:  # pragma: no cover
        tb_data = {}  # store information about showtraceback call
        default_showtraceback = ip.showtraceback  # keep reference of default traceback

        def ipy_show_traceback(*args: Any, **kwargs: Any) -> None:
            """Wrap the default ip.showtraceback to store info for ip._showtraceback"""
            nonlocal tb_data
            tb_data = kwargs
            default_showtraceback(*args, **kwargs)

        def ipy_display_traceback(
            *args: Any, is_syntax: bool = False, **kwargs: Any
        ) -> None:
            """Internally called traceback from ip._showtraceback"""
            nonlocal tb_data
            exc_tuple = ip._get_exc_info()  # type: ignore

            # do not display trace on syntax error
            tb: TracebackType | None = None if is_syntax else exc_tuple[2]

            # determine correct tb_offset
            compiled = tb_data.get("running_compiled_code", False)
            tb_offset = tb_data.get("tb_offset", 1 if compiled else 0)
            if tb_offset is None:
                tb_offset = 1 if compiled else 0
            # remove ipython internal frames from trace with tb_offset
            for _ in range(tb_offset):
                if tb is None:
                    break
                tb = tb.tb_next

            excepthook(exc_tuple[0], exc_tuple[1], tb)
            tb_data = {}  # clear data upon usage

        # replace _showtraceback instead of showtraceback to allow ipython features such as debugging to work
        # this is also what the ipython docs recommends to modify when subclassing InteractiveShell
        ip._showtraceback = ipy_display_traceback
        # add wrapper to capture tb_data
        ip.showtraceback = ipy_show_traceback
        ip.showsyntaxerror = lambda *args, **kwargs: ipy_display_traceback(
            *args, is_syntax=True, **kwargs
        )

    def asyncio_excepthook(loop: Any, context: dict[str, Any]) -> None:
        exception: BaseException | None = context.get("exception", None)
        if exception is None:
            return

        exception_type = type(exception)

        excepthook(
            exception_type,
            exception,
            None,
        )

    try:  # pragma: no cover
        # if within ipython, use customized traceback
        ipython = get_ipython()  # type: ignore[name-defined] # noqa: F821
        ipy_excepthook_closure(ipython)
        return sys.excepthook
    except Exception:
        # otherwise use default system hook
        old_excepthook = sys.excepthook
        sys.excepthook = excepthook

        # if within asyncio, update loop exception handler as well
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(asyncio_excepthook)

        return old_excepthook
