from asyncio import Task, gather
from typing import Literal, Optional

from fastapi import FastAPI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.datastructures import State

from constants import DIR_REPO
from db.blocks import BlockRepository
from db.clients import DbClient
from db.transaction import TransactionRepository
from node.api.base import NodeApi
from node.manager.base import NodeManager

ENV_FILEPATH = DIR_REPO.joinpath(".env")


class NBESettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILEPATH, extra="ignore")

    node_compose_filepath: Optional[str] = Field(alias="NBE_NODE_COMPOSE_FILEPATH", default=None)

    node_api: Literal["http", "fake"] = Field(alias="NBE_NODE_API", default="http")
    node_manager: Literal["docker", "noop"] = Field(alias="NBE_NODE_MANAGER", default="noop")

    node_api_host: str = Field(alias="NBE_NODE_API_HOST", default="127.0.0.1")
    node_api_port: int = Field(alias="NBE_NODE_API_PORT", default=18080)
    node_api_timeout: int = Field(alias="NBE_NODE_API_TIMEOUT", default=60)
    node_api_protocol: str = Field(alias="NBE_NODE_API_PROTOCOL", default="http")


class NBEState(State):
    signal_exit: bool = False  # TODO: asyncio.Event
    node_manager: Optional[NodeManager]
    node_api: Optional[NodeApi]
    db_client: DbClient
    block_repository: BlockRepository
    transaction_repository: TransactionRepository
    subscription_to_updates_handle: Task
    backfill_handle: Task

    @property
    def is_running(self) -> bool:
        return not self.signal_exit

    async def stop(self):
        self.signal_exit = True
        await self._wait_tasks_finished()

    async def _wait_tasks_finished(self):
        await gather(
            self.subscription_to_updates_handle,
            self.backfill_handle,
            return_exceptions=True,
        )


class NBE(FastAPI):
    state: NBEState
    settings: NBESettings

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = NBEState()
        self.settings = NBESettings()  # type: ignore[call-arg] # The missing parameter is filled from the env file
