# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver TCP/IP client connector.

Provides an connector for a AnthemReceiverClientTransport over a TCP/IP
socket.
"""

from __future__ import annotations

import os
import asyncio
import time
from asyncio import Future
from abc import ABC, abstractmethod

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..pkg_logging import logger
from ..protocol_impl import BarePacketStreamTransport
from .client_config import AnthemReceiverClientConfig
from .bare_packet_stream_connector import BarePacketStreamConnector
from .resolve_host import resolve_receiver_tcp_host
from ..protocol_impl import BarePacketStreamTransport

class TcpBarePacketStreamConnector(BarePacketStreamConnector):
    """Anthem receiver TCP/IP client bare packet transport connector."""

    config: AnthemReceiverClientConfig

    def __init__(
            self,
            host: Optional[str]=None,
            port: Optional[int]=None,
            timeout_secs: Optional[float] = None,
            config: Optional[AnthemReceiverClientConfig]=None,
          ) -> None:
        """Creates a connector that can create transports to
           a Anthem receiver that is reachable over TCP/IP.

              Args:
                host: The hostname or IPV4 address of the receiver.
                      may optionally be prefixed with "tcp://".
                      May be suffixed with ":<port>" to specify a
                      non-default port, which will override the port argument.
                      May be "dp://" or "dp://<host>" to use
                      Anthem Discovery Protocol to discover the receiver.
                      If None, the host will be taken from the
                        ANTHEM_RECEIVER_HOST environment variable.
                port: The default TCP/IP port number to use. If None, the port
                      will be taken from the ANTHEM_RECEIVER_PORT. If that
                      environment variable is not found, the default Anthem
                      receiver port (14999) will be used.
                timeout_secs: The default timeout for operations on the
                        transport. If not provided, DEFAULT_TIMEOUT (2 seconds)
                        is used.
                config: A AnthemReceiverClientConfig object that specifies
                        the default host, port, password, etc to use.
                        If None, a default config will be created.
        """
        super().__init__()
        self.config = AnthemReceiverClientConfig(
            default_host=host,
            default_port=port,
            timeout_secs=timeout_secs,
            base_config=config
          )
        host = self.config.default_host
        assert host is not None
        if '://' in host and not host.startswith('tcp://') and not host.startswith('dp://'):
            raise AnthemReceiverError(f"Invalid host protocol specifier for TCP transport: '{host}'")

    # @abstractmethod
    async def connect(self) -> BarePacketStreamTransport:
        """Create and initialize (including handshake and authentication)
           a TCP/IP client transport for the receiver associated with this
           connector.
        """

        resolved_host, resolved_port, _ = await resolve_receiver_tcp_host(
            config=self.config)
        logger.debug(f"Connecting to receiver at {resolved_host}:{resolved_port}")
        connect_end_time = time.monotonic() + self.config.connect_timeout_secs
        while True:
            next_retry_time = min(
                connect_end_time,
                time.monotonic() + self.config.connect_retry_interval_secs)
            try:
                wait_time = max(connect_end_time - time.monotonic(), 0.25)
                logger.info(f"Trying receiver connect to {resolved_host}:{resolved_port} with timeout={wait_time}")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(resolved_host, resolved_port),
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

        transport = BarePacketStreamTransport(reader, writer)
        return transport

    def __str__(self) -> str:
        return f"TcpBarePacketStreamConnector(host='{self.config.default_host}', port={self.config.default_port})"

    def __repr__(self) -> str:
        return str(self)
