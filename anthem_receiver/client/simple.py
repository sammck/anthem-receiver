# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver simple multi-protocol client connection API.

Provides a simple API for connection to a receiver over any transport.
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
from .client_config import AnthemReceiverClientConfig
from .client_impl import AnthemReceiverClient

from .general_connector import GeneralAnthemReceiverConnector

async def anthem_receiver_transport_connect(
        host: Optional[str]=None,
        password: Optional[str]=None,
        config: Optional[AnthemReceiverClientConfig]=None
      ) -> AnthemReceiverClientTransport:
    """Create and initialize (including handshake and authentication)
       a transport for a Anthem receiver from a configuration.

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
                The password to use to authenticate with the receiver.
                If None, the password will be taken from the
                config.
        config: A AnthemReceiverClientConfig object that specifies
                the default host, port, and password to use.
                If None, a default config will be created.
    """
    connector = GeneralAnthemReceiverConnector(
        host=host,
        password=password,
        config=config
      )
    transport = await connector.connect()
    return transport

async def anthem_receiver_connect(
        host: Optional[str]=None,
        password: Optional[str]=None,
        config: Optional[AnthemReceiverClientConfig]=None
      ) -> AnthemReceiverClient:
    """Create and initialize (including handshake and authentication)
       a Anthem receiver client from a configuration.

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
                The password to use to authenticate with the receiver.
                If None, the password will be taken from the
                config.
        config: A AnthemReceiverClientConfig object that specifies
                the default host, port, and password, etc. to use.
                If None, a default config will be created.
    """
    config = AnthemReceiverClientConfig(
        default_host=host,
        password=password,
        base_config=config
      )
    transport = await anthem_receiver_transport_connect(
        config=config
      )
    try:
        client = AnthemReceiverClient(
            transport=transport,
            config=config,
        )
    except BaseException:
        await transport.aclose()
        raise

    return client
