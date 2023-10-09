# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver TCP/IP client connector.

Abstract base class for a connector that produces a BarePacketStreamTransport
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from abc import ABC, abstractmethod

from ..internal_types import *
from ..pkg_logging import logger
from ..protocol_impl import BarePacketStreamTransport


class BarePacketStreamConnector(ABC):
    """Abstract base class for a connector that produces a BarePacketStreamTransport."""

    @abstractmethod
    async def connect(self) -> BarePacketStreamTransport:
        """Create and initialize a new BarePacketStreamTransport.
        """
        ...

    def __str__(self) -> str:
        return f"BarePacketStreamConnector(host='{self.config.default_host}', port={self.config.default_port})"

    def __repr__(self) -> str:
        return str(self)
