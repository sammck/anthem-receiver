# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver TCP/IP client transport.

Provides an implementation of AnthemReceiverClientTransport over a TCP/IP
socket.
"""

from __future__ import annotations

import asyncio
from asyncio import Future
import time

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT, STABLE_POWER_TIMEOUT
from ..pkg_logging import logger
from ..protocol import (
    Packet,
    AnthemModel,
    AnthemCommand,
    AnthemResponse,
    CommandMeta,
    models,
    name_to_command_meta,
    model_status_list_map,
  )
from .client_config import AnthemReceiverClientConfig

from .client_transport import AnthemReceiverClientTransport
from .tcp_client_transport import TcpAnthemReceiverClientTransport

POWER_POLL_INTERVAL = 0.5
"""Seconds between power status pools while waiting for power to stabilize (e.g.,
   waiting for warmup or cooldown)."""
class AnthemReceiverClient:
    """Anthem receiver TCP/IP client."""

    transport: AnthemReceiverClientTransport
    final_status: Future[None]

    config: AnthemReceiverClientConfig
    model: Optional[AnthemModel] = None
    stable_power_timeout: float

    model_status_query_command_meta = name_to_command_meta("model_status.query")


    def __init__(
            self,
            transport: AnthemReceiverClientTransport,
            model: Optional[AnthemModel]=None,
            stable_power_timeout_secs: float=STABLE_POWER_TIMEOUT,
            config: Optional[AnthemReceiverClientConfig]=None,
          ):
        """Initialize a Anthem receiver TCP/IP client."""
        self.config = AnthemReceiverClientConfig(
            model=model,
            stable_power_timeout_secs=stable_power_timeout_secs,
            base_config=config,
        )
        self.transport = transport
        self.model = self.config.model
        self.stable_power_timeout = self.config.stable_power_timeout_secs
        self.final_status = asyncio.get_event_loop().create_future()

    async def transact(
            self,
            command: AnthemCommand,
          ) -> AnthemResponse:
        """Sends a command and reads the response."""
        command_packet = command.command_packet
        basic_response_packet, advanced_response_packet = await self.transport.transact(command_packet)
        response = command.create_response_from_packets(
            basic_response_packet, advanced_response_packet)
        if self.model is None and command.name == "model_status.query":
            # if we don't know the receiver model, and we just got a model_status.query response,
            # then we can use the response to determine the model
            _, default_model = model_status_list_map[response.payload]
            self.model = default_model
        return response

    async def transact_by_name(
            self,
            command_name: str,
            payload: Optional[bytes]=None,
          ) -> AnthemResponse:
        """Sends a command and reads the response."""
        command = AnthemCommand.create_from_name(command_name, payload=payload)
        return await self.transact(command)


    async def _async_dispose(self) -> None:
        await self.transport.aclose()

    async def __aenter__(self) -> AnthemReceiverClient:
        logger.debug(f"{self}: Entering async context manager")
        return self

    async def __aexit__(
            self,
            exc_type: type[BaseException],
            exc_val: Optional[BaseException],
            exc_tb: TracebackType
          ) -> None:
        logger.debug(f"{self}: Exiting async context manager, exc={exc_val}")
        await self._async_dispose()

    async def cmd_null(self) -> AnthemResponse:
        """Send a null command."""
        return await self.transact_by_name("test_command.null_command")

    async def cmd_power_status(self) -> AnthemResponse:
        """Send a power status query command and returns the response.

        The friendly power status name is available with response.response_str().
        """
        return await self.transact_by_name("power_status.query")

    async def power_status_wait(self, stable_power_timeout: Optional[float]=None) -> AnthemResponse:
        """Waits for power to stabilize (e.g., not warming up or cooling down) and returns
           the final stable power status response.

           raises AnthemReceiverError if the power status does not stabilize within
              stable_power_timeout seconds. If stable_power_timeout is None, then
              the timeout provided at construction is used.

           The friendly power status name is available with response.response_str().
        """
        if stable_power_timeout is None:
            stable_power_timeout = self.stable_power_timeout
        first = True
        start_time = time.monotonic()
        while True:
            response = await self.cmd_power_status()
            if response.response_str() == "Warming":
                # warming up
                if first:
                    logger.debug(f"{self}: Waiting for receiver to warm up")
                    first = False
            elif response.response_str() == "Cooling":
                # cooling down
                if first:
                    logger.debug(f"{self}: Waiting for receiver to cool down")
                    first = False
            else:
                # stable power status
                return response
            remaining_timeout = stable_power_timeout - (time.monotonic() - start_time)
            if remaining_timeout <= 0:
                raise AnthemReceiverError(f"{self}: Power status did not stabilize within {stable_power_timeout} seconds")
            await asyncio.sleep(min(POWER_POLL_INTERVAL, remaining_timeout))

    async def cmd_power_on(self) -> AnthemResponse:
        """Send a power on command.

        Does not wait for the power to stabilize either before or after sending the command.

        NOTE: For some or all receivers (at least DLA-NZ8), this command will fail
              (the receiver will not send any response) if the receiver is not in "Standby" state.
              For a safe, reliable power-on command, use power_on_wait().
        """
        return await self.transact_by_name("power.on")

    async def power_on_wait(
            self,
            wait_for_final: bool=True,
            stable_power_timeout: Optional[float]=None
        ) -> AnthemResponse:
        """Turns the receiver on if it is not already on.

        If the receiver is cooling down, waits for it to finish cooling down before turning it on.
        If wait_for_final is True, waits for the receiver to finish warming up before returning.
        If wait_for_final is False, returns as soon as the receiver is either on or warming up.

        If the receiver is in "Emergency" mode, raises an exception.

        The friendly power status name at return time (either "On" or "Warming") is available
        with response.response_str().
        """
        response = await self.cmd_power_status()
        response_str = response.response_str()
        if response_str == "Cooling" or (response_str == "Warming" and wait_for_final):
            response = await self.power_status_wait(stable_power_timeout=stable_power_timeout)
            response_str = response.response_str()
        if response_str == "Standby":
            await self.cmd_power_on()
            if wait_for_final:
                response = await self.power_status_wait(stable_power_timeout=stable_power_timeout)
            else:
                response = await self.cmd_power_status()
            response_str = response.response_str()

        if response_str == "Emergency":
            raise AnthemReceiverError(f"{self}: Receiver is in Emergency mode")
        elif response_str not in ("On", "Warming"):
            raise AnthemReceiverError(f"{self}: Unexpected power status: {response_str}")

        return response

    async def cmd_power_off(self) -> AnthemResponse:
        """Send a power off command.

        Does not wait for the power to stabilize either before or after sending the command.

        NOTE: For some or all receivers (at least DLA-NZ8), this command will fail
              (the receiver will not send any response) if the receiver is not in "On" state.
              For a safe, reliable power-off command, use power_off_wait().
        """
        return await self.transact_by_name("power.off")

    async def power_off_wait(
            self,
            wait_for_final: bool=True,
            stable_power_timeout: Optional[float]=None
          ) -> AnthemResponse:
        """Turns the receiver off (Standby) if it is not already in "Standby".

        If the receiver is warming up, waits for it to finish warming up before turning it off.
        If wait_for_final is True, waits for the receiver to finish cooling down before returning.
        If wait_for_final is False, returns as soon as the receiver is either in Standby or cooling down.

        If the receiver is in "Emergency" mode, raises an exception.

        The friendly power status name at return time (either "On" or "Warming") is available
        with response.response_str().
        """
        response = await self.cmd_power_status()
        response_str = response.response_str()
        if response_str == "Warming" or (response_str == "Cooling" and wait_for_final):
            response = await self.power_status_wait(stable_power_timeout=stable_power_timeout)
            response_str = response.response_str()
        if response_str == "On":
            await self.cmd_power_off()
            if wait_for_final:
                response = await self.power_status_wait(stable_power_timeout=stable_power_timeout)
            else:
                response = await self.cmd_power_status()
            response_str = response.response_str()

        if response_str == "Emergency":
            raise AnthemReceiverError(f"{self}: Receiver is in Emergency mode")
        elif response_str not in ("Standby", "Cooling"):
            raise AnthemReceiverError(f"{self}: Unexpected power status: {response_str}")

        return response

    async def cmd_model_status(self) -> AnthemResponse:
        return await self.transact_by_name("model_status.query")

    def __str__(self) -> str:
        return f"AnthemReceiverClient(transport={self.transport})"

    def __repr__(self) -> str:
       return str(self)

    async def aclose(self) -> None:
       await self._async_dispose()
