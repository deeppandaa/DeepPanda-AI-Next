from __future__ import annotations

import asyncio
import os

from mcp.server.fastmcp import FastMCP

server = FastMCP("DeepPanda isolated continuity acceptance")
count = 0


@server.tool()
async def remember(value: str, slow: bool = False) -> dict:
    global count
    if value == "disconnect-fixture":
        os._exit(17)
    count += 1
    if slow:
        await asyncio.sleep(30)
    return {"count": count, "value": value, "pid": os.getpid()}


if __name__ == "__main__":
    server.run()
