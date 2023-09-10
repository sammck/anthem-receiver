# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

from __future__ import annotations

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from .packet import Packet
from .response import AnthemResponse
from ..pkg_logging import logger
from .command_meta import (
    AnthemModel,
    CommandMeta,
    ResponsePayloadMapper,
    bytes_to_command_meta,
    name_to_command_meta,
  )

from .constants import (
    PacketType,
    PACKET_MAGIC,
    END_OF_PACKET_BYTES
  )
class AnthemCommand:
    """A command to a Anthem receiver"""
    command_packet: Packet
    command_meta: CommandMeta

    def __init__(
            self,
            command_packet: Packet,
            command_meta: Optional[CommandMeta]=None,
          ):
        command_packet.validate()
        if not command_packet.packet_type in (PacketType.BASIC_COMMAND, PacketType.ADVANCED_COMMAND):
            raise AnthemReceiverError(f"Invalid command packet type {command_packet.packet_type}: {command_packet}")
        if command_meta is None:
            command_metas = bytes_to_command_meta(command_packet.raw_data)
            if len(command_metas) == 0:
                raise AnthemReceiverError(f"Unrecognized command packet: {command_packet}")
            if len(command_metas) > 1:
                logger.debug(f"Multiple command metas found for command packet; using first: {command_packet}")
            command_meta = command_metas[0]
        self.command_packet = command_packet
        self.command_meta = command_meta
        if not command_packet.raw_data.startswith(command_meta.packet_prefix):
            raise AnthemReceiverError(f"Command packet does not match command meta prefix {command_meta.packet_prefix.hex(' ')}: {command_packet}")
        if not command_meta.packet_payload_length is None:
            if command_packet.packet_payload_length != command_meta.packet_payload_length:
                raise AnthemReceiverError(
                    f"Command packet payload length {command_packet.packet_payload_length} does not match command meta packet payload length {command_meta.packet_payload_length}: {command_packet}")

    @property
    def name(self) -> str:
        """Returns the full name of the command; e.g. f"{group_name}.{command_name}"""
        return self.command_meta.full_name

    @property
    def raw_data(self) -> bytes:
        """Returns the raw data of the command"""
        return self.command_packet.raw_data

    @property
    def command_code(self) -> bytes:
        """Returns the command code of the command"""
        return self.command_packet.command_code

    @property
    def packet_payload(self) -> bytes:
        """Returns the raw packet payload of the command packet.
           This includes the command prefix and the command payload."""
        return self.command_packet.packet_payload

    @property
    def packet_payload_length(self) -> int:
        """Returns length in bytes of the raw payload of the command packet.
           This includes the command prefix and the command payload."""
        return self.command_packet.packet_payload_length

    @property
    def payload(self) -> bytes:
        """Returns the command payload.
           This includes all bytes after the command prefix and before
           the END_OF_PACKET byte."""
        return self.command_packet.packet_payload[self.command_prefix_length:]

    @property
    def payload_length(self) -> int:
        """Returns the length in bytes of the command payload.
           This includes all bytes after the command prefix and before
           the END_OF_PACKET byte."""
        return self.packet_payload_length - self.command_prefix_length

    @property
    def command_prefix(self) -> bytes:
        """Returns the command prefix of the command. This includes
           all bytes after command_code and before the command payload."""
        return self.command_meta.command_prefix

    @property
    def command_prefix_length(self) -> int:
        """Returns the length in bytes of the command prefix of the command.
           This includes all bytes after command_code and before the
           command payload."""
        return self.command_meta.command_prefix_length

    @property
    def packet_prefix(self) -> bytes:
        """Returns the packet prefix of the command. This includes
           all bytes before the command payload, including the packet type,
           packet magic, command code, and command prefix."""
        return self.command_meta.packet_prefix

    @property
    def packet_prefix_length(self) -> int:
        """Returns the length of the packet prefix of the command. This includes
           all bytes before the command payload, including the packet type,
           packet magic, command code, and command prefix."""
        return self.command_meta.packet_prefix_length

    @property
    def packet_type(self) -> PacketType:
        """Returns the packet type of the command"""
        return self.command_packet.packet_type

    @property
    def is_advanced(self) -> bool:
        """Returns True iff the command is an advanced command"""
        return self.command_packet.is_advanced_command

    @property
    def response_payload_length(self) -> Optional[int]:
        """Fixed length of the payload of the advanced response, if known.
           0 for basic commands. None if the payload is variable in size."""
        return self.command_meta.response_payload_length

    @property
    def response_map(self) -> ResponsePayloadMapper:
        """Map of response payloads to friendly response strings.
           None if not an advanced command."""
        return self.command_meta.response_map

    @classmethod
    def create_from_command_packet(
            cls,
            command_packet: Packet,
            model: Optional[AnthemModel]=None,
          ) -> Self:
        """Creates a basic or advanced AnthemCommand from a command packet.
           If model is provided, it will be used to resolve ambiguities in
           the command packet (Different receiver models occasionally overload
           command packets for different commands). If multiple commands match
           the command packet/model, the first one will be used."""
        command_metas = bytes_to_command_meta(command_packet.raw_data)
        if len(command_metas) == 0:
            raise AnthemReceiverError(f"Unrecognized command packet: {command_packet}")
        if len(command_metas) > 1:
            if not model is None:
                matching_command_metas = [command_meta for command_meta in command_metas
                    if command_meta.models is None or model in command_meta.models]
                if len(matching_command_metas) > 0:
                    if len(matching_command_metas) == 1:
                        logger.debug(f"Multiple command metas found for command packet; using model-matching command: {command_packet}")
                    else:
                        logger.debug(f"Multiple model-matching command metas found for command packet; using first: {command_packet}")
                    command_meta = matching_command_metas[0]
                else:
                    logger.debug(f"Multiple command metas found for command packet; using first: {command_packet}")
                    command_meta = command_metas[0]
        else:
            # Only one command matches packet; no need to resolve ambiguity
            command_meta = command_metas[0]
        return cls(command_packet, command_meta)

    @classmethod
    def create_from_meta(
            cls,
            command_meta: CommandMeta,
            payload: Optional[bytes]=None,
          ) -> Self:
        """Creates a basic or advanced AnthemCommand from command metadata"""
        if payload is None:
            payload = b''
        raw_data = command_meta.packet_prefix + payload + END_OF_PACKET_BYTES
        command_packet = Packet(raw_data)
        return cls(command_packet, command_meta)

    @classmethod
    def create_from_name(
            cls,
            command_name: str,
            payload: Optional[bytes]=None,
          ):
        """Creates a basic or advanced AnthemCommand from command name"""
        command_meta = name_to_command_meta(command_name)
        return cls.create_from_meta(command_meta, payload=payload)

    def create_basic_response_packet(self) -> Packet:
        """Creates a basic response packet for the command"""
        raw_data = (
            bytes([PacketType.BASIC_RESPONSE.value]) +
            PACKET_MAGIC +
            self.command_code +
            END_OF_PACKET_BYTES
          )
        result = Packet(raw_data)
        return result

    def create_advanced_response_packet(self, payload: bytes) -> Packet:
        """Creates an advanced response packet for the command"""
        if not self.is_advanced:
            raise AnthemReceiverError(f"Cannot create advanced response packet for basic command: {self}")
        if payload is None:
            payload = b''
        if self.response_payload_length is not None:
            if len(payload) != self.response_payload_length:
                raise AnthemReceiverError(
                    f"Invalid response payload length {len(payload)}, expected {self.response_payload_length} for command : {payload.hex(' ')}")
        raw_data = (
            bytes([PacketType.ADVANCED_RESPONSE.value]) +
            PACKET_MAGIC +
            self.command_code +
            payload +
            END_OF_PACKET_BYTES
          )
        result = Packet(raw_data)
        return result

    def create_response(self, payload: Optional[bytes]=None) -> AnthemResponse:
        """Creates a AnthemResponse from the command and the response payload"""
        if payload is None:
            payload = b''
        basic_response_packet = self.create_basic_response_packet()
        advanced_response_packet: Optional[Packet] = None
        if self.is_advanced:
            advanced_response_packet = self.create_advanced_response_packet(payload)
        elif len(payload) > 0:
            raise AnthemReceiverError(f"Invalid response payload length {len(payload)} for basic command {self}: {payload.hex(' ')}")
        result = AnthemResponse(self, basic_response_packet, advanced_response_packet)
        return result

    def create_response_from_packets(
            self,
            basic_response_packet: Packet,
            advanced_response_packet: Optional[Packet]=None,
          ) -> AnthemResponse:
        """Creates a AnthemResponse from the command and the response packets"""
        result = AnthemResponse(self, basic_response_packet, advanced_response_packet)
        return result

    def __str__(self) -> str:
        return f"AnthemCommand({self.name}: {self.command_packet})"

    def __repr__(self) -> str:
        return str(self)
