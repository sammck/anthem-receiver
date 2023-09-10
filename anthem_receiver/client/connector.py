# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver client abstract transport connectorinterface.

Provides a low-level abstract interface for objects that can create
trasport connections (including handshake and authentication)
to a Anthem receiver.
This abstraction allows for the implementation of proxies and alternate network
transports (e.g., HTTP).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..internal_types import *
from .client_transport import AnthemReceiverClientTransport
from .client_config import AnthemReceiverClientConfig

class AnthemReceiverConnector(ABC):
    """Abstract base class for Anthem receiver client transport connectors."""

    @abstractmethod
    async def connect(self) -> AnthemReceiverClientTransport:
        """Create and initialize (including handshake and authentication)
           a client transport for the receiver associated with this
           connector.

        Must be implemented by subclasses.
        """
        raise NotImplementedError()
