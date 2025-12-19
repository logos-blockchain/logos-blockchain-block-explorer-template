import logging
from typing import TYPE_CHECKING, AsyncIterator, List, Optional
from urllib.parse import urljoin, urlunparse

import httpx
from pydantic import ValidationError
from rusty_results import Empty, Option, Some
from third_party import requests

from core.authentication import Authentication
from node.api.base import NodeApi
from node.api.serializers.block import BlockSerializer
from node.api.serializers.health import HealthSerializer

if TYPE_CHECKING:
    from core.app import NBESettings


logger = logging.getLogger(__name__)


class HttpNodeApi(NodeApi):
    # Paths can't have a leading slash since they are relative to the base URL
    ENDPOINT_INFO = "cryptarchia/info"
    ENDPOINT_TRANSACTIONS = "cryptarchia/transactions"
    ENDPOINT_BLOCKS = "cryptarchia/blocks"
    ENDPOINT_BLOCKS_STREAM = "cryptarchia/blocks/stream"

    def __init__(self, settings: "NBESettings"):
        self.host: str = settings.node_api_host
        self.port: int = settings.node_api_port
        self.protocol: str = settings.node_api_protocol or "http"
        self.timeout: int = settings.node_api_timeout or 60
        self.authentication: Option[Authentication] = (
            Some(settings.node_api_auth) if settings.node_api_auth else Empty()
        )

    @property
    def base_url(self) -> str:
        if "/" in self.host:
            host, path = self.host.split("/", 1)
            path = f"/{path}"
            if not path.endswith("/"):
                path += "/"
        else:
            host = self.host
            path = ""

        network_location = f"{host}:{self.port}" if self.port else host

        url = urlunparse(
            (
                self.protocol,
                network_location,
                path,
                # The following are unused but required
                "",  # Params
                "",  # Query
                "",  # Fragment
            )
        )
        return url

    async def get_health(self) -> HealthSerializer:
        url = urljoin(self.base_url, self.ENDPOINT_INFO)
        response = requests.get(url, auth=self.authentication, timeout=60)
        if response.status_code == 200:
            return HealthSerializer.from_healthy()
        else:
            return HealthSerializer.from_unhealthy()

    async def get_blocks(self, slot_from: int, slot_to: int) -> List[BlockSerializer]:
        query_string = f"slot_from={slot_from}&slot_to={slot_to}"
        endpoint = urljoin(self.base_url, self.ENDPOINT_BLOCKS)
        url = f"{endpoint}?{query_string}"
        response = requests.get(url, auth=self.authentication, timeout=60)
        python_json = response.json()
        blocks = [BlockSerializer.model_validate(item) for item in python_json]
        return blocks

    async def get_blocks_stream(self) -> AsyncIterator[BlockSerializer]:
        url = urljoin(self.base_url, self.ENDPOINT_BLOCKS_STREAM)
        auth = self.authentication.map(lambda _auth: _auth.for_httpx()).unwrap_or(None)
        async with httpx.AsyncClient(timeout=self.timeout, auth=auth) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()  # TODO: Result

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        block = BlockSerializer.model_validate_json(line)
                    except ValidationError as error:
                        logger.exception(error)
                        continue

                    logger.debug(f"Received new block from Node: {block}")
                    yield block
