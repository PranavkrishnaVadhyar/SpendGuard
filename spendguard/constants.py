"""Public lifecycle states shared by the core and integrations."""

STATUSES = ("allowed", "executing", "settled", "failed", "denied",
            "pending_approval", "approved", "rejected", "expired", "cancelled")
TERMINAL = ("settled", "failed", "denied", "rejected", "expired", "cancelled")
RESERVING = ("allowed", "executing", "pending_approval", "approved")
