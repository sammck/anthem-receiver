# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Protocol-specific constants
"""

from __future__ import annotations

from enum import Enum
from ..internal_types import *
from ..exceptions import AnthemReceiverError

PACKET_MAGIC = b"\x89\x01"
"""The magic bytes that follow the packet type in all packets sent to or received from the receiver."""

END_OF_PACKET = 0x0a
"""The terminating byte value for all packets sent to or received from the receiver, as an int."""

END_OF_PACKET_BYTES = bytes([END_OF_PACKET])
"""The terminating byte for all packets sent to or received from the receiver,
   as a bytes object."""

MAX_PACKET_LENGTH = 256
"""The maximum length of a packet sent to or received from the receiver, in bytes."""

MIN_PACKET_LENGTH = 6
"""The minimum length of a packet sent to or received from the receiver, in bytes."""

class PacketType(Enum):
    """The first byte of a packet sent to or received from the receiver, identifying its type."""
    UNKNOWN = -1
    BASIC_COMMAND = 0x21
    ADVANCED_COMMAND = 0x3f
    BASIC_RESPONSE = 0x06
    ADVANCED_RESPONSE = 0x40


