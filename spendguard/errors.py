"""Public errors; request() returns a deny Outcome instead of raising."""


class SpendGuardError(Exception):
    """Base class for SpendGuard operation errors."""


class UnknownAgent(SpendGuardError):
    """The requested agent does not exist."""


class NotFound(SpendGuardError):
    """The requested record does not exist."""


class InvalidState(SpendGuardError):
    """The requested transition is not valid in the current state."""


class RequestDenied(SpendGuardError):
    """Optional tool wrappers raise this with the original outcome."""

    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome.reason)
