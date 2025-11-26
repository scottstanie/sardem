# from . import dem
from . import loading, utils

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"
