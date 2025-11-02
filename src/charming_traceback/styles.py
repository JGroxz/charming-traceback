from rich.box import Box
from rich.style import Style

STYLES = {
    "traceback.error": Style(color="red", italic=True),
    "traceback.border.syntax_error": Style(color="bright_red"),
    "traceback.border": Style(color="blue"),
    "traceback.text": Style.null(),
    "traceback.title": Style(color="red", bold=True),
    "traceback.exc_type": Style(color="bright_red", bold=True),
    "traceback.exc_value": Style.null(),
    "traceback.offset": Style(color="bright_red", bold=True),
}

TRACEBACK_TOP_BOX = Box(
    """\
╭─┬╮
│ ││
├─┼┤
│ ││
├─┼┤
├─┼┤
│ ││
┴ ┴┴
"""
)

TRACEBACK_MIDDLE_BOX = Box(
    """\
┬ ┬┬
│ ││
├─┼┤
│ ││
├─┼┤
├─┼┤
│ ││
│ ┴┴
"""
)

TRACEBACK_BOTTOM_BOX = Box(
    """\
┬ ┬┬
│ ││
├─┼┤
│ ││
├─┼┤
├─┼┤
│ ││
╰─┴╯
"""
)
