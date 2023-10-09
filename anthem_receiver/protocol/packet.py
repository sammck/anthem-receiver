# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Encapsulation of a single Anthem receiver raw protocol "packet" sent over the TCP/IP socket in either
direction. Basically an arbitrary sequence of bytes, delimited by a ';' character.
"""

from __future__ import annotations

from enum import Enum
from ..internal_types import *
from ..exceptions import AnthemReceiverError
from .constants import (
    END_OF_PACKET,
    END_OF_PACKET_BYTES,
    MAX_PACKET_LENGTH,
  )
from .packet_type import PacketType

class Packet:
    """
    Encapsulation of a single low-level protocol packet, in either direction.
    Can encapsulate a single raw Anthem command/response/notification, or any additional
    messages used by higher level protocols.
    """

    def __init__(self, packet_type: PacketType=PacketType.UNKNOWN, raw_data: bytes=b''):
        """Create a Packet object.

        Args:
            packet_type (PacketType, optional): _description_. Defaults to PacketType.UNKNOWN.
            raw_data (bytes, optional): _description_. Defaults to b''.
        """
        self.packet_type = packet_type
        self.raw_data = raw_data

    @classmethod
    def anthem_packet(cls, raw_data: Union[str, bytes]) -> Packet:
        """
        Create a Anthem Packet object from a raw data packet sent to or received from the Anthem receiver.

        An Anthem Packet raw_data consists of an arbitrary sequence of 0-255 non-';' bytes. Packets are delimited
        in a protocol byte stream by b';'.

        The delimiting ';' character is not considered part of the packet, and is not included in the
        packet raw_data.

        As a convenience, if the provided raw_data ends with the ';' delimiter, it is removed before the packet is
        constructed.
        """
        if isinstance(raw_data, str):
            raw_data = raw_data.encode('utf-8')
        if len(raw_data) > 0 and raw_data[-1] == END_OF_PACKET:
            raw_data = raw_data[:-1]
        if len(raw_data) > MAX_PACKET_LENGTH:
            raise AnthemReceiverError(f"Anthem packet data length {len(raw_data)} exceeds maximum allowed length {MAX_PACKET_LENGTH}")
        if END_OF_PACKET in raw_data:
            raise AnthemReceiverError(f"Anthem packet data contains embedded END_OF_PACKET delimiter {END_OF_PACKET_BYTES!r}: {raw_data!r}")
        return cls(packet_type=PacketType.ANTHEM, raw_data=raw_data)


    def __str__(self) -> str:
        return f"Packet({self.packet_type!r}, {self.raw_data!r})"

    def __repr__(self) -> str:
        return str(self)
