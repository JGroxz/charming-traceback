# 🐍 Charming Traceback

[Rich][rich] [traceback][rich_traceback] adapted for [PyCharm IDE by JetBrains][pycharm].

### Differences from the original

- File paths are rendered in the format which allows PyCharm to automatically detect them as links.
- `CharmingTraceback`'s `suppress` argument accepts string module names in addition to paths and Python modules already supported by `RichTraceback`. 

## Installation

Install with `pip`:

```bash
pip install charming-traceback
```

## Usage

To install as the default traceback handler:

```python
from charming_traceback import install

install(show_locals=True)
```

To print the exception traceback manually:

```python
from charming_traceback import Traceback

try:
    do_something()
except Exception as e:
    Traceback.print_exception(show_locals=True)
```

Essentially, `CharmingTraceback` class is designed to be a drop-in replacement for `RichTraceback` from Rich. You can refer to the official [Rich traceback documentation][rich_traceback] for more usage info.

[rich]: https://github.com/Textualize/rich
[rich_traceback]: https://rich.readthedocs.io/en/stable/traceback.html
[pycharm]: https://www.jetbrains.com/pycharm/
