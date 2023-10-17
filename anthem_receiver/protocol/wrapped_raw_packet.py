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
from .raw_packet_type import RawPacketType
from .raw_packet import RawPacket
from abc import ABC, abstractmethod

class ZoneId(Enum):
    INVALID = "INVALID"
    ALL_ZONES = "0"
    ZONE_1 = "1"
    ZONE_2 = "2"
    ZONE_3 = "3"
    ZONE_4 = "4"

class TunerId(Enum):
    INVALID = "INVALID"
    TUNER_1 = "1"

class TriggerId(Enum):
    INVALID = "INVALID"
    TRIGGER_1 = "0"
    TRIGGER_2 = "1"

class WrappedRawPacket(ABC, RawPacket):
    """
    Encapsulation of a single high-level protocol packet that can be converted to/from a raw
    Anthem protocol packet, in either direction.
    Can encapsulate a single Anthem command/response/notification.
    """

    # ============================================================
    # Class attributes (common to all instances of the subclass)

    description: str
    """A description of the packet type"""

    short_name: str
    """The 3-4 character upper-case alhabetic string identifying the packet type, as a string.
       Common to all instances of the subclass."""

    long_name: str
    """The snake-case string identifying the packet type, as a string.
       Common to all instances of the subclass."""

    requires_zone: bool = False
    """Whether the packet type requires a zone number to be specified.
       Common to all instances of the subclass."""

    requires_tuner: bool = False
    """Whether the packet type requires a tuner number to be specified.
       Common to all instances of the subclass."""

    requires_trigger: bool = False
    """Whether the packet type requires a trigger number to be specified.
       Common to all instances of the subclass."""

    is_queryable: bool = False
    """Whether this packet type is queryable. Defaults to False."""

    is_commandable: bool = True
    """Whether this packet type can be sent as a non-query request. Defaults to True."""

    is_reportable: bool = False
    """Whether changes to values associated with this packet type are asynchronously
       reported. Defaults to False."""

    is_error_response: bool = False
    """Whether this packet type is an error response. Defaults to False."""

    # ============================================================
    # Instance attributes (specific to each instance of the subclass)

    zone_id: ZoneId = ZoneId.INVALID
    """The zone number associated with this packet, if any. Defaults to ZoneId.INVALID."""

    tuner_id: TunerId = TunerId.INVALID
    """The tuner number associated with this packet, if any. Defaults to TunerId.INVALID."""

    trigger_id: TriggerId = TriggerId.INVALID
    """The trigger number associated with this packet, if any. Defaults to TriggerId.INVALID."""

    is_query: bool = False
    """Whether this packet is a query. Defaults to False."""

    # ============================================================
    # class methods (overridden by each subclass)

    @classmethod
    def from_raw_data(cls, raw_data: Union[str, bytes]) -> WrappedRawPacket:
        if isinstance(raw_data, str):
            raw_data = raw_data.encode('utf-8')
        return cls(raw_data=raw_data)


    def __init__(self):
        """Create a Packet object.
        """
        super().__init__(raw_packet_type=RawPacketType.ANTHEM, raw_data=b'')

    def __str__(self) -> str:
        return f"Packet({self.raw_packet_type!r}, {self.raw_data!r})"

    def __repr__(self) -> str:
        return str(self)

    def render_string_param(self, value: str, *, min_length: int=1, max_length: int=255, blank_pad: bool=True, null_pad: bool=False) -> Iterable[int]:
        assert 0 < min_length <= max_length
        result = value.encode('utf-8')
        while blank_pad and len(result) < min_length:
            result += b' '
        while null_pad and len(result) < min_length:
            result += b'\x00'
        if len(result) < min_length:
            raise AnthemReceiverError(f"String parameter {value!r} shorter than minimum length {min_length}, and padding not allowed")
        if len(result) > max_length:
            raise AnthemReceiverError(f"String parameter {value!r} longer than maximum length {max_length}")
        return result

    def render_int_param(self, value: int, *, min_length: int=1, max_length: int=6, require_sign: bool=False) -> Iterable[int]:
        assert 0 < min_length <= max_length
        sign = "-" if value < 0 else ("+" if require_sign else "")
        abs_vstr = str(abs(value))
        npad = max(0, min_length - len(sign) - len(abs_vstr))
        result = sign.encode('utf-8') + b'0' * npad + abs_vstr.encode('utf-8')
        if len(result) > max_length:
            raise AnthemReceiverError(f"Integer parameter {result!r} longer than maximum length {max_length}")
        return result

    def render_float_param(self, value: float, *, min_length: int=1, max_length: int=9, require_sign: bool=False, digs_after_decimal:int=2) -> Iterable[int]:
        assert 0 < min_length <= max_length
        assert 0 <= digs_after_decimal <= max_length - 1 - (1 if require_sign else 0)
        sign = "-" if value < 0 else ("+" if require_sign else "")
        abs_vstr = f"{abs(value):.{digs_after_decimal}f}"
        npad = max(0, min_length - len(sign) - len(abs_vstr))
        result = sign.encode('utf-8') + b'0' * npad + abs_vstr.encode('utf-8')
        if len(result) > max_length:
            raise AnthemReceiverError(f"Float parameter {result!r} longer than maximum length {max_length}")
        return result

    def render_pre_query(self) -> Iterable[int]:
        """Generate the pre-query portion of the packet from high level attributes.
           By default, this returns an empty byte-string.
        """
        return b''

    def render_post_query(self) -> Iterable[int]:
        """Generate the post-query portion of the packet from high level attributes.
           By default, this does returns an empty byte-string.
        """
        return b''




    def render_raw_data(self) -> bytes:
        """Generate the raw data for this packet from high level attributes."""

        sprefix = ''
        if self.requires_zone:
            if self.zone_id == ZoneId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a zone number, but none was specified")
            sprefix += f"Z{self.zone_id.value}"
        if self.requires_tuner:
            if self.tuner_id == TunerId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a tuner number, but none was specified")
            sprefix += f"T{self.tuner_id.value}"
        if self.requires_trigger:
            if self.trigger_id == TriggerId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a trigger number, but none was specified")
            sprefix += f"R{self.trigger_id.value}"
        sprefix += self.short_name
        raw_data = bytearray(sprefix.encode('utf-8'))
        raw_data.extend(self.render_pre_query())
        if self.is_query:
            raw_data.append(ord('?'))
        else:
            raw_data.extend(self.render_post_query())
        return bytes(raw_data)

    def update_raw_data(self, raw_data: bytes) -> None:
        """Update the raw_data associated with this packet.

        Args:
            raw_data (bytes): The new raw_data.
        """
        self.raw_data = self.render_raw_data()

    def parse_string_param(
            self,
            raw_data: bytes,
            *,
            min_length: int=1,
            max_length: int=255,
            rstrip: bool=True,
            null_rstrip: bool=True
          ) -> Tuple[str, bytes]:
        """Parse a string parameter from the packet.

        Args:
            raw_data (bytes): The remaining raw data parameters with all prior parameters removed.
            min_length (int, optional): The minimum length of the string. Defaults to 1.
            max_length (int, optional): The maximum length of the string. Defaults to 255.
            rstrip (bool, optional): Whether to strip trailing whitespace. Defaults to True.
            null_rstrip (bool, optional): Whether to strip trailing nulls. Defaults to True.

        Returns:
            Tuple[str, bytes]: The parsed string, and the remaining raw data parameters with the parsed string removed.
        """
        plen = min(max_length, len(raw_data))
        if plen < min_length:
            raise AnthemReceiverError(f"Remaining packet data {self.raw_data!r} shorter than minimum string length {min_length}")
        raw_result = raw_data[:plen]
        remaining = raw_data[plen:]
        if null_rstrip:
            while plen > 0 and raw_result[plen-1] == 0:
                plen -= 1
            raw_result = raw_result[:plen]
        result = raw_result.decode('utf-8')
        if rstrip:
            result = result.rstrip()
        return result, remaining

    def parse_int_param(
            self,
            raw_data: bytes,
            *,
            min_length: int=1,
            max_length: int=6,
            min_value: int=0,
            max_value: int=999999,
            allow_sign: bool=True,
          ) -> Tuple[int, bytes]:
        """Parse an integer parameter from the packet.

        Args:
            raw_data (bytes): The remaining raw data parameters with all prior parameters removed.
            min_length (int, optional): The minimum length of the string. Defaults to 1.
            max_length (int, optional): The maximum length of the string. Defaults to 6.
            min_value (int, optional): The minimum value of the integer. Defaults to 0.
            max_value (int, optional): The maximum value of the integer. Defaults to 999999.
            allow_sign (bool, optional): Whether to allow a leading '-' or '+' sign. Defaults to True.

        Returns:
            Tuple[int, bytes]: The parsed int, and the remaining raw data parameters with the parsed string removed.
        """
        plen = min(max_length, len(raw_data))
        for i in range(plen):
            if not ((allow_sign and i == 0 and raw_data[i] in b'-+') or raw_data[i] in b'0123456789'):
                plen = i
                break
        if plen < min_length:
            raise AnthemReceiverError(f"Remaining packet data {self.raw_data!r} shorter than minimum string length {min_length}")
        result = int(raw_data[:plen])
        if result < min_value or result > max_value:
            raise AnthemReceiverError(f"Remaining packet data {self.raw_data!r} integer value {result} out of range {min_value}..{max_value}")
        remaining = raw_data[plen:]
        return result, remaining

    def parse_float_param(
            self,
            raw_data: bytes,
            *,
            min_length: int=1,
            max_length: int=9,
            min_value: float=0.0,
            max_value: float=999999.0,
            allow_sign: bool=True,
          ) -> Tuple[float, bytes]:
        """Parse a float parameter from the packet.

        Args:
            raw_data (bytes): The remaining raw data parameters with all prior parameters removed.
            min_length (int, optional): The minimum length of the string. Defaults to 1.
            max_length (int, optional): The maximum length of the string. Defaults to 6.
            min_value (float, optional): The minimum value of the float. Defaults to 0.0.
            max_value (float, optional): The maximum value of the float. Defaults to 999999.0.
            allow_sign (bool, optional): Whether to allow a leading '-' or '+' sign. Defaults to True.

        Returns:
            Tuple[float, bytes]: The parsed float, and the remaining raw data parameters with the parsed string removed.
        """
        plen = min(max_length, len(raw_data))
        for i in range(plen):
            if not ((allow_sign and i == 0 and raw_data[i] in b'-+') or raw_data[i] in b'.0123456789'):
                plen = i
                break
        if plen < min_length:
            raise AnthemReceiverError(f"Remaining packet data {self.raw_data!r} shorter than minimum string length {min_length}")
        result = float(raw_data[:plen])
        if result < min_value or result > max_value:
            raise AnthemReceiverError(f"Remaining packet data {self.raw_data!r} float value {result} out of range {min_value}..{max_value}")
        remaining = raw_data[plen:]
        return result, remaining

    def parse_pre_query(self, sdata: str) -> str:
        """Parse the pre-query portion of the packet. By default, this does nothing.
           This method is called for both queries and non-queries.

           Pre-query parameters are parts of the packet (not including zone, tuner and trigger prefixes) that
           are provided for both queries and non-queries. Most packets do not have pre-query parameters. An
           example of a command that has a pre-query parameter is SDVSxxy. The xx is the input number for
           which dolby volume is being set, and the y is the dolby volume level. The xx is a pre-query
           parameter, and the y is a post-query parameter.  The query version of this command is SDVSxx?.

           Packets that are not queryable or that do not accept pre-query parameters should not override this method.

        Args:
            sdata (str): The string raw data with zone, tuner, and trigger prefixes, and the packet short name, removed.

        Returns:
            str: The remainder of sdata after pre-query parameters are removed.
        """
        return sdata

    def parse_post_query(self, sdata: str) -> None:
        """Parse the post-query portion of the packet. By default, this simply ensures there is no more data.
           This method is only called if the packet is not a query. It is called for non-query commands
           query responses, and unsolicited reports.

           Post-query parameters are parts of the packet that are only provided for non-queries (e.g., commands,
           responses, and reports).

           Packets that are not queryable should treat all parameters as post-query parameters, and should
           override this method if they accept parameters.

           Packets that do not accept any post-query parameters should not override this method.

        Args:
            sdata (str): The string raw data with zone, tuner, and trigger prefixes, the packet short name,
                         the pre-query parameters removed.

        Returns:
            str: The remainder of sdata after pre-query attributes are removed.
        """
        if sdata != '':
            raise AnthemReceiverError(f"Packet {self.raw_data!r} contains data after legitimate parameters: {sdata!r}")

    def validate_parsed(self) -> None:
        """Validate the parsed packet. By default, this does nothing.
           This method is called after the packet is parsed, and is intended to validate
           the parsed packet.
        """
        pass

    def init_from_raw(self, raw_data: Union[bytes, str]) -> None:
        """Initialize this packet from raw data.

        Args:
            raw_data (bytes): The raw data.
        """
        if raw_data.endswith(b';'):
            raw_data = raw_data[:-1]
        if isinstance(raw_data, str):
            raw_data = raw_data.encode('utf-8')
        self.raw_data = raw_data
        sraw_data = raw_data.rstrip(b'\x00')
        sdata = sraw_data.decode('utf-8')
        if len(sdata) > 1:
            if sdata[0] = 'Z' and '0' <= sdata[1] <= '9':
                if not self.requires_zone:
                    raise AnthemReceiverError(f"Zone number specified for packet {self.raw_data!r} which does not require a zone number")
                self.zone_id = ZoneId(sdata[1])
                sdata = sdata[2:]
            elif sdata[0] = 'T' and '0' <= sdata[1] <= '9':
                if not self.requires_tuner:
                    raise AnthemReceiverError(f"Tuner number specified for packet {self.raw_data!r} which does not require a tuner number")
                self.tuner_id = TunerId(sdata[1])
                sdata = sdata[2:]
            elif sdata[0] = 'R' and '0' <= sdata[1] <= '9':
                if not self.requires_trigger:
                    raise AnthemReceiverError(f"Trigger number specified for packet {self.raw_data!r} which does not require a trigger number")
                self.trigger_id = TriggerId(sdata[1])
                sdata = sdata[2:]
        if self.requires_zone and self.zone_id == ZoneId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a zone number, but none was specified")
        if self.requires_tuner and self.tuner_id == TunerId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a tuner number, but none was specified")
        if self.requires_trigger and self.trigger_id == TriggerId.INVALID:
                raise AnthemReceiverError(f"Packet {self.raw_data!r} requires a trigger number, but none was specified")

        if not sdata.startswith(self.short_name):
            raise AnthemReceiverError(f"Packet {self.raw_data!r} type {self.short_name!r} does not match packet data {sdata!r}")
        sdata = sdata[len(self.short_name):]
        sdata = self.parse_pre_query(sdata)
        if self.is_queryable and sdata.startswith('?'):
            self.is_query = True
            sdata = sdata[1:]
            if sdata != '':
                raise AnthemReceiverError(f"Packet {self.raw_data!r} contains data after query: {sdata!r}")
        else:
            self.is_query = False
            self.parse_post_query(sdata)
            sdata = ''

        self.validate_parsed()

packet_classes_by_short_name: Dict[str, Type[WrappedRawPacket]] = {}
"""A registery of wrapped packet classes, indexed by short_name."""

packet_classes_by_long_name: Dict[str, Type[WrappedRawPacket]] = {}
"""A registery of wrapped packet classes, indexed by long_name."""

_WrappedPacketClass = TypeVar('_WrappedPacketClass', bound=Type[WrappedRawPacket])
def register_packet_class(cls: _WrappedPacketClass) -> _WrappedPacketClass:
    """A class decorator to register a wrapped packet class.
       Allows the class to be looked up by short or long name
    """
    packet_classes_by_short_name[cls.short_name] = cls
    packet_classes_by_long_name[cls.long_name] = cls
    return cls
