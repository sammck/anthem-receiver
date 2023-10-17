# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Auto-reconnect Anthem receiver TCP/IP client transport.

Provides an implementation of AnthemReceiverClientTransport
that dynamically connects/disconnects/reconnects to another transport.
"""

from __future__ import annotations

import time
import asyncio
from asyncio import Future
from abc import ABC, abstractmethod

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT
from ..pkg_logging import logger
from ..protocol import RawPacket, PJ_OK, PJREQ, PJACK, PJNAK

from .connector import AnthemReceiverConnector
from .client_config import AnthemReceiverClientConfig
from .client_transport import (
    AnthemReceiverClientTransport,
    ResponsePackets
  )

from .resolve_host import resolve_receiver_tcp_host

class ReconnectAnthemReceiverClientTransport(AnthemReceiverClientTransport):
    """Anthem receiver client transport that automatically
       connects/disconnects/reconnects to another transport."""

    config: AnthemReceiverClientConfig

    connector: AnthemReceiverConnector
    """The connector to use to connect to the receiver."""

    current_transport: Optional[AnthemReceiverClientTransport] = None
    """The current transport, or None if not connected."""

    final_status: Future[None]
    """A future that will be set when the transport is closed."""

    _transaction_lock: asyncio.Lock
    """A mutex to ensure that only one transaction is in progress at a time;
    this allows multiple callers to use the same transport without worrying
    about mixing up response packets."""

    idle_timer_wakeup_queue: asyncio.Queue[None]
    is_timing_out: bool = False
    idle_timeout_task: Optional[asyncio.Task[None]] = None
    next_idle_monotonic_time: float = 0.0

    def __init__(
            self,
            connector: AnthemReceiverConnector,
            config: Optional[AnthemReceiverClientConfig]=None,
          ) -> None:
        """Initializes the transport."""
        super().__init__()
        self.config = AnthemReceiverClientConfig(base_config=config)
        self.connector = connector
        self.final_status = asyncio.get_event_loop().create_future()
        self._transaction_lock = asyncio.Lock()
        self.idle_timer_wakeup_queue = asyncio.Queue()

    # @abstractmethod
    def is_shutting_down(self) -> bool:
        """Returns True if the transport is shutting down or closed."""
        return self.final_status.done()

    async def get_connected_transport(self) -> AnthemReceiverClientTransport:
        """Returns the current transport, or connects if not connected.
        """
        if self.is_shutting_down():
            raise AnthemReceiverError("Transport is shutting down")
        if self.current_transport is not None and self.current_transport.is_shutting_down():
            self.cancel_idle_timer()
            try:
                await self.current_transport.wait()
            except BaseException:
                pass
            self.current_transport = None

        if self.current_transport is None:
            self.current_transport = await self.connector.connect()
            await self.restart_idle_timer()

        return self.current_transport

    def cancel_idle_timer(self) -> None:
        """Cancels the idle timer on the current transport."""
        self.is_timing_out = False

    async def restart_idle_timer(self) -> None:
        """Restarts the idle timer on the current transport."""
        self.is_timing_out = False
        if self.current_transport is not None and not self.is_shutting_down():
            self.is_timing_out = True
            self.next_idle_monotonic_time = time.monotonic() + self.config.idle_disconnect_secs
            if self.idle_timeout_task is None:
                self.idle_timeout_task = asyncio.get_event_loop().create_task(self._idle_timeout_func())
            else:
                self.idle_timer_wakeup_queue.put_nowait(None)

    async def _idle_timeout_func(self) -> None:
        """The idle timeout task."""
        while not self.is_shutting_down():
            if self.is_timing_out:
                remaining_time = self.next_idle_monotonic_time - time.monotonic()
                if remaining_time <= 0.0:
                    # Idle timeout has expired; close the current transport
                    self.is_timing_out = False
                    if self.current_transport is not None:
                        logger.debug("Idle timeout; closing receiver transport")
                        await self.current_transport.shutdown()
                else:
                    try:
                       # Timing out with remaining_time idle seconds remaining;
                       # expiration, restart_idle_timer(), or shutdown() will wake us up
                        await asyncio.wait_for(
                            self.idle_timer_wakeup_queue.get(), timeout=remaining_time
                          )
                    except asyncio.TimeoutError:
                        pass
            else:
                # Not timing out; restart_idle_timer() or shutdown() will wake us up
                await self.idle_timer_wakeup_queue.get()

    # @abstractmethod
    async def begin_transaction(self) -> None:
        """Acquires the transaction lock.
        """
        await self._transaction_lock.acquire()

    # @abstractmethod
    async def end_transaction(self) -> None:
        """Releases the transaction lock.
        """
        self._transaction_lock.release()

    # @abstractmethod
    async def transact_no_lock(
            self,
            command_packet: RawPacket,
          ) -> ResponsePackets:
        """Sends a command packet and reads the response packet(s).

        The first response packet is the basic response. The second response
        packet is the advanced response, if any.

        The caller must be holding the transaction lock. Ordinary users
        should use the transaction() context manager or call transact()
        instead.
        """
        transport = await self.get_connected_transport()
        try:
            self.cancel_idle_timer()
            result = await transport.transact(command_packet)
        finally:
            await self.restart_idle_timer()

        return result

    # @abstractmethod
    async def shutdown(self, exc: Optional[BaseException] = None) -> None:
        """Shuts the transport down. Does not wait for the transport to finish
           closing. Safe to call from a callback or with transaction lock.

        If exc is not None, sets the final status of the transport.

        Has no effect if the transport is already shutting down or closed.

        Does not raise an exception based on final status.
        """
        if not self.final_status.done():
            if exc is not None:
                self.final_status.set_exception(exc)
            else:
                self.final_status.set_result(None)
        self.cancel_idle_timer()
        if self.idle_timeout_task is not None:
            self.idle_timer_wakeup_queue.put_nowait(None)
        if self.current_transport is not None:
            await self.current_transport.shutdown()
        if self.idle_timeout_task is not None:
            self.idle_timeout_task.cancel()

    # @abstractmethod
    async def wait(self) -> None:
        """Waits for complete shutdown/cleanup. Does not initiate shutdown.
        Not safe to call from a callback.

        Returns immediately if the transport is already closed.
        Raises an exception if the final status of the transport is an exception.
        """
        try:
            await self.final_status
        finally:
            if self.current_transport is not None:
                await self.current_transport.wait()
                self.current_transport = None

    # @override
    async def __aenter__(self) -> ReconnectAnthemReceiverClientTransport:
        """Enters a context that will close the transport on exit."""
        return self


    def __str__(self) -> str:
        if self.current_transport is not None:
            result = f"ReconnectAnthemReceiverClientTransport({self.current_transport})"
        else:
            result = f"ReconnectAnthemReceiverClientTransport({self.connector})"
        return result

    def __repr__(self) -> str:
        return str(self)
