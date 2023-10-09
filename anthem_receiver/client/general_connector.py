# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver multi-protocol client connector.

Provides general connector for a AnthemReceiverClientTransport over
supported transport protocols.
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

from .tcp_connector import TcpAnthemReceiverConnector
from .reconnect_client_transport import ReconnectAnthemReceiverClientTransport
from .client_config import AnthemReceiverClientConfig

class GeneralAnthemReceiverConnector(AnthemReceiverConnector):
    """General Anthem receiver client transport connector."""
    config: AnthemReceiverClientConfig
    child_connector: AnthemReceiverConnector

    def __init__(
            self,
            host: Optional[str]=None,
            password: Optional[str]=None,
            config: Optional[AnthemReceiverClientConfig]=None
          ) -> None:
        """Creates a connector that can create transports to
           a Anthem receiver over any supported transport protocol.

              Args:
                host: The hostname or IPV4 address of the receiver.
                      may optionally be prefixed with "tcp://".
                      May be suffixed with ":<port>" to specify a
                      non-default port, which will override the port argument.
                      May be "dp://" or "dp://<host>" to use
                      Anthem Discovery Protocol to discover the receiver.
                      If None, the host will be taken from the
                        ANTHEM_RECEIVER_HOST environment variable.
                password:
                        The password to use to authenticate with the receiver.
                        If None, the password will be taken from the
                        config.
                config: A AnthemReceiverClientConfig object that specifies
                        the default host, port, and password to use.
                        If None, a default config will be created.
        """
        super().__init__()
        self.config = AnthemReceiverClientConfig(
            default_host=host,
            password=password,
            base_config=config
        )
        host = self.config.default_host
        assert host is not None
        if not '://' in host or host.startswith('tcp://') or host.startswith('dp://'):
            self.child_connector = TcpAnthemReceiverConnector(
                config=self.config,
              )
        else:
            raise AnthemReceiverError(
                f"Unsupported protocol in host specifier: {host}"
              )

    # @abstractmethod
    async def connect(self) -> AnthemReceiverClientTransport:
        """Create and initialize (including handshake and authentication)
           a TCP/IP client transport for the receiver associated with this
           connector.
        """
        transport: AnthemReceiverClientTransport
        if self.config.auto_reconnect:
            transport = ReconnectAnthemReceiverClientTransport(
                connector=self.child_connector,
                config=self.config
              )
        else:
            transport = await self.child_connector.connect()
        return transport

    def __str__(self) -> str:
        return f"GeneralAnthemReceiverConnector({self.child_connector})"

    def __repr__(self) -> str:
        return str(self)
