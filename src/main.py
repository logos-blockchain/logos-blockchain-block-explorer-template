import asyncio

import uvicorn

from app import create_app
from core.settings import Settings, load_dotenv
from logs import setup_logging


async def main():
    settings = Settings.from_env()
    config = uvicorn.Config(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        loop="asyncio",
        log_config=None,
        # The NDJSON streams are held open indefinitely by browser tabs; without
        # a bound, uvicorn waits for them forever on SIGTERM.
        timeout_graceful_shutdown=5,
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    try:
        load_dotenv()
        setup_logging()
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful stop triggered by debugger/CTRL-C
        pass
