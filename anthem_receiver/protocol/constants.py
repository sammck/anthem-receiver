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

END_OF_PACKET = ord(';')
"""The terminating byte value for all packets sent to or received from the receiver, as an int."""

END_OF_PACKET_BYTES = bytes([END_OF_PACKET])
"""The terminating byte for all Anthem packets sent to or received from the receiver,
   as a bytes object."""

MAX_PACKET_LENGTH = 255
"""The maximum length of a, Anthem packet sent to or received from the receiver, in bytes.
   Does not include the ';' packet delimiter"""
