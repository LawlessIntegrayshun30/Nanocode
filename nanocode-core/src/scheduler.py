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
