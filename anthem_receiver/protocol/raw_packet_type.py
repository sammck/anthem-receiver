# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Protocol packet type enumeration
"""

from __future__ import annotations

from aenum import Enum as AEnum
from ..internal_types import *
from ..exceptions import AnthemReceiverError

class RawPacketType(AEnum):
    UNKNOWN                     = 0x00000000
    """Unknown packet type"""

    ANTHEM                      = 0x00000001
    """A raw Anthem packet. Does not include b';' delimiter."""

    INVALID_ANTHEM              = 0x00000002
    """An invalid Anthem protocol byte sequence. May include b';' delimiter.
       Primarily caused by packets longer than 255 bytes, or a byte stream that
       does not end in a semicolon. Clients that are not expecting this
       should treat it as a transport error or rude disconnect."""

    TRANSPORT_ERROR            = 0x00000003
    """A connection or read/write error occurred. Indicates that an attempt
       to connect, reconnect, read, or write failed.  `raw_data` contains a
       JSON-serialized object with a "message" property describing the reason
       for the error. Clients that are not expecting this should treat it as
       a transport error or rude disconnect."""

    SESSION_INTERRUPTED      = 0x00000003
    """The stateful session to the remote end was temporarily interrupted. Indicates
       that session state accumulated before this packet must be discarded and
       rebuilt as if there is a new connection. `raw_data` is not used. Clients
       that are not expecting this should treat it as a rude disconnect."""
