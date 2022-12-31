import asyncio
from typing import *
from aiohttp import ClientSession


async def get(url: str, session: ClientSession) -> bytes:
    """
    Get a *thing* from the given URL.
    """
    async with session.get(url) as response:
        return await response.read()


async def get_batch(urls: List[str], session: ClientSession) -> List[Tuple[str, bytes]]:
    """
    Get a batch of *thing*s from the given URLs.
    """
    responses = await asyncio.gather(*[get(url, session) for url in urls])
    return list(zip(urls, responses))
