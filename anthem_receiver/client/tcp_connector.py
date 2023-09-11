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
from asyncio import Future
from abc import ABC, abstractmethod

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT
from ..pkg_logging import logger
from ..protocol import Packet, PJ_OK, PJREQ, PJACK, PJNAK
from .connector import AnthemReceiverConnector
from .client_transport import (
    AnthemReceiverClientTransport,
    ResponsePackets
  )
from .client_config import AnthemReceiverClientConfig

from .tcp_client_transport import TcpAnthemReceiverClientTransport

class TcpAnthemReceiverConnector(AnthemReceiverConnector):
    """Anthem receiver TCP/IP client transport connector."""

    config: AnthemReceiverClientConfig

    def __init__(
            self,
            host: Optional[str]=None,
            password: Optional[str]=None,
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
                      SSDP to discover the receiver.
                      If None, the host will be taken from the
                        anthem_receiver_HOST environment variable.
                password:
                      The receiver password. If None, the password
                      will be taken from the anthem_receiver_PASSWORD
                      environment variable. If an empty string or the
                      environment variable is not found, no password
                      will be used.
                port: The default TCP/IP port number to use. If None, the port
                      will be taken from the anthem_receiver_PORT. If that
                      environment variable is not found, the default Anthem
                      receiver port (20554) will be used.
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
            password=password,
            base_config=config
          )
        host = self.config.default_host
        assert host is not None
        if '://' in host and not host.startswith('tcp://') and not host.startswith('dp://'):
            raise AnthemReceiverError(f"Invalid host protocol specifier for TCP transport: '{host}'")

    # @abstractmethod
    async def connect(self) -> AnthemReceiverClientTransport:
        """Create and initialize (including handshake and authentication)
           a TCP/IP client transport for the receiver associated with this
           connector.
        """
        transport = TcpAnthemReceiverClientTransport(config=self.config)
        await transport.connect()
        # on error, the transport will be shut down, and no further interaction is possible
        return transport

    def __str__(self) -> str:
        return f"TcpAnthemReceiverConnector(host='{self.config.default_host}', port={self.config.default_port})"

    def __repr__(self) -> str:
        return str(self)
