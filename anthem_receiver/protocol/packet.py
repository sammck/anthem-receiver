# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Encapsulation of a single Anthem receiver protocol "packet" sent over the TCP/IP socket in either
"""

from __future__ import annotations

from enum import Enum
from ..internal_types import *
from ..exceptions import AnthemReceiverError
from .constants import (
    PACKET_MAGIC,
    END_OF_PACKET,
    MAX_PACKET_LENGTH,
    MIN_PACKET_LENGTH,
    PacketType,
  )

class Packet:
    """
    Encapsulation of a single Anthem receiver protocol "packet" sent over the TCP/IP socket in either
    direction.

    All packets sent to or received from the receiver (after initial auth handshake)
    are of the raw form:

        <packet_type_byte> 89 01 <two_byte_command_code> <command_prefix> <packet_payload> 0A

    packet_type_byte is one of the PacketType values.

    The 0A byte is a newline b'\n' character, and is the terminating byte for all packets. It is
    never present in any of the other portions of a packet.

    The two-byte command code in responses from the receiver is the same as the
    two-byte command code in the corresponding command packet.

    The command_prefix is an optional bytestring that further identifies
    the command but is not considered part of the payload.

    The packet_payload is the portion of the packet after the command code and before the
    terminating newline character. The payload is optional, and may be empty. If present,
    its content is determined by the packet type and command code.
    """

    raw_data: bytes
    """The raw packet data, including the terminating newline character"""

    def __init__(self, raw_data: bytes):
        self.raw_data = raw_data

    def __str__(self) -> str:
        return f"Packet({self.raw_data.hex(' ')})"

    def __repr__(self) -> str:
        return str(self)

    @property
    def packet_type_byte(self) -> int:
        """The first byte of the packet, which identifies the type of packet"""
        return self.raw_data[0]

    @property
    def packet_type(self) -> PacketType:
        """The type of packet. Returns PacketType.UNKNOWN if the packet type is not recognized."""
        try:
            result = PacketType(self.packet_type_byte)
        except ValueError:
            result = PacketType.UNKNOWN
        return result

    @property
    def packet_magic(self) -> bytes:
        """The packet magic validation bytes, which are the first two bytes after the packet type"""
        return self.raw_data[1:3]

    @property
    def command_code(self) -> bytes:
        """The 2-byte command code of the packet, which are the first two bytes after the packet magic"""
        return self.raw_data[3:5]

    @property
    def packet_payload(self) -> bytes:
        """The payload of the packet, excluding the packet type, the magic bytes, the
           command code, and the terminating newline character. Note that for
           command packets this includes the command prefix."""
        return self.raw_data[5:-1]

    @property
    def packet_payload_length(self) -> int:
        """The length of the packet payload, in bytes. Note that for command packets
           this includes the command prefix."""
        return len(self.packet_payload)

    @property
    def packet_final_byte(self) -> int:
        """The terminating byte of the packet. Should always be 0x0a."""
        return self.raw_data[-1]

    @property
    def is_valid(self) -> bool:
        """Returns True iff the packet is a well-formed packet at the simplest level"""
        if not (MIN_PACKET_LENGTH <= len(self.raw_data) <= MAX_PACKET_LENGTH):
            return False
        if self.packet_magic != PACKET_MAGIC:
            return False
        if not self.packet_final_byte == END_OF_PACKET:
            return False
        if self.packet_type == PacketType.UNKNOWN:
            return False
        return True

    def validate(self) -> None:
        if len(self.raw_data) < MIN_PACKET_LENGTH:
            raise AnthemReceiverError(f"Packet too short: {self}")
        if len(self.raw_data) > MAX_PACKET_LENGTH:
            raise AnthemReceiverError(f"Packet too long: {self}")
        if self.packet_magic != PACKET_MAGIC:
            raise AnthemReceiverError(f"Packet magic validator byte mismatch: {self}")
        if not self.packet_final_byte == END_OF_PACKET:
            raise AnthemReceiverError(f"Packet does not end in newline: {self}")
        if self.packet_type == PacketType.UNKNOWN:
            raise AnthemReceiverError(f"Unrecognized packet type byte {self.packet_type_byte:02x}: {self}")

    @property
    def is_basic_command(self) -> bool:
        """Returns True iff the packet is a well-formed basic command packet"""
        return self.is_valid and self.packet_type == PacketType.BASIC_COMMAND

    @property
    def is_advanced_command(self) -> bool:
        """Returns True iff the packet is a well-formed advanced command packet"""
        return self.is_valid and self.packet_type == PacketType.ADVANCED_COMMAND

    @property
    def is_command(self) -> bool:
        """Returns True iff the packet is a well-formed command packet"""
        return self.is_valid and self.packet_type in (PacketType.BASIC_COMMAND, PacketType.ADVANCED_COMMAND)

    @property
    def is_basic_response(self) -> bool:
        """Returns True iff the packet is a well-formed basic response packet"""
        return self.is_valid and self.packet_type == PacketType.BASIC_RESPONSE

    @property
    def is_advanced_response(self) -> bool:
        """Returns True iff the packet is a well-formed advanced response packet"""
        return self.is_valid and self.packet_type == PacketType.ADVANCED_RESPONSE

    @property
    def is_response(self) -> bool:
        """Returns True iff the packet is a well-formed response packet"""
        return self.is_valid and self.packet_type in (PacketType.BASIC_RESPONSE, PacketType.ADVANCED_RESPONSE)

    @classmethod
    def create(cls, packet_type: PacketType, command_code: bytes, payload: Optional[bytes]=None) -> Packet:
        if packet_type == PacketType.UNKNOWN:
            raise AnthemReceiverError(f"Cannot create packet of UNKNOWN type")
        if len(command_code) != 2:
            raise AnthemReceiverError(f"Command code not 2 bytes: {command_code.hex(' ')}")
        if payload is None:
            payload = b''
        raw_data = bytes([packet_type.value]) + PACKET_MAGIC + command_code + payload + bytes([END_OF_PACKET])
        return cls(raw_data)

    @classmethod
    def create_basic_command(cls, cmd_bytes: bytes, payload: Optional[bytes]=None) -> Packet:
        """Creates a basic command packet"""
        return cls.create(PacketType.BASIC_COMMAND, cmd_bytes, payload)

    @classmethod
    def create_advanced_command(cls, cmd_bytes: bytes, payload: Optional[bytes]=None) -> Packet:
        """Creates a basic command packet"""
        return cls.create(PacketType.ADVANCED_COMMAND, cmd_bytes, payload)

    @classmethod
    def create_command(cls, cmd_bytes: bytes, payload: Optional[bytes]=None, is_advanced: bool=False) -> Packet:
        """Creates a basic or advanced command packet"""
        if is_advanced:
            result = cls.create_advanced_command(cmd_bytes, payload)
        else:
            result = cls.create_basic_command(cmd_bytes, payload)
        return result

