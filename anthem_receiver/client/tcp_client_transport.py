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

import time
import asyncio
from asyncio import Future
from abc import ABC, abstractmethod

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT
from ..pkg_logging import logger
from ..protocol import Packet, PJ_OK, PJREQ, PJACK, PJNAK

from .client_config import AnthemReceiverClientConfig

from .client_transport import (
    AnthemReceiverClientTransport,
    ResponsePackets
  )

from .resolve_host import resolve_receiver_tcp_host

class TcpAnthemReceiverClientTransport(AnthemReceiverClientTransport):
    """Anthem receiver TCP/IP client transport."""

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    config: AnthemReceiverClientConfig
    resolved_host: str
    resolved_port: int
    final_status: Future[None]
    reader_closed: bool = False
    writer_closed: bool = False

    _transaction_lock: asyncio.Lock
    """A mutex to ensure that only one transaction is in progress at a time;
    this allows multiple callers to use the same transport without worrying
    about mixing up response packets."""


    def __init__(
            self,
            host: Optional[str]=None,
            password: Optional[str]=None,
            *,
            config: Optional[AnthemReceiverClientConfig]=None,
          ) -> None:
        """Initializes the transport.
        """
        super().__init__()
        self.config = AnthemReceiverClientConfig(
            default_host=host,
            password=password,
            base_config=config
        )
        assert self.config.default_host is not None
        assert self.config.default_port is not None
        self.resolved_host = self.config.default_host
        self.resolved_port = self.config.default_port
        self.final_status = asyncio.get_event_loop().create_future()
        self._transaction_lock = asyncio.Lock()

    @property
    def host_string(self) -> str:
        """Returns the unresolved host string."""
        result = self.config.default_host
        assert result is not None
        return result

    @property
    def host(self) -> str:
        """Returns the resolved TCP/IP host. Before connect() this will be the host string,"""
        return self.resolved_host

    @property
    def port(self) -> int:
        """Returns the resolved TCP/IP port. Before connect() this will be the default port."""
        return self.resolved_port

    @property
    def password(self) -> Optional[str]:
        """Returns the password."""
        return self.config.password

    @property
    def timeout_secs(self) -> float:
        """Returns the timeout in seconds."""
        return self.config.timeout_secs

    # @abstractmethod
    def is_shutting_down(self) -> bool:
        """Returns True if the transport is shutting down or closed."""
        return self.final_status.done()

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

    async def _read_response_packet(self) -> Packet:
        """Reads a single response packet from the receiver, with timeout (nonlocking).

        All packets end in b'\n' (0x0a). Not usable for initial handshake
        and authentication.

        On error, the transport will be shut down, and no further interaction is possible.
        """
        assert self.reader is not None

        try:
            packet_bytes = await asyncio.wait_for(self.reader.readline(), self.timeout_secs)
            logger.debug(f"Read packet bytes: {packet_bytes.hex(' ')}")
            if len(packet_bytes) == 0:
                raise AnthemReceiverError("Connection closed by receiver while waiting for response")
            if packet_bytes[-1] != 0x0a:
                raise AnthemReceiverError(f"Connection closed by receiver with partial response packet: {packet_bytes.hex(' ')}")
            try:
                result = Packet(packet_bytes)
                result.validate()
            except Exception as e:
                raise AnthemReceiverError(f"Invalid response packet received from receiver: {packet_bytes.hex(' ')}") from e
            if not result.is_response:
                raise AnthemReceiverError(f"Received packet is not a response: {result}")
        except Exception as e:
            await self.shutdown(e)
            raise
        return result

    async def read_response_packet(self) -> Packet:
        """Reads a single response packet from the receiver, with timeout.

        All packets end in b'\n' (0x0a). Not usable for initial handshake
        and authentication.

        On error, the transport will be shut down, and no further interaction is possible.
        """
        async with self._transaction_lock:
            return await self._read_response_packet()

    async def _read_response_packets(self, command_code: bytes, is_advanced: bool=False) -> ResponsePackets:
        """Reads a basic response packet and an optional advanced response packet (nonlocking).

        On error, the transport will be shut down, and no further interaction is possible.
        """
        try:
            basic_response_packet = await self._read_response_packet()
            advanced_response_packet: Optional[Packet] = None
            if basic_response_packet.command_code != command_code:
                raise AnthemReceiverError(f"Received response packet for wrong command code (expected {command_code.hex(' ')}): {basic_response_packet}")
            if basic_response_packet.is_advanced_response:
                raise AnthemReceiverError(f"Received advanced response packet before basic response packet: {basic_response_packet}")
            if is_advanced:
                advanced_response_packet = await self._read_response_packet()
                if advanced_response_packet.command_code != command_code:
                    raise AnthemReceiverError(f"Received second response packet for wrong command code (expected {command_code.hex(' ')}): {advanced_response_packet}")
                if not advanced_response_packet.is_advanced_response:
                    raise AnthemReceiverError(f"Received second basic response packet instead of advanced response packet: {advanced_response_packet}")
        except Exception as e:
            await self.shutdown(e)
            raise
        return (basic_response_packet, advanced_response_packet)

    async def read_response_packets(self, command_code: bytes, is_advanced: bool=False) -> Tuple[Packet, Optional[Packet]]:
        """Reads a basic response packet and an optional advanced response packet.

        On error, the transport will be shut down, and no further interaction is possible.
        """
        async with self._transaction_lock:
            return await self._read_response_packets(command_code, is_advanced=is_advanced)

    async def _read_exactly(self, length: int) -> bytes:
        """Reads exactly the specified number of bytes from the receiver, with timeout (nonlocking).

        Usable for initial handshake and authentication which do not terminate
        exchanges with b'\n' (0x0a).

        On error, the transport will be shut down, and no further interaction is possible.
        """
        assert self.reader is not None

        try:
            data = await asyncio.wait_for(self.reader.readexactly(length), self.timeout_secs)
            logger.debug(f"Read exactly {len(data)} bytes: {data.hex(' ')}")
        except Exception as e:
            await self.shutdown(e)
            raise
        return data

    async def read_exactly(self, length: int) -> bytes:
        """Reads exactly the specified number of bytes from the receiver, with timeout.

        Usable for initial handshake and authentication which do not terminate
        exchanges with b'\n' (0x0a).

        On error, the transport will be shut down, and no further interaction is possible.
        """
        async with self._transaction_lock:
            return await self._read_exactly(length)

    async def _write_exactly(self, data: bytes | bytearray | memoryview) -> None:
        """Writes exactly the specified number of bytes to the receiver, with timeout (nonlocking).

        On error, the transport will be shut down, and no further interaction is possible.
        """
        assert self.writer is not None

        try:
            logger.debug(f"Writing exactly {len(data)} bytes: {data.hex(' ')}")
            self.writer.write(data)
            await asyncio.wait_for(self.writer.drain(), self.timeout_secs)
        except Exception as e:
            await self.shutdown(e)
            raise

    async def write_exactly(self, data: bytes | bytearray | memoryview) -> None:
        """Writes exactly the specified number of bytes to the receiver, with timeout.

        On error, the transport will be shut down, and no further interaction is possible.
        """
        async with self._transaction_lock:
            await self._write_exactly(data)

    async def _send_packet(self, packet: Packet) -> None:
        """Sends a single command packet to the receiver, with timeout (nonlocking).

        On error, the transport will be shut down, and no further interaction is possible.
        """
        await self._write_exactly(packet.raw_data)

    async def send_packet(self, packet: Packet) -> None:
        """Sends a single command packet to the receiver, with timeout.

        On error, the transport will be shut down, and no further interaction is possible.
        """
        async with self._transaction_lock:
            await self._send_packet(packet)

    # @abstractmethod
    async def transact_no_lock(
            self,
            command_packet: Packet,
          ) -> ResponsePackets:
        """Sends a command packet and reads the response packet(s).

        The first response packet is the basic response. The second response
        packet is the advanced response, if any.

        The caller must be holding the transaction lock. Ordinary users
        should use the transaction() context manager or call transact()
        instead.
        """
        await self._send_packet(command_packet)
        basic_response_packet, advanced_response_packet = await self._read_response_packets(
            command_packet.command_code, command_packet.is_advanced_command)
        return (basic_response_packet, advanced_response_packet)

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
        try:
            if not self.reader_closed:
                self.reader_closed = True
                if self.reader is not None:
                    self.reader.feed_eof()
        except Exception as e:
            logger.debug("Exception while closing reader", exc_info=True)
        finally:
            try:
                if not self.writer_closed:
                    self.writer_closed = True
                    if self.writer is not None:
                        self.writer.close()
                    # await self.writer.wait_closed()
            except Exception as e:
                logger.debug("Exception while closing writer", exc_info=True)

    # @abstractmethod
    async def wait(self) -> None:
        """Waits for complete shutdown/cleanup. Does not initiate shutdown.
        Not safe to call from a callback.

        Returns immediately if the transport is already closed.
        Raises an exception if the final status of the transport is an exception.
        """
        try:
            if self.writer is not None:
                await self.writer.wait_closed()
        except Exception as e:
            logger.debug("Exception while waiting for writer to close", exc_info=True)
            await self.shutdown(e)
        finally:
            if not self.final_status.done():
                await self.shutdown()
        await self.final_status

    # @override
    async def __aenter__(self) -> TcpAnthemReceiverClientTransport:
        """Enters a context that will close the transport on exit."""
        return self

    async def connect(self) -> None:
        """Connect to the receiver and authenticate/handshake, with timeout.
        """
        try:
            async with self._transaction_lock:
                try:
                    assert self.reader is None and self.writer is None
                    self.resolved_host, self.resolved_port, _ = await resolve_receiver_tcp_host(
                        config=self.config)
                    logger.debug(f"Connecting to receiver at {self.host}:{self.port}")
                    connect_end_time = time.monotonic() + self.config.connect_timeout_secs
                    while True:
                        next_retry_time = min(
                            connect_end_time,
                            time.monotonic() + self.config.connect_retry_interval_secs)
                        try:
                            wait_time = max(connect_end_time - time.monotonic(), 0.25)
                            logger.warning(f"Trying receiver connect to {self.host}:{self.port} with timeout={wait_time}")
                            self.reader, self.writer = await asyncio.wait_for(
                                asyncio.open_connection(self.host, self.port),
                                timeout=wait_time)
                            break
                        except ConnectionRefusedError as e:
                            # If the receiver is servicing another client, it will refuse
                            # the connection. We retry until the timeout expires.
                            if time.monotonic() >= connect_end_time:
                                raise
                            else:
                                retry_sleep_time = next_retry_time - time.monotonic()
                                if retry_sleep_time > 0:
                                    logger.debug(f"Connection refused, sleeping for {retry_sleep_time} seconds")
                                    await asyncio.sleep(retry_sleep_time)
                                logger.debug("Connection refused, retrying")
                        except asyncio.TimeoutError as e:
                            logger.debug("Timeout connecting to receiver")
                    # Perform the initial handshake. This is a bit weird, since the receiver
                    # sends a greeting, then we send a request, then the receiver sends an
                    # acknowledgement, but none of these include a terminating newline.
                    logger.debug(f"Receiver TCP connection established; Handshake: Waiting for greeting")
                    greeting = await self._read_exactly(len(PJ_OK))
                    if greeting != PJ_OK:
                        raise AnthemReceiverError(f"Handshake: Unexpected greeting (expected {PJ_OK.hex(' ')}): {greeting.hex(' ')}")
                    logger.debug(f"Handshake: Received greeting: {greeting.hex(' ')}")
                    # newer receivers (e.g., DLA-NX8) require a password to be appended to the PJREQ blob
                    # (with an underscore separator). Older receivers (e.g., DLA-X790) do not accept a password.
                    req_data = PJREQ
                    if not self.password is None and len(self.password) > 0:
                        req_data += b'_' + self.password.encode('utf-8')
                        logger.debug(f"Handshake: writing auth data: {PJREQ.hex(' ')} + _<password>")
                    else:
                        logger.debug(f"Handshake: writing hello data: {PJREQ.hex(' ')}")
                    await self._write_exactly(req_data)
                    pjack = await self._read_exactly(len(PJACK))
                    logger.debug(f"Handshake: Read exactly {len(pjack)} bytes: {pjack.hex(' ')}")
                    if pjack == PJNAK:
                        raise AnthemReceiverError(f"Handshake: Authentication failed (bad password?)")
                    elif pjack != PJACK:
                        raise AnthemReceiverError(f"Handshake: Unexpected ack (expected {PJACK.hex(' ')}): {pjack.hex(' ')}")
                    logger.info(f"Handshake: {self} connected and authenticated")
                except BaseException as e:
                    await self.shutdown(e)
                    raise
        except BaseException as e:
            await self.aclose(e)
            raise

    def __str__(self) -> str:
        return f"TcpAnthemReceiverClientTransport({self.host}:{self.port})"

    def __repr__(self) -> str:
        return str(self)
