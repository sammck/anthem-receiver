#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Abstraction of a Datagram packet used in the AnthemDp protocol.


Example search request (sent to UDP multicast 255.255.255.255 port 14999):

    0000   ff ff ff ff ff ff ea 7e d0 eb f4 6a 08 00 45 00   .......~...j..E.
    0010   00 5c 33 5a 00 00 40 11 81 f2 c0 a8 04 9d ff ff   .\3Z..@.........
    0020   ff ff 3a 97 3a 97 00 48 21 65 50 41 52 43 00 00   ..:.:..H!ePARC..
    0030   01 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00   ................
    0040   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   ................
    0050   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   ................
    0060   00 00 00 00 00 00 00 00 00 00                     ..........

    header = b'PARC\0\0'
    request_announce = 01 = True
    is_off = 00 = False
    dp_version = 00 00 00 01 = 1
    tcp_port = 00 00 00 00 = 0
    device_name = 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 = b'\0'*16
    model_name = 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 = b'\0'*16
    serial_number = 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 = b'\0'*16


Example search response:
    0000   ff ff ff ff ff ff 7c b7 7b 03 96 7a 08 00 45 00   ......|.{..z..E.
    0010   00 5c 08 ed 00 00 ff 11 24 fd c0 a8 04 57 c0 a8   .\......$....W..
    0020   07 ff 3a 97 3a 97 00 48 84 16 50 41 52 43 00 00   ..:.:..H..PARC..
    0030   00 00 00 00 00 01 00 00 3a 97 41 56 4d 20 36 30   ........:.AVM 60
    0040   20 20 20 20 20 20 20 20 20 20 41 56 4d 20 36 30             AVM 60
    0050   20 00 00 00 00 00 00 00 00 00 37 43 42 37 37 42    .........7CB77B
    0060   30 33 39 36 30 41 00 00 00 00                     03960A....

    header = b'PARC\0\0'
    request_announce = 00 = False
    is_off = 00 = False
    dp_version = 00 00 00 01 = 1
    tcp_port = 00 00 3a 97 = 14999
    device_name = 41 56 4d 20 36 30 20 20 20 20 20 20 20 20 20 20 = b'AVM 60          ' -> 'AVM 60'
    model_name = 41 56 4d 20 36 30 20 00 00 00 00 00 00 00 00 00 = b'AVM 60 \0\0\0\0\0\0\0\0\0' -> 'AVM 60'
    serial_number = 37 43 42 37 37 42 30 33 39 36 30 41 00 00 00 00 = b'7CB77B03960A\0\0\0\0' -> '7CB77B03960A'

"""

from __future__ import annotations

from ..internal_types import *
from ..pkg_logging import logger

from .constants import ANTHEM_DP_PORT

import json

HeaderValue = Union[str, int, float]
NullableHeaderValue = Optional[HeaderValue]

class AnthemDpDatagram():
    """Wrapper for a raw AnthemDp datagram.

    This class provides parsing and formatting of the Anthem discovery protocol
    advertisement packet. It is also used for the search request (with announce=True)


    An AnthemDpDatagram packet is a UDP packet composed as follows:

        (b'PARC\0\0' + anounce_request_byte + off_byte + version_4_bytes + tcp_ip_port_4_bytes
           + device_name_16_chars + model_name_16_chars + serial_number_16_chars)

    where:
        `announce_request_byte` is 0x01 if this is a request for all receiving devices to announce
            themselves with a broadcast, or 0x00 if this is an announcement, a response,
            or a directed request.

        `off_byte` is 0x01 if this is an announcement that the sending device is going offline,
            or 00 otherwise.

        `version_4_bytes` is a 4-byte network-byte-order (big-endian) integer indicating
            the protocol version. The current version is 1.

        `tcp_ip_port_4_bytes` is a 4-byte network-byte-order (big-endian) integer indicating
            the TCP/IP port number that the device is listening on. The usual port
            is 14999. On query, this is 0.

        `device_name_16_chars` is a 16-character, blank-or-null padded byte-string containing
            the device name. May contain embedded spaces. For AVM-60, this is
            b'AVM 60          '. On query, this is b'\0'*16.

        `model_name_16_chars` is a 16-character, blank-or-null-padded byte-string containing
            the model name. May contain embedded spaces. On AVM-60, this is b'AVM 60 \0\0\0\0\0\0\0\0\0'
            (notice extra blank at end).
            On query, this is b'\0'*16.

        `serial_number_16_chars` is a 16-character null-padded hexadecimal byte-string containing the serial number.
            an example is b'7CB77B03960A\0\0\0\0'
            On query, this is b'\0'*16.
    """

    _raw_data: bytes
    """The raw UDP datagram contents"""

    _HEADER_OFFSET = 0
    _HEADER_LENGTH = 6
    _HEADER_VALUE = b'PARC\0\0'

    _ANNOUNCE_REQUEST_OFFSET = _HEADER_OFFSET + _HEADER_LENGTH
    _ANNOUNCE_REQUEST_LENGTH = 1

    _IS_OFF_OFFSET = _ANNOUNCE_REQUEST_OFFSET + _ANNOUNCE_REQUEST_LENGTH
    _IS_OFF_LENGTH = 1

    _DP_VERSION_OFFSET = _IS_OFF_OFFSET + _IS_OFF_LENGTH
    _DP_VERSION_LENGTH = 4

    _TCP_PORT_OFFSET = _DP_VERSION_OFFSET + _DP_VERSION_LENGTH
    _TCP_PORT_LENGTH = 4

    _DEVICE_NAME_OFFSET = _TCP_PORT_OFFSET + _TCP_PORT_LENGTH
    _DEVICE_NAME_LENGTH = 16

    _MODEL_NAME_OFFSET = _DEVICE_NAME_OFFSET + _DEVICE_NAME_LENGTH
    _MODEL_NAME_LENGTH = 16

    _SERIAL_NUMBER_OFFSET = _MODEL_NAME_OFFSET + _MODEL_NAME_LENGTH
    _SERIAL_NUMBER_LENGTH = 16

    _TOTAL_LENGTH = _SERIAL_NUMBER_OFFSET + _SERIAL_NUMBER_LENGTH

    _DEFAULT_DP_VERSION = 1

    def __init__(
            self,
            *,
            announce_request: Optional[bool]=None,
            is_off: Optional[bool]=None,
            dp_version: Optional[int]=None,
            tcp_port: Optional[int]=None,
            device_name: Optional[str]=None,
            model_name: Optional[str]=None,
            serial_number: Optional[str]=None,
            is_query: bool=False,
            raw_data: Optional[bytes]=None,
            copy_from: Optional[AnthemDpDatagram]=None
          ):
        if copy_from is not None:
            assert (raw_data is None and announce_request is None and is_off is None and dp_version is None and
                    tcp_port is None and device_name is None and model_name is None and serial_number is None)
            self._raw_data = copy_from._raw_data
        elif raw_data is None:
            self._raw_data = self._HEADER_VALUE + b'\x00' * (self._TOTAL_LENGTH - self._HEADER_LENGTH)
            if is_query:
                assert (is_off is None and tcp_port is None and device_name is None and model_name is None and serial_number is None)
                self.announce_request = announce_request if announce_request is not None else True
                self.is_off = False
                self.dp_version = dp_version if dp_version is not None else self._DEFAULT_DP_VERSION
                self.tcp_port = 0
                self.raw_device_name = b'\0' * self._DEVICE_NAME_LENGTH
                self.raw_model_name = b'\0' * self._MODEL_NAME_LENGTH
                self.raw_serial_number = b'\0' * self._SERIAL_NUMBER_LENGTH
            else:
                self.announce_request = announce_request if announce_request is not None else False
                self.is_off = is_off if is_off is not None else False
                self.dp_version = dp_version if dp_version is not None else self._DEFAULT_DP_VERSION
                self.tcp_port = tcp_port if tcp_port is not None else ANTHEM_DP_PORT
                self.device_name = device_name if device_name is not None else 'AVMSIM'
                self.model_name = model_name if model_name is not None else 'AVM 60'
                self.serial_number = serial_number if serial_number is not None else ''
        else:
            assert (copy_from is None and announce_request is None and is_off is None and dp_version is None and
                    tcp_port is None and device_name is None and model_name is None and serial_number is None)
            self.raw_data = raw_data

    @classmethod
    def new_query(
            cls,
            announce_request: Optional[bool]=None,
            dp_version: Optional[int]=None,
          ) -> AnthemDpDatagram:
        """Create a new query datagram"""
        return cls(is_query=True, announce_request=announce_request, dp_version=dp_version)

    @classmethod
    def from_raw(cls, raw_data: bytes) -> AnthemDpDatagram:
        """Create a new AnthemDpDatagram from raw bytes"""
        return cls(raw_data=raw_data)

    @property
    def raw_data(self) -> bytes:
        """The raw UDP datagram contents"""
        return self._raw_data

    @raw_data.setter
    def raw_data(self, value: bytes) -> None:
        """Set the raw UDP datagram contents, and recompute headers."""
        if not isinstance(value, bytes):
            raise ValueError("raw_data must be a bytes object")
        if len(value) != self._TOTAL_LENGTH:
            raise ValueError(f"raw_data must be exactly {self._TOTAL_LENGTH} bytes long")
        if value[self._HEADER_OFFSET:self._HEADER_OFFSET+self._HEADER_LENGTH] != self._HEADER_VALUE:
            raise ValueError(f"raw_data must start with {self._HEADER_VALUE!r}")
        assert isinstance(value, bytes)
        self._raw_data = value

    def _get_raw_field(self, offset: int, length: int) -> bytes:
        return self._raw_data[offset:offset+length]

    def _set_raw_field(self, offset: int, length: int, value: bytes) -> None:
        if len(value) != length:
            raise ValueError(f"Field at offset {offset }must be exactly {length} bytes long: {value!r}")
        self._raw_data = self._raw_data[:offset] + value + self._raw_data[offset+length:]

    @property
    def raw_announce_request(self) -> bytes:
        """The raw "announce_request" field contents"""
        return self._get_raw_field(self._ANNOUNCE_REQUEST_OFFSET, self._ANNOUNCE_REQUEST_LENGTH)

    @raw_announce_request.setter
    def raw_announce_request(self, value: bytes) -> None:
        """Set the raw "announce_request" field contents"""
        self._set_raw_field(self._ANNOUNCE_REQUEST_OFFSET, self._ANNOUNCE_REQUEST_LENGTH, value)

    @property
    def raw_is_off(self) -> bytes:
        """The raw "is_off" field contents"""
        return self._get_raw_field(self._IS_OFF_OFFSET, self._IS_OFF_LENGTH)

    @raw_is_off.setter
    def raw_is_off(self, value: bytes) -> None:
        """Set the raw "is_off" field contents"""
        self._set_raw_field(self._IS_OFF_OFFSET, self._IS_OFF_LENGTH, value)

    @property
    def raw_dp_version(self) -> bytes:
        """The raw "dp_version" field contents"""
        return self._get_raw_field(self._DP_VERSION_OFFSET, self._DP_VERSION_LENGTH)

    @raw_dp_version.setter
    def raw_dp_version(self, value: bytes) -> None:
        """Set the raw "dp_version" field contents"""
        self._set_raw_field(self._DP_VERSION_OFFSET, self._DP_VERSION_LENGTH, value)

    @property
    def raw_tcp_port(self) -> bytes:
        """The raw "tcp_port" field contents"""
        return self._get_raw_field(self._TCP_PORT_OFFSET, self._TCP_PORT_LENGTH)

    @raw_tcp_port.setter
    def raw_tcp_port(self, value: bytes) -> None:
        """Set the raw "tcp_port" field contents"""
        self._set_raw_field(self._TCP_PORT_OFFSET, self._TCP_PORT_LENGTH, value)

    @property
    def raw_device_name(self) -> bytes:
        """The raw "device_name" field contents"""
        return self._get_raw_field(self._DEVICE_NAME_OFFSET, self._DEVICE_NAME_LENGTH)

    @raw_device_name.setter
    def raw_device_name(self, value: bytes) -> None:
        """Set the raw "device_name" field contents"""
        self._set_raw_field(self._DEVICE_NAME_OFFSET, self._DEVICE_NAME_LENGTH, value)

    @property
    def raw_model_name(self) -> bytes:
        """The raw "model_name" field contents"""
        return self._get_raw_field(self._MODEL_NAME_OFFSET, self._MODEL_NAME_LENGTH)

    @raw_model_name.setter
    def raw_model_name(self, value: bytes) -> None:
        """Set the raw "model_name" field contents"""
        self._set_raw_field(self._MODEL_NAME_OFFSET, self._MODEL_NAME_LENGTH, value)

    @property
    def raw_serial_number(self) -> bytes:
        """The raw "serial_number" field contents"""
        return self._get_raw_field(self._SERIAL_NUMBER_OFFSET, self._SERIAL_NUMBER_LENGTH)

    @raw_serial_number.setter
    def raw_serial_number(self, value: bytes) -> None:
        """Set the raw "serial_number" field contents"""
        self._set_raw_field(self._SERIAL_NUMBER_OFFSET, self._SERIAL_NUMBER_LENGTH, value)

    @property
    def announce_request(self) -> bool:
        """The "announce_request" field contents as a bool"""
        return self.raw_announce_request != b'\x00'

    @announce_request.setter
    def announce_request(self, value: bool) -> None:
        """Set the "announce_request" field contents from a bool"""
        self.raw_announce_request = b'\x01' if value else b'\x00'

    @property
    def header(self) -> bytes:
        """The "header" field contents"""
        return self._get_raw_field(self._HEADER_OFFSET, self._HEADER_LENGTH)

    @property
    def is_off(self) -> bool:
        """The "is_off" field contents as a bool"""
        return self.raw_is_off != b'\x00'

    @is_off.setter
    def is_off(self, value: bool) -> None:
        """Set the "is_off" field contents from a bool"""
        self.raw_is_off = b'\x01' if value else b'\x00'

    @property
    def dp_version(self) -> int:
        """The "dp_version" field contents as an int"""
        return int.from_bytes(self.raw_dp_version, 'big')

    @dp_version.setter
    def dp_version(self, value: int) -> None:
        """Set the "dp_version" field contents from an int"""
        self.raw_dp_version = value.to_bytes(self._DP_VERSION_LENGTH, 'big')

    @property
    def tcp_port(self) -> int:
        """The "tcp_port" field contents as an int"""
        return int.from_bytes(self.raw_tcp_port, 'big')

    @tcp_port.setter
    def tcp_port(self, value: int) -> None:
        """Set the "tcp_port" field contents from an int"""
        self.raw_tcp_port = value.to_bytes(self._TCP_PORT_LENGTH, 'big')

    @property
    def device_name(self) -> str:
        """The "device_name" field contents as a str"""
        return self.raw_device_name.decode('utf-8').rstrip('\x00').rstrip()

    @device_name.setter
    def device_name(self, value: str) -> None:
        """Set the "device_name" field contents from a str"""
        new_raw = value.rstrip().encode('utf-8').ljust(self._DEVICE_NAME_LENGTH, b' ')
        if len(new_raw) > self._DEVICE_NAME_LENGTH:
            raise ValueError(f"device_name must be no more than {self._DEVICE_NAME_LENGTH} encoded bytes long")
        assert len(new_raw) == self._DEVICE_NAME_LENGTH
        self.raw_device_name = new_raw

    @property
    def model_name(self) -> str:
        """The "model_name" field contents as a str"""
        return self.raw_model_name.decode('utf-8').rstrip('\x00').rstrip()

    @model_name.setter
    def model_name(self, value: str) -> None:
        """Set the "model_name" field contents from a str"""
        # to be consistent with the AVM-60, we will blank-pad to 7 characters, and
        # then null-pad the rest
        new_raw = value.rstrip().encode('utf-8').ljust(7, b' ').ljust(self._MODEL_NAME_LENGTH, b'\x00')
        if len(new_raw) > self._MODEL_NAME_LENGTH:
            raise ValueError(f"model_name must be no more than {self._MODEL_NAME_LENGTH} encoded bytes long")
        assert len(new_raw) == self._MODEL_NAME_LENGTH
        self.raw_model_name = new_raw

    @property
    def serial_number(self) -> str:
        """The "serial_number" field contents as a str"""
        return self.raw_serial_number.decode('utf-8').rstrip('\x00').rstrip()

    @serial_number.setter
    def serial_number(self, value: str) -> None:
        """Set the "serial_number" field contents from a str"""
        new_raw = value.rstrip().encode('utf-8').ljust(self._SERIAL_NUMBER_LENGTH, b'\x00')
        if len(new_raw) > self._SERIAL_NUMBER_LENGTH:
            raise ValueError(f"serial_number must be no more than {self._SERIAL_NUMBER_LENGTH} encoded bytes long")
        assert len(new_raw) == self._SERIAL_NUMBER_LENGTH
        self.raw_serial_number = new_raw

    def copy(self) -> AnthemDpDatagram:
        """Return a copy of this object"""
        return AnthemDpDatagram(copy_from=self)

    def __str__(self) -> str:
        return f"AnthemDpDatagram([{self.raw_data.hex(' ')}], announce={self.announce_request}, is_off={self.is_off}, dp_version={self.dp_version}, tcp_port={self.tcp_port}, device_name={self.device_name!r}, model_name={self.model_name!r}, serial_number={self.serial_number!r})"

    def __repr__(self) -> str:
        return str(self)
