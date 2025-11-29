import random
from collections import deque
from typing import Optional


class FIFOScheduler:
    """Simple FIFO scheduler for rewrite frontiers."""

    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def push(self, term_id: str) -> None:
        self._queue.append(term_id)

    def pop(self) -> Optional[str]:
        if not self._queue:
            return None
        return self._queue.popleft()

    def clear(self) -> None:
        self._queue.clear()

    def pending(self) -> tuple[str, ...]:
        return tuple(self._queue)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._queue)


class LIFOScheduler:
    """LIFO scheduler that behaves like a stack for rewrite frontiers."""

    def __init__(self) -> None:
        self._stack: list[str] = []

    def push(self, term_id: str) -> None:
        self._stack.append(term_id)

    def pop(self) -> Optional[str]:
        if not self._stack:
            return None
        return self._stack.pop()

    def clear(self) -> None:
        self._stack.clear()

    def pending(self) -> tuple[str, ...]:
        return tuple(self._stack)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._stack)


class RandomScheduler:
    """Randomized scheduler with optional seeding for reproducibility."""

    def __init__(self, seed: Optional[int] = None, state: object | None = None) -> None:
        self._items: list[str] = []
        self._seed = seed
        self._rng = random.Random(seed)
        if state is not None:
            self._rng.setstate(state)

    def push(self, term_id: str) -> None:
        self._items.append(term_id)

    def pop(self) -> Optional[str]:
        if not self._items:
            return None
        idx = self._rng.randrange(len(self._items))
        return self._items.pop(idx)

    def clear(self) -> None:
        self._items.clear()

    def pending(self) -> tuple[str, ...]:
        return tuple(self._items)

    def state(self) -> object:
        return self._rng.getstate()

    def set_state(self, state: object) -> None:
        self._rng.setstate(state)

    @property
    def seed(self) -> Optional[int]:
        return self._seed

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._items)
