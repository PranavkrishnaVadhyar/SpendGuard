"""Base interface for payment adapters.

Implementations can route an approved request through a virtual card checkout,
metered API proxy, cloud role, or agent payment rail. Policy decisions belong
to SpendGuard and must happen before an adapter is called.
"""


class Adapter:
    def execute(self, request: dict) -> dict:
        """Execute an already-approved request and return its receipt result."""
        raise NotImplementedError
