"""
Rich traceback handler modified to work better for PyCharm IDE.
"""

from __future__ import annotations

import linecache
import multiprocessing
import os
import sysconfig
import threading
from pathlib import Path
from traceback import walk_tb
from types import ModuleType, TracebackType
from typing import Optional, Iterable, Union, Type, Any

import rich
from pygments.token import Text as TextToken
from pygments.token import Token, String, Name, Number, Comment, Keyword, Operator
from rich import pretty
from rich._loop import loop_last
from rich.columns import Columns
from rich.console import Console
from rich.console import ConsoleOptions, RenderResult, ConsoleRenderable, group
from rich.constrain import Constrain
from rich.highlighter import ReprHighlighter
from rich.panel import Panel
from rich.scope import render_scope
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme
from rich.traceback import (
    Stack,
    _SyntaxError,
    Frame,
    PathHighlighter,
    Trace,
    LOCALS_MAX_LENGTH,
    LOCALS_MAX_STRING,
    Traceback,
)

from charming_traceback.styles import (
    TRACEBACK_MIDDLE_BOX,
    TRACEBACK_TOP_BOX,
    TRACEBACK_BOTTOM_BOX,
)

_SITE_PACKAGES_DIRECTORY = sysconfig.get_path("platlib")


class CharmingTraceback(Traceback):
    """A Console renderable that renders a traceback.

    Args:
        trace (Trace, optional): A `Trace` object produced from `extract`. Defaults to None, which uses
            the last exception.
        width (Optional[int], optional): Number of characters used to traceback. Defaults to 100.
        extra_lines (int, optional): Additional lines of code to render. Defaults to 3.
        theme (str, optional): Override pygments theme used in traceback.
        word_wrap (bool, optional): Enable word wrapping of long lines. Defaults to False.
        show_locals (bool, optional): Enable display of local variables. Defaults to False.
        indent_guides (bool, optional): Enable indent guides in code and locals. Defaults to True.
        locals_max_length (int, optional): Maximum length of containers before abbreviating, or None for no abbreviation.
            Defaults to 10.
        locals_max_string (int, optional): Maximum length of string before truncating, or None to disable. Defaults to 80.
        locals_hide_dunder (bool, optional): Hide locals prefixed with double underscore. Defaults to True.
        locals_hide_sunder (bool, optional): Hide locals prefixed with single underscore. Defaults to False.
        suppress (Sequence[Union[str, Path, ModuleType]]): Optional sequence of modules, module names or paths to exclude from traceback.
        max_frames (int): Maximum number of frames to show in a traceback, 0 for no maximum. Defaults to 100.

    """

    def __init__(
        self,
        trace: Trace | None = None,
        *,
        width: int | None = 100,
        extra_lines: int = 3,
        theme: str | None = None,
        word_wrap: bool = False,
        show_locals: bool = False,
        locals_max_length: int = LOCALS_MAX_LENGTH,
        locals_max_string: int = LOCALS_MAX_STRING,
        locals_hide_dunder: bool = True,
        locals_hide_sunder: bool = False,
        indent_guides: bool = True,
        suppress: Iterable[str | Path | ModuleType] = (),
        max_frames: int = 100,
    ):
        super().__init__(
            trace=trace,
            width=width,
            extra_lines=extra_lines,
            theme=theme,
            word_wrap=word_wrap,
            show_locals=show_locals,
            locals_max_length=locals_max_length,
            locals_max_string=locals_max_string,
            locals_hide_dunder=locals_hide_dunder,
            locals_hide_sunder=locals_hide_sunder,
            indent_guides=indent_guides,
            suppress=(),  # <- we handle suppress iterable differently
            max_frames=max_frames,
        )

        # handle suppressed modules differently from Rich's implementation
        self.suppress: list[str | Path | ModuleType] = []
        for suppress_entity in suppress:
            if isinstance(suppress_entity, ModuleType):
                assert (
                    suppress_entity.__file__ is not None
                ), f"{suppress_entity!r} must be a module with '__file__' attribute"
                path = Path(suppress_entity.__file__)
            else:
                path = Path(suppress_entity)

            if path.exists():
                if path.name == "__init__.py":
                    path = path.parent
                suppress_entity = path.resolve()

            self.suppress.append(suppress_entity)

    @classmethod
    def extract(
        cls,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        traceback: Optional[TracebackType],
        *,
        show_locals: bool = False,
        locals_max_length: int = LOCALS_MAX_LENGTH,
        locals_max_string: int = LOCALS_MAX_STRING,
        locals_hide_dunder: bool = True,
        locals_hide_sunder: bool = False,
    ) -> Trace:
        """Extract traceback information.

        Args:
            exc_type (Type[BaseException]): Exception type.
            exc_value (BaseException): Exception value.
            traceback (TracebackType): Python Traceback object.
            show_locals (bool, optional): Enable display of local variables. Defaults to False.
            locals_max_length (int, optional): Maximum length of containers before abbreviating, or None for no abbreviation.
                Defaults to 10.
            locals_max_string (int, optional): Maximum length of string before truncating, or None to disable. Defaults to 80.
            locals_hide_dunder (bool, optional): Hide locals prefixed with double underscore. Defaults to True.
            locals_hide_sunder (bool, optional): Hide locals prefixed with single underscore. Defaults to False.

        Returns:
            Trace: A Trace instance which you can use to construct a `Traceback`.
        """

        stacks: list[Stack] = []
        is_cause = False

        def safe_str(_object: Any) -> str:
            """Don't allow exceptions from __str__ to propagate."""
            # noinspection PyBroadException
            try:
                return str(_object)
            except Exception:
                return "<exception str() failed>"

        while True:
            stack = Stack(
                exc_type=safe_str(exc_type.__name__),
                exc_value=safe_str(exc_value),
                is_cause=is_cause,
            )

            if isinstance(exc_value, SyntaxError):
                stack.syntax_error = _SyntaxError(
                    offset=exc_value.offset or 0,
                    filename=exc_value.filename or "?",
                    lineno=exc_value.lineno or 0,
                    line=exc_value.text or "",
                    msg=exc_value.msg,
                )

            stacks.append(stack)
            append = stack.frames.append

            def get_locals(
                iter_locals: Iterable[tuple[str, object]],
            ) -> Iterable[tuple[str, object]]:
                """Extract locals from an iterator of key pairs."""
                if not (locals_hide_dunder or locals_hide_sunder):
                    yield from iter_locals
                    return
                for key, value in iter_locals:
                    if locals_hide_dunder and key.startswith("__"):
                        continue
                    if locals_hide_sunder and key.startswith("_"):
                        continue
                    yield key, value

            for frame_summary, line_no in walk_tb(traceback):
                filename = frame_summary.f_code.co_filename
                if filename and not filename.startswith("<"):
                    if not os.path.isabs(filename):
                        filename = os.path.join(_SITE_PACKAGES_DIRECTORY, filename)
                if frame_summary.f_locals.get("_rich_traceback_omit", False):
                    continue

                frame = Frame(
                    filename=filename or "?",
                    lineno=line_no,
                    name=frame_summary.f_code.co_name,
                    locals={
                        key: pretty.traverse(
                            value,
                            max_length=locals_max_length,
                            max_string=locals_max_string,
                        )
                        for key, value in get_locals(frame_summary.f_locals.items())
                    }
                    if show_locals
                    else None,
                )
                append(frame)
                if frame_summary.f_locals.get("_rich_traceback_guard", False):
                    del stack.frames[:]

            cause = getattr(exc_value, "__cause__", None)
            if cause:
                exc_type = cause.__class__
                exc_value = cause
                # __traceback__ can be None, e.g. for exceptions raised by the 'multiprocessing' module
                traceback = cause.__traceback__
                is_cause = True
                continue

            cause = exc_value.__context__
            if cause and not getattr(exc_value, "__suppress_context__", False):
                exc_type = cause.__class__
                exc_value = cause
                traceback = cause.__traceback__
                is_cause = False
                continue
            # No cover, code is reached but coverage doesn't recognize it.
            break  # pragma: no cover

        trace = Trace(stacks=stacks)
        return trace

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        theme = self.theme
        background_style = theme.get_background_style()
        token_style = theme.get_style_for_token

        traceback_theme = Theme(
            {
                "pretty": token_style(TextToken),
                "pygments.text": token_style(Token),
                "pygments.string": token_style(String),
                "pygments.function": token_style(Name.Function),
                "pygments.number": token_style(Number),
                "repr.indent": token_style(Comment) + Style(dim=True),
                "repr.str": token_style(String),
                "repr.brace": token_style(TextToken) + Style(bold=True),
                "repr.number": token_style(Number),
                "repr.bool_true": token_style(Keyword.Constant),
                "repr.bool_false": token_style(Keyword.Constant),
                "repr.none": token_style(Keyword.Constant),
                "scope.border": token_style(String.Delimiter),
                "scope.equals": token_style(Operator),
                "scope.key": token_style(Name),
                "scope.key.special": token_style(Name.Constant) + Style(dim=True),
            },
            inherit=False,
        )

        highlighter = ReprHighlighter()
        for last, stack in loop_last(reversed(self.trace.stacks)):
            if stack.frames:
                stack_renderable: ConsoleRenderable = self._render_stack(stack)
                stack_renderable = Constrain(stack_renderable, self.width)
                with console.use_theme(traceback_theme):
                    yield stack_renderable
            if stack.syntax_error is not None:
                syntax_error_renderable = self._render_syntax_error(stack.syntax_error)
                syntax_error_renderable = Constrain(syntax_error_renderable, self.width)
                with console.use_theme(traceback_theme):
                    yield syntax_error_renderable
                yield Text.assemble(
                    (f"{stack.exc_type}: ", "traceback.exc_type"),
                    highlighter(stack.syntax_error.msg),
                )
                yield ""
            elif stack.exc_value:
                yield Text.assemble(
                    (f"{stack.exc_type}: ", "traceback.exc_type"),
                    highlighter(Text.from_ansi(stack.exc_value)),
                )
                yield ""
            else:
                yield Text.assemble((f"{stack.exc_type}", "traceback.exc_type"))
                yield ""

            if not last:
                if stack.is_cause:
                    yield Text.from_markup(
                        "\n[i]The above exception was the direct cause of the following exception:\n",
                    )
                else:
                    yield Text.from_markup(
                        "\n[i]During handling of the above exception, another exception occurred:\n",
                    )

    @group()
    def _render_path(
        self,
        filename: Path,
        lineno: int,
        function_name: str | None = None,
        suppressed: bool = False,
    ) -> RenderResult:
        path_highlighter = PathHighlighter()

        text = Text.from_markup("[traceback.border]╰─▶[/] ")  # ⟶

        if suppressed:
            text.append(Text.from_markup("[dim](suppressed) "))

        text.append(
            Text.assemble(
                ("File ", "pygments.text"),
                path_highlighter(Text(f'"{filename}"', style="pygments.string")),
                (", line ", "pygments.text"),
                (str(lineno), "pygments.number"),
                style="pygments.text",
            )
        )

        if function_name:
            text.append(
                Text.assemble(
                    " in ",
                    (function_name, "pygments.function"),
                    style="pygments.text",
                )
            )

        # if PyCharm's console won't recognize and highlight paths in the console if they get wrapped using line breaks added by rich's formatting;
        # to prevent this, disable word wrapping for the path text:
        text.overflow = "ignore"

        yield text

    @group()
    def _render_syntax_error(self, syntax_error: _SyntaxError) -> RenderResult:
        yield Panel(
            "",
            title="[traceback.title]Syntax error",
            box=TRACEBACK_TOP_BOX,
            style=self.theme.get_background_style(),
            border_style="traceback.border",
            expand=True,
            width=self.width,
        )

        highlighter = ReprHighlighter()
        if syntax_error.filename != "<stdin>":
            if os.path.exists(syntax_error.filename):
                text = Text.assemble(
                    (f"{syntax_error.filename}", "pygments.string"),
                    (":", "pygments.text"),
                    (str(syntax_error.lineno), "pygments.number"),
                    style="pygments.text",
                )
                yield self._render_path(syntax_error.filename, syntax_error.lineno)

        syntax_error_text = highlighter(syntax_error.line.rstrip())
        syntax_error_text.no_wrap = True
        offset = min(syntax_error.offset - 1, len(syntax_error_text))
        syntax_error_text.stylize("bold underline", offset, offset)
        syntax_error_text += Text.from_markup(
            "\n" + " " * offset + "[traceback.offset]▲[/]",
            style="pygments.text",
        )

        background_style = None  # theme.get_background_style()
        yield Panel(
            syntax_error_text,
            box=TRACEBACK_BOTTOM_BOX,
            style=self.theme.get_background_style(),
            border_style="traceback.border",
            expand=True,
            width=self.width,
        )

    def _check_should_suppress(self, frame_filename: str):
        """Check if a frame should be suppressed based on its filename.

        Args:
            frame_filename (str): Frame's filename.
        """

        for suppress_entity in self.suppress:
            assert isinstance(
                suppress_entity, (str, Path)
            ), f"{suppress_entity!r} must be a string or a file path"

            if isinstance(suppress_entity, Path):
                if frame_filename.startswith(str(suppress_entity)):
                    return True

            if isinstance(suppress_entity, str):
                suppress_entity = suppress_entity.replace(".", "/")
                frame_filename = (
                    frame_filename.removesuffix(".py")
                    .removesuffix("__init__")
                    .removesuffix("/")
                    .removesuffix("\\")
                )
                if f"/{suppress_entity}" in frame_filename:
                    return True

        return False

    @group()
    def _render_stack(self, stack: Stack) -> RenderResult:
        theme = self.theme

        def read_code(filename: str) -> str:
            """Read files, and cache results on filename.

            Args:
                filename (str): Filename to read

            Returns:
                str: Contents of file
            """
            return "".join(linecache.getlines(filename))

        def render_locals(frame: Frame) -> Iterable[ConsoleRenderable]:
            if frame.locals:
                yield render_scope(
                    frame.locals,
                    title="locals",
                    indent_guides=self.indent_guides,
                    max_length=self.locals_max_length,
                    max_string=self.locals_max_string,
                )

        exclude_frames: Optional[range] = None
        if self.max_frames != 0:
            exclude_frames = range(
                self.max_frames // 2,
                len(stack.frames) - self.max_frames // 2,
            )

        excluded = False
        for frame_index, frame in enumerate(stack.frames):
            is_first = frame_index == 0
            is_last = frame_index == len(stack.frames) - 1

            if is_first:
                description = Text.from_markup(
                    f"[traceback.error]Printed in "
                    f"thread [violet i]'{threading.current_thread().name}'[/] "
                    f"of process [purple i]'{multiprocessing.current_process().name}'[/]",
                    overflow="fold",
                )

                yield Panel(
                    description,
                    title="[traceback.title]Traceback [dim](most recent call last)",
                    box=TRACEBACK_TOP_BOX,
                    style=self.theme.get_background_style(),
                    border_style="traceback.border",
                    expand=True,
                    width=self.width,
                )

            if exclude_frames and (frame_index in exclude_frames):
                excluded = True
                continue

            if excluded:
                assert exclude_frames is not None
                yield Text(
                    f"\n... {len(exclude_frames)} frames hidden ...",
                    justify="center",
                    style="traceback.error",
                )
                excluded = False

            frame_filename = frame.filename
            suppressed = self._check_should_suppress(frame_filename)
            if is_last:
                suppressed = False  # <- always show the last frame

            frozen_module = frame.filename.startswith("<")

            if frozen_module:
                yield from render_locals(frame)
            else:
                if suppressed:
                    yield Text.from_markup("[traceback.border]┬")
                else:
                    panel_content = None
                    try:
                        code = read_code(frame.filename)
                        lexer_name = self._guess_lexer(frame.filename, code)
                        syntax = Syntax(
                            code,
                            lexer_name,
                            theme=theme,
                            line_numbers=True,
                            line_range=(
                                frame.lineno - self.extra_lines,
                                frame.lineno + self.extra_lines,
                            ),
                            highlight_lines={frame.lineno},
                            word_wrap=self.word_wrap,
                            code_width=88,
                            indent_guides=self.indent_guides,
                            dedent=False,
                        )
                        panel_content = (
                            Columns(
                                [
                                    syntax,
                                    *render_locals(frame),
                                ],
                                padding=1,
                            )
                            if frame.locals
                            else syntax
                        )
                    except Exception as error:
                        error_text = f"\nException message: {error}" if error else ""
                        panel_content = Text.from_markup(
                            f"[dim]Caught {type(error).__name__} when rendering code from '{frame.filename}'.{error_text}"
                        )
                    finally:
                        yield Panel(
                            panel_content,
                            title_align="center",
                            box=TRACEBACK_MIDDLE_BOX,
                            style=self.theme.get_background_style(),
                            border_style="traceback.border",
                            expand=True,
                            width=self.width,
                        )

            if os.path.exists(frame.filename):
                yield self._render_path(
                    frame.filename, frame.lineno, frame.name, suppressed
                )
            else:
                yield Text.assemble(
                    ("┬\n", "traceback.border"),
                    ("╰─▶", "traceback.border"),
                    " in ",
                    (frame.filename, "pygments.function"),
                )

            if is_last:
                yield ""

    @staticmethod
    def print_exception(
        *,
        console: Console | None = None,
        width: Optional[int] = 100,
        extra_lines: int = 3,
        theme: Optional[str] = None,
        word_wrap: bool = False,
        show_locals: bool = False,
        suppress: Iterable[Union[str, ModuleType]] = (),
        max_frames: int = 100,
    ) -> None:
        """
        Prints a charming render of the last exception and traceback.

        Notes:
            This is a replacement for Rich's built-in Console.print_exception() method which works with CharmingTraceback.

        Args:
            console: Console instance to print to. Defaults to the global Rich Console instance.
            width: Number of characters used to render code. Defaults to 100.
            extra_lines: Additional lines of code to render. Defaults to 3.
            theme: Override pygments theme used in traceback
            word_wrap: Enable word wrapping of long lines. Defaults to False.
            show_locals: Enable display of local variables. Defaults to False.
            suppress: Optional sequence of modules or paths to exclude from traceback.
            max_frames: Maximum number of frames to show in a traceback, 0 for no maximum. Defaults to 100.
        """
        if console is None:
            console = rich.get_console()

        traceback = CharmingTraceback(
            width=width,
            extra_lines=extra_lines,
            theme=theme,
            word_wrap=word_wrap,
            show_locals=show_locals,
            suppress=suppress,
            max_frames=max_frames,
        )
        console.print(traceback)
