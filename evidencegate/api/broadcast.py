"""Bounded, independent in-process result notification subscribers."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from evidencegate.api.models import ResultNotification, StreamGap


StreamMessage = ResultNotification | StreamGap


@dataclass(eq=False, slots=True)
class Subscription:
    queue: asyncio.Queue[ResultNotification]
    _gap_pending: bool = field(default=False, init=False)

    async def get(self) -> StreamMessage:
        if self._gap_pending:
            self._gap_pending = False
            return StreamGap()
        return await self.queue.get()

    def mark_gap(self) -> None:
        self._gap_pending = True
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return


class ResultBroadcaster:
    """Fan out hints without ever back-pressuring persistence or the runtime."""

    def __init__(self, queue_size: int = 100):
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.queue_size = queue_size
        self._subscribers: set[Subscription] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> Subscription:
        subscription = Subscription(asyncio.Queue(maxsize=self.queue_size))
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    def publish(self, notification: ResultNotification) -> None:
        for subscriber in tuple(self._subscribers):
            try:
                subscriber.queue.put_nowait(notification)
            except asyncio.QueueFull:
                subscriber.mark_gap()
