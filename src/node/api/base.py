from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Optional

from node.api.serializers.block import BlockSerializer
from node.api.serializers.health import HealthSerializer
from node.api.serializers.info import InfoSerializer

if TYPE_CHECKING:
    from core.app import NBESettings


class NodeApi(ABC):
    @abstractmethod
    def __init__(self, _settings: "NBESettings"):
        pass

    @abstractmethod
    async def get_health(self) -> HealthSerializer:
        pass

    @abstractmethod
    async def get_info(self) -> InfoSerializer:
        pass

    @abstractmethod
    async def get_block_by_hash(self, block_hash: str) -> Optional[BlockSerializer]:
        pass

    @abstractmethod
    async def get_blocks_stream(self) -> AsyncIterator[BlockSerializer]:
        pass
