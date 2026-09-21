"""Reading an on/off switch out of the environment.

Several checks are held back unless a run opts into them: the samples that
spend credits, and the links that depend on somebody else's website being up.
They are all turned on the same way, from a workflow expression that yields
"true" or "false", so what counts as on is decided once here.
"""

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str) -> bool:
    """Whether an environment variable is set to something meaning yes."""
    return os.environ.get(name, "").strip().lower() in _TRUTHY
