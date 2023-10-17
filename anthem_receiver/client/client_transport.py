# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver client abstract transport interface.

Provides a low-level abstract interface for sending opaque command packets
to a Anthem receiver and receiving opaque response packets. Does not provide session
establishment, handshake or authentication. Does not provide any higher-level
abstractions such as semantic commands or responses.

This abstraction allows for the implementation of proxies and alternate network
transports (e.g., HTTP).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from ..internal_types import *
from ..pkg_logging import logger
from ..protocol import RawPacket
from .multi_response_packets import MultiResponsePackets

from .client_transport_transaction import AnthemReceiverClientTransportTransaction

ResponsePackets = Tuple[RawPacket, Optional[RawPacket]]
"""A tuple of (basic_response: RawPacket, advanced_response: Optional[RawPacket]). If the response
   is to a basic command, advanced_response will be None."""

class AnthemReceiverClientTransport(ABC):
    """Abstract base class for Anthem receiver client transports."""

    @abstractmethod
    async def begin_transaction(self) -> None:
        """Acquires the transaction lock.

        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    @abstractmethod
    async def end_transaction(self) -> None:
        """Releases the transaction lock.

        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    def transaction(self) -> AnthemReceiverClientTransportTransaction:
        """Returns an async context manager that while entered will
           hold the transaction lock for this transport and provide
           a safe transact() method.

        Note that some transports (e.g., HTTP) may forcibly release
        the transaction lock if no commands are sent for a period of time.
        The caller should minimize the amount of time spent in the
        transaction context.

        Example:

           async with transport.transaction() as transaction:
               response1 = await transaction.transact(command_packet1)
               response2 = await transaction.transact(command_packet2)
        """
        return AnthemReceiverClientTransportTransaction(self)

    @abstractmethod
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

        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    async def multi_transact_no_lock(
            self,
            command_packets: Iterable[RawPacket],
          ) -> MultiResponsePackets:
        """Sends multiple command packets and reads all response packet(s),
           encapsulating them in MultiResponsePackets.

        Does not raise an exception if some commands fail. Instead, the
        exception is stored in the MultiResponsePackets object. The caller
        should call wait() on the MultiResponsePackets object to rethrow
        the exception if desired. Any commands that succeeded before the
        failure will have their responses available in the responses list.

        The caller must be holding the transaction lock. Ordinary users
        should use the transaction() context manager or call multi_transact()
        instead.

        The default implementation simply calls transact_no_lock() for each
        command packet in turn. Subclasses may override this method to
        provide a more efficient implementation.
        """
        multi_response = MultiResponsePackets()
        try:
            for command_packet in command_packets:
                response = await self.transact_no_lock(command_packet)
                multi_response.add_response(response)
            multi_response.set_final_result(None)
        except BaseException as exc:
            logger.debug("multi_transact: failed: %s", exc)
            multi_response.set_final_result(exc)
        return multi_response

    async def transact(
            self,
            command_packet: RawPacket,
          ) -> Tuple[RawPacket, Optional[RawPacket]]:
        """Sends a command packet and reads the response packet(s).

        The first response packet is the basic response. The second response
        packet is the advanced response, if any.

        A transaction lock is held during the transaction to ensure that only one transaction
        is in progress at a time.
        """
        async with self.transaction() as transaction:
            return await transaction.transact(command_packet)

    async def multi_transact(
            self,
            command_packets: Iterable[RawPacket],
          ) -> MultiResponsePackets:
        """Sends multiple command packets and reads all response packet(s),
           encapsulating them in MultiResponsePackets.

        Does not raise an exception if some commands fail. Instead, the
        exception is stored in the MultiResponsePackets object. The caller
        should call wait() on the MultiResponsePackets object to rethrow
        the exception if desired. Any commands that succeeded before the
        failure will have their responses available in the responses list.
        """
        async with self.transaction() as transaction:
            return await transaction.multi_transact(command_packets)

    @abstractmethod
    def is_shutting_down(self) -> bool:
        """Returns True if the transport is shutting down or closed."""
        raise NotImplementedError()

    @abstractmethod
    async def shutdown(self, exc: Optional[BaseException] = None) -> None:
        """Shuts the transport down. Does not wait for the transport to finish
           closing. Safe to call from a callback.

        If exc is not None, sets the final status of the transport.

        Has no effect if the transport is already shutting down or closed.

        Does not raise an exception based on final status.

        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    @abstractmethod
    async def wait(self) -> None:
        """Waits for complete shutdown/cleanup. Does not initiate shutdown
        Not safe to call from a callback.

        Returns immediately if the transport is already closed.
        Raises an exception if the final status of the transport is an exception.

        Must be implemented by a subclass.
        """
        raise NotImplementedError()

    # @overridable
    async def aclose(self, exc: Optional[BaseException] = None) -> None:
        """Closes the transport and waits for complete shutdown/cleanup.
        Not safe to call from a callback.

        If exc is not None, sets the final status of the transport.

        Has no effect if the transport is already closed.

        Raises an exception if the final status of the transport is an exception.

        May be overridden by subclasses. The default implementation simply calls
        shutdown() and then wait().
        """
        await self.shutdown(exc)
        await self.wait()

    async def __aenter__(self) -> AnthemReceiverClientTransport:
        """Enters a context that will close the transport on exit."""
        return self

    async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType],
          ) -> None:
        """Exits the context, closes the transport, and waits for complete shutdown/cleanup."""
        # Close the transport without raising an exception
        closer: asyncio.Task[None] = asyncio.ensure_future(self.aclose(exc))
        assert isinstance(closer, asyncio.Task)
        done, pending = await asyncio.wait([closer])
        assert len(done) == 1 and len(pending) == 0
        if exc is None:
            # raise the exception from the transport if there is one
            closer.result()

