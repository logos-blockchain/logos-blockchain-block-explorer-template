import asyncio


class ChainNotifier:
    """Wakes stream handlers when ingestion commits new blocks.

    Ingestion calls `publish()` after each commit. Streams remember the version
    they last saw and `wait_for_change()` until it moves (or a timeout passes,
    so a stream still re-checks the database occasionally). This replaces the
    old per-client polling of the database every second.
    """

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self.version = 0

    async def publish(self) -> None:
        async with self._condition:
            self.version += 1
            self._condition.notify_all()

    async def wait_for_change(self, seen_version: int, *, timeout: float) -> int:
        async with self._condition:
            try:
                await asyncio.wait_for(self._condition.wait_for(lambda: self.version != seen_version), timeout)
            except TimeoutError:
                pass
            return self.version
