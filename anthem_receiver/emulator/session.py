# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver emulator.

Provides a simple emulation of a Anthem receiver on TCP/IP.
"""

from __future__ import annotations

import asyncio
from enum import Enum

from ..internal_types import *
from ..pkg_logging import logger
from ..protocol import (
    RawPacket,
    PJ_OK,
    PJREQ,
    PJACK,
    PJNAK,
    END_OF_PACKET_BYTES,
  )
from ..constants import DEFAULT_PORT

if TYPE_CHECKING:
    from .emulator_impl import AnthemReceiverEmulator

HANDSHAKE_TIMEOUT = 5.0
"""Timeout for the initial handshake."""

IDLE_TIMEOUT = 30.0
"""Timeout for idle connections, after handshake."""

class EmulatorSessionState(Enum):
    UNCONNECTED = 0
    SENDING_GREETING = 1
    READING_AUTHENTICATION = 2
    SENDING_AUTH_ACK = 3
    SENDING_AUTH_NAK = 4
    READING_COMMAND = 5
    RUNNING_COMMAND = 6
    SENDING_RESPONSE = 7
    SHUTTING_DOWN = 8
    CLOSED = 9

class AnthemReceiverEmulatorSession(asyncio.Protocol):
    session_id: int = -1
    emulator: AnthemReceiverEmulator
    transport: Optional[asyncio.Transport] = None
    peer_name: str = "<unconnected>"
    description: str = "EmulatorSession(<unconnected>)"
    state: EmulatorSessionState = EmulatorSessionState.UNCONNECTED
    partial_data: bytes = b""
    transport_closed: bool = True
    auth_timer: Optional[asyncio.TimerHandle] = None
    idle_timer: Optional[asyncio.TimerHandle] = None

    def __init__(self, emulator: AnthemReceiverEmulator):
        self.emulator = emulator
        self.session_id = emulator.alloc_session_id(self)
        self.description = f"EmulatorSession(id={self.session_id}, from=<unconnected>)"

    @property
    def password(self) -> Optional[str]:
        return self.emulator.password

    def write(self, data: Union[bytes, bytearray, memoryview]) -> None:
        if self.transport is None:
            logger.debug(f"EmulatorSession: Attempt to write to closed session {self.description}; ignored")
            return
        self.transport.write(data)

    def connection_made(self, transport: asyncio.BaseTransport):
        """Called when a connection is made.

        The argument is the transport representing the pipe connection.
        To receive data, wait for data_received() calls.
        When the connection is closed, connection_lost() is called.
        """
        assert isinstance(transport, asyncio.Transport)
        assert self.state == EmulatorSessionState.UNCONNECTED
        self.transport = transport
        self.transport_closed = False
        self.peer_name = transport.get_extra_info('peername')
        self.description = f"EmulatorSession(id={self.session_id}, from='{self.peer_name}')"
        logger.debug(f"EmulatorSession: Connection from {self.peer_name}")
        self.state = EmulatorSessionState.SENDING_GREETING
        self.transport.write(PJ_OK)
        self.state = EmulatorSessionState.READING_AUTHENTICATION
        self.auth_timer = asyncio.get_running_loop().call_later(
            HANDSHAKE_TIMEOUT,
            lambda: self._on_auth_read_timeout())

    def close(self) -> None:
        if not self.state in (EmulatorSessionState.CLOSED, EmulatorSessionState.SHUTTING_DOWN):
            self.state = EmulatorSessionState.SHUTTING_DOWN
            if not self.transport_closed and not self.transport is None:
                self.transport_closed = True
                self.transport.close()
            self.state = EmulatorSessionState.CLOSED
            self.emulator.free_session_id(self.session_id)

    def _on_auth_read_timeout(self) -> None:
        assert not self.transport is None
        self.auth_timer = None
        if self.state == EmulatorSessionState.READING_AUTHENTICATION:
            logger.debug(f"{self}: Authentication timeout")
            self.state = EmulatorSessionState.SENDING_AUTH_NAK
            self.transport.write(PJNAK)
            self.close()

    def _on_idle_read_timeout(self) -> None:
        assert not self.transport is None
        self.idle_timer = None
        if self.state == EmulatorSessionState.READING_COMMAND:
            logger.debug(f"{self}: Idle timeout")
            self.close()

    def data_received(self, data: bytes) -> None:
        """Called when some data is received."""
        assert not self.transport is None
        try:
            self.partial_data += data
            i_eop = self.partial_data.find(END_OF_PACKET_BYTES)
            if self.state == EmulatorSessionState.READING_AUTHENTICATION:
                valid_auth_data = PJREQ
                password = self.password
                if not password is None and len(password) > 0:
                    valid_auth_data += b'_' + password.encode('utf-8')
                nb_auth = len(valid_auth_data)
                if len(self.partial_data) >= nb_auth or (0 <= i_eop < nb_auth):
                    if not self.auth_timer is None:
                        self.auth_timer.cancel()
                        self.auth_timer = None
                    if 0 <= i_eop < nb_auth:
                        auth_data = self.partial_data[:i_eop+1]
                    else:
                        auth_data = self.partial_data[:nb_auth]
                    self.partial_data = self.partial_data[len(auth_data):]
                    if auth_data == valid_auth_data:
                        logger.debug(f"{self}: Authentication successful")
                        self.state = EmulatorSessionState.SENDING_AUTH_ACK
                        self.transport.write(PJACK)
                        self.state = EmulatorSessionState.READING_COMMAND
                        self.idle_timer = asyncio.get_running_loop().call_later(
                            IDLE_TIMEOUT,
                            lambda: self._on_idle_read_timeout())
                    else:
                        logger.debug(f"{self}: Authentication failed")
                        self.state = EmulatorSessionState.SENDING_AUTH_NAK
                        self.transport.write(PJNAK)
                        self.close()
            elif i_eop >= 0 and self.state == EmulatorSessionState.READING_COMMAND:
                if not self.idle_timer is None:
                    self.idle_timer.cancel()
                    self.idle_timer = None
                packet_bytes = self.partial_data[:i_eop + 1]
                self.partial_data = self.partial_data[i_eop + 1:]
                packet = RawPacket(packet_bytes)
                self.state = EmulatorSessionState.RUNNING_COMMAND
                self.emulator.on_packet_received(self, packet)
                self.state = EmulatorSessionState.READING_COMMAND
                self.idle_timer = asyncio.get_running_loop().call_later(
                    IDLE_TIMEOUT,
                    lambda: self._on_idle_read_timeout())
        except BaseException as e:
            logger.exception(f"{self}: Exception while processing data: {e}")
            self.close()
            raise


    def connection_lost(self, exc: Optional[BaseException]) -> None:
        """Called when the connection is lost or closed.

        The argument is an exception object or None (the latter
        meaning a regular EOF is received or the connection was
        aborted or closed).
        """
        logger.debug(f"{self}: Connection lost, exception={exc}; closing connection")
        self.close()

    def eof_received(self) -> bool:
        """Called when the other end calls write_eof() or equivalent.

        If this returns a false value (including None), the transport
        will close itself.  If it returns a true value, closing the
        transport is up to the protocol.
        """
        logger.debug(f"{self}: EOF received; closing connection")
        self.close()
        return True

    def __str__(self) -> str:
        return self.description

    def __repr__(self) -> str:
        return str(self)
