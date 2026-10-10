"""SpendGuard: deterministic spend controls for agent tools."""

from .errors import InvalidState, NotFound, RequestDenied, SpendGuardError, UnknownAgent
from .guard import SpendGuard
from .models import Outcome, Policy, RequestRecord

__version__ = "0.1.0"
__all__ = ["SpendGuard", "Policy", "RequestRecord", "Outcome", "SpendGuardError",
           "UnknownAgent", "NotFound", "InvalidState", "RequestDenied", "__version__"]

try:
    from .tools import governed
except ImportError:
    pass
else:
    __all__.append("governed")
