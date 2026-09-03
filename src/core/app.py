from asyncio import Task
from typing import Optional

from fastapi import FastAPI
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.datastructures import State

from constants import DIR_REPO
from core.authentication import Authentication
from db.blocks import BlockRepository
from db.channels import ChannelOperationRepository
from db.clients import DbClient
from core.notifier import ChainNotifier
from db.transaction import TransactionRepository
from node.api.http import HttpNodeApi

ENV_FILEPATH = DIR_REPO.joinpath(".env")


class NBESettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILEPATH, extra="ignore")

    node_api_host: str = Field(alias="NBE_NODE_API_HOST", default="127.0.0.1")
    node_api_port: int = Field(alias="NBE_NODE_API_PORT", default=8080)
    node_api_timeout: int = Field(alias="NBE_NODE_API_TIMEOUT", default=60)
    node_api_protocol: str = Field(alias="NBE_NODE_API_PROTOCOL", default="http")
    node_api_auth: Optional[Authentication] = Field(alias="NBE_NODE_API_AUTH", default=None)

    database_url: str = Field(alias="NBE_DATABASE_URL", default=f"sqlite:///{DIR_REPO}/sqlite.db")

    @field_validator("node_api_auth", mode="before")
    @classmethod
    def parse_auth(cls, value: str) -> Optional[Authentication]:
        if value is None:
            return None

        try:
            return Authentication.from_string(value)
        except Exception as e:
            raise ValueError(f"Invalid NBE_NODE_API_AUTH: {value}") from e


class NBEState(State):
    node_api: HttpNodeApi
    db_client: DbClient
    block_repository: BlockRepository
    transaction_repository: TransactionRepository
    channel_repository: ChannelOperationRepository
    chain_notifier: ChainNotifier
    subscription_to_updates_handle: Task


class NBE(FastAPI):
    state: NBEState
    settings: NBESettings

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = NBEState()
        self.settings = NBESettings()  # type: ignore[call-arg] # The missing parameter is filled from the env file
