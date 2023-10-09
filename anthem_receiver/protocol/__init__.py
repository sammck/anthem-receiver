# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Low-level protocol definitions for Anthem receivers.

This module defines the low-level protocol used by the Anthem receivers for TCP/IP control.
It does not contain protocol implementations.

Refer to https://support.Anthem.com/consumer/support/documents/DILAremoteControlGuide.pdf
for the official protocol documentation.
"""

from .constants import (
    END_OF_PACKET,
    END_OF_PACKET_BYTES,
    MAX_PACKET_LENGTH,
  )

from .anthem_model import AnthemModel, anthem_models
from .packet_type import PacketType

from .packet import (
    Packet,
  )

from .packet_stream_transport import PacketStreamTransport
