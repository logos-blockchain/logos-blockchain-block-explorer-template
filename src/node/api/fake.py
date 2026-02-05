from asyncio import sleep
from random import random
from typing import TYPE_CHECKING, AsyncIterator, Optional

from rusty_results import Some

from node.api.base import NodeApi
from node.api.serializers.block import BlockSerializer
from node.api.serializers.health import HealthSerializer
from node.api.serializers.info import InfoSerializer

if TYPE_CHECKING:
    from core.app import NBESettings


class FakeNodeApi(NodeApi):
    def __init__(self, _settings: "NBESettings"):
        self.current_slot: int = 0

    async def get_health(self) -> HealthSerializer:
        if random() < 0.1:
            return HealthSerializer.from_unhealthy()
        else:
            return HealthSerializer.from_healthy()

    async def get_info(self) -> InfoSerializer:
        return InfoSerializer(
            lib="0" * 64,
            tip="0" * 64,
            slot=self.current_slot,
            height=0,
            mode="Fake",
        )

    async def get_block_by_hash(self, block_hash: str) -> Optional[BlockSerializer]:
        # Fake API doesn't track blocks by hash
        return None

    async def get_blocks_stream(self) -> AsyncIterator[BlockSerializer]:
        while True:
            yield BlockSerializer.from_random(slot=Some(self.current_slot))
            self.current_slot += 1
            await sleep(3)
