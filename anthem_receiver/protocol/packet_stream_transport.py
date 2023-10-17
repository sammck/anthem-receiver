# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Abstract base class for a PacketStreamWriter, to which a stream of Packets can be written.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


from ..internal_types import *
from .raw_packet import RawPacket

class PacketStreamTransport(ABC):
    """
    Interface for a bi-directional stream of RawPacket objects that can be asynchronously read and written.
    """

    @abstractmethod
    async def read(self) -> Optional[RawPacket]:
        """
        Read the next RawPacket from the stream.

        Returns:
            The next RawPacket from the stream, or None if the stream has ended.
        """
        ...

    @abstractmethod
    async def write(self, packet: RawPacket):
        """
        Writes the next RawPacket to the stream. May retuurn before the packet has been
        fully written.
        """
        ...

    @abstractmethod
    async def write_eof(self):
        """
        Writes an eof. Subsequent writes are not allowed. May be called multiple times
        without error. Subsequent reads on the remote end will receive an EOF.
        May retuurn before pending write packets have been fully written.
        """
        ...

    async def flush(self):
        """
        Flushes any buffered write packets.

        In spite of flushing, may return before the receiving end of the stream has processed the packet;
        failures may result in the packet never being received and processed.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close both directions of the PacketStreamTransport. Does not wait for
        the transport to be completely closed.

        The remote end of the stream will subsequently receive an end of stream
        indication when reading from the stream, and errors attempting to
        write to the stream.

        Repeated calls to this method are allowed and will have no effect.
        """
        ...

    @abstractmethod
    async def wait_closed(self) -> None:
        """
        Wait for the PacketStreamTransport to be completely closed. Does not initiate
        closing.
        """
        ...

    async def aclose(self) -> None:
        """
        Close the PacketStreamWriter, and the underlying stream.

        The remote end of the stream will subsequently receive an end of stream
        indication when reading from the stream

        Repeated calls to this method are allowed and will have no effect.
        """
        self.close()
        await self.wait_closed()

    async def __aenter__(self) -> PacketStreamTransport:
        """
        Enter a context that will close the PacketStreamTransport when the context exits.
        """
        return self

    async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType],
          ) -> None:
        """
        Async context manager exit point.
        """
        await self.aclose()

    async def __aiter__(self) -> AsyncIterator[RawPacket]:
        """
        Async iterator for read side of transport.
        """
        while True:
            packet: Optional[RawPacket] = await self.read()
            if packet is None:
                return
            yield packet
