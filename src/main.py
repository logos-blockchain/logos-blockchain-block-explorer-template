import asyncio
from os import getenv

import uvicorn
from dotenv import load_dotenv

from src.app import create_app
from logs import setup_logging


async def main():
    base_path = getenv("NBE_BASE_PATH", "").strip().rstrip("/")
    app = create_app(base_path)

    host = getenv("NBE_HOST", "0.0.0.0")
    port = int(getenv("NBE_PORT", 8000))
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        reload=False,
        loop="asyncio",
        log_config=None,
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    except KeyboardInterrupt:
        # Swallow debugger’s SIGINT
        pass


# Pycharm-Debuggable Uvicorn Server
if __name__ == "__main__":
    try:
        load_dotenv()
        setup_logging()
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful stop triggered by debugger/CTRL-C
        pass
