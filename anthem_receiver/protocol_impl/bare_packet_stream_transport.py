# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
A PacketStreamWriter that directly talks to Anthem receiver protocol
"""

from __future__ import annotations

#from abc import ABC, abstractmethod
import asyncio
from asyncio import StreamReader, StreamWriter, Future

from ..protocol.packet import Packet
from ..protocol.packet_type import PacketType
from ..protocol.packet_stream_transport import PacketStreamTransport
from ..protocol.constants import END_OF_PACKET_BYTES, MAX_PACKET_LENGTH, END_OF_PACKET
from ..exceptions import AnthemReceiverError
from ..internal_types import *
from ..client import client_config
class BarePacketStreamTransport(PacketStreamTransport):
    """
    A PacketStreamWriter that directly talks to Anthem receiver protocol
    """

    stream_writer: StreamWriter
    """The StreamWriter to write to."""

    stream_reader: StreamReader
    """The StreamReader to read from."""

    buffer: bytearray

    end_of_stream_reached: bool = False

    skipping_invalid_packet: bool = False

    close_result: Future[None]
    """Future that will be set when close() is called. Can hold an exception if close failed."""

    wait_closed_result: Future[None]
    """Future that will be set when the PacketStreamWriter is completely closed. Can hold an exception if closing failed."""

    wait_closed_task: Optional[asyncio.Task[None]] = None
    """Task that will be created at close() to wait for the underlying StreamWriter to finish closing. Can hold an exception if closing failed."""

    init_completed: bool = False
    """True if the constructor has completed."""

    def __init__(
            self,
            stream_reader: StreamReader,
            stream_writer: StreamWriter,
          ) -> None:
        """
        Constructor.

        Args:
            stream_reader: The StreamReader to read from.
            stream_writer: The StreamWriterer to write to.
        """
        self.stream_reader = stream_reader
        self.stream_writer = stream_writer
        self.close_result = asyncio.get_running_loop().create_future()
        self.wait_closed_result = asyncio.get_running_loop().create_future()
        self.buffer = bytearray()
        self.init_completed = True

    @property
    def is_closed(self) -> bool:
        return self.close_result.done()

    # @abstractmethod
    async def read(self) -> Optional[Packet]:
        """
        Read the next Packet from the stream.

        Returns:
            The next Packet from the stream, or None if the stream has ended.
        """

        # Read until we have a complete packet
        more = True
        while more:
            more = False

            if self.is_closed:
                raise AnthemReceiverError("PacketStreamReader is closed")

            isemi = self.buffer.find(END_OF_PACKET)
            if 0 <= isemi <= MAX_PACKET_LENGTH:
                # Found a complete packet (or trailing end of an invalid packet) that is not too long
                raw_data = bytes(self.buffer[:isemi])
                n_consumed = isemi + 1
                packet_type = PacketType.INVALID_ANTHEM if self.skipping_invalid_packet else PacketType.ANTHEM
                self.skipping_invalid_packet = False
            elif len(self.buffer) > MAX_PACKET_LENGTH:
                # Found a packet or portion of a packet that is too long
                raw_data = bytes(self.buffer[:MAX_PACKET_LENGTH])
                n_consumed = MAX_PACKET_LENGTH
                packet_type = PacketType.INVALID_ANTHEM
                self.skipping_invalid_packet = True
            elif self.end_of_stream_reached:
                # Reached the end of the stream and there are no buffered full packets left.
                # If we have any buffered data left, it's an invalid packet.
                # Otherwise, we are done and can return None
                if len(self.buffer) == 0:
                    return None
                raw_data = bytes(self.buffer)
                n_consumed = len(self.buffer)
                packet_type = PacketType.INVALID_ANTHEM
                self.skipping_invalid_packet = True
            else:
                # We don't yet have a complete packet, and the buffered partial packet is not too
                # big yet.  Read some more data and iterate.
                more_data = await self.stream_reader.read(2048)
                if len(more_data) == 0:
                    self.end_of_stream_reached = True
                else:
                    self.buffer.extend(more_data)
                more = True

        # At this point, we have enough data to construct a packet.
        #     n_consumed = number of bytes consumed from buffer
        #     packet_type = packet type
        #     raw_data = packet data
        del self.buffer[:n_consumed]
        packet = Packet(packet_type=packet_type, raw_data=raw_data)
        return packet

    # @abstractmethod
    async def write(self, packet: Packet):
        """
        Writes the next Packet to the stream. May return before the packet has been
        fully written.
        """
        if packet.packet_type in (PacketType.ANTHEM, PacketType.INVALID_ANTHEM):
            raw_data = packet.raw_data
            if packet.packet_type == PacketType.ANTHEM:
                raw_data += END_OF_PACKET_BYTES
            self.stream_writer.write(raw_data)
        else:
            raise AnthemReceiverError(f"Cannot write non-Anthem packet {packet}")
        ...

    #@abstractmethod
    async def write_eof(self):
        """
        Writes an eof. Subsequent writes are not allowed. May be called multiple times
        without error. Subsequent reads on the remote end will receive an EOF.
        May retuurn before pending write packets have been fully written.
        """
        self.stream_writer.write_eof()

    # @override
    async def flush(self):
        """
        Flushes any buffered data to the underlying stream.

        In spite of flushing, may return before the receiving end of the stream has processed the packet;
        failures may result in the packet never being received and processed.
        """
        await self.stream_writer.drain()

    @staticmethod
    async def _wait_closed(
            stream_writer: StreamWriter,
            close_result_future: Future[None],
            result_future: Future[None],
          ) -> None:
        """
        Task function that waits for a StreamWriter to be completely closed and
        sets a future based on the result. Does not hold a reference to the
        PacketStreamWriter, so it can be safely cleaned up if the PacketStreamWriter
        is destroyed without closing.
        """
        try:
            # First wait for close() to be called. If an exception is raised, then
            # that is the final result.
            await close_result_future

            # Then wait for the underlying stream to finish closing

            await stream_writer.wait_closed()
            result_future.set_result(None)
        except BaseException as e:
            result_future.set_exception(e)
            raise

    def _start_close_waiter(self):
        """
        Start a task to wait for the underlying StreamWriter to finish closing.
        """
        if self.wait_closed_result.done():
            if self.wait_closed_task is not None:
                self.wait_closed_task.cancel()
                self.wait_closed_task = None
        elif self.wait_closed_task is None:
            self.wait_closed_task = asyncio.create_task(self._wait_closed(self.stream_writer, self.close_result, self.wait_closed_result))


    # @abstractmethod
    def close(self) -> None:
        """
        Close the PacketStreamTransport. Does not wait for
        the stream to be completely closed.

        The remote end of the stream will subsequently receive end-of-stream while attempting to
        read from to the stream, and errors attempting to write to the stream.

        Repeated calls to this method are allowed and will have no effect.
        """
        if not self.close_result.done():
            try:
                self.stream_writer.close()
                self.close_result.set_result(None)
            except BaseException as e:
                self.close_result.set_exception(e)
                raise
        return self.close_result.result()

    # @abstractmethod
    async def wait_closed(self) -> None:
        """
        Wait for the transport to be completely closed. Does not initiate
        closing.
        """
        self._start_close_waiter()
        await self.wait_closed_result

    def __del__(self):
        """
        Destructor. Close the transport and stop the close waiter task if necessary.
        """
        if self.init_completed:
            try:
                if not self.close_result.done():
                    self.close()
            finally:
                wait_closed_task = self.wait_closed_task
                self.wait_closed_task = None
                if wait_closed_task is not None:
                    wait_closed_task.cancel()

