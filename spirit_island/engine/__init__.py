"""Spirit Island game engine: state, rules and step-by-step guidance.

Pure Python with no dependencies, so it can be tested and driven by either the
dashboard (taps) or the vision pipeline (observations).
"""

from .game import ActionError, Game, new_state  # noqa: F401
from .guide import describe  # noqa: F401
