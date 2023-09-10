# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Encapsulation of response packets for a multi_transact()
"""

from __future__ import annotations

import asyncio
from ..internal_types import *
from ..pkg_logging import logger

if TYPE_CHECKING:
    from .client_transport import ResponsePackets

class MultiResponsePackets:
    """An encapsulation of response packets to multiple commands
       run within a single multi_transact() call. If some
       commands succeed before the multi_transact fails, their
       responses will be available in the responses list.
    """
    responses: List[ResponsePackets]
    final_result: asyncio.Future[None]

    def __init__(self) -> None:
        self.responses = []
        self.final_result = asyncio.get_event_loop().create_future()

    def add_response(self, response: ResponsePackets) -> None:
        """Adds a response to the list of responses."""
        self.responses.append(response)

    def set_final_result(self, exc: Optional[BaseException]) -> None:
        """Sets the final result of the transaction."""
        if not self.final_result.done():
            if exc is None:
                self.final_result.set_result(None)
            else:
                self.final_result.set_exception(exc)

    async def wait(self) -> List[ResponsePackets]:
        """Waits for the final result of the multi-command transaction, and
           raises an exception if not all commands succeeded.

        If all commands succeeded, returns the list of responses.

        If any command failed, raises the exception that caused the failure.
        and subsequent commands are not attempted. The responses list will
        contain the responses to the commands that succeeded before the
        failure.
        """
        await self.final_result
        return self.responses

