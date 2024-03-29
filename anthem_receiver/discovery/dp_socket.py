#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
AnthemDpSocket -- An abstract base class for an AnthemDp socket that can:

  1. Listen on either a multicast or unicast address
  2. Receive and decode AnthemDpDatagrams from remote nodes and deliver them to any number of async subscribers
  3. Send AnthemDpDatagrams to a remote multicast or unicast address

  The subscriber interface is a simple async iterator that returns a sequents of (HostAndPort, AnthemDpdatagram)
  tuples until the socket is closed.

  Subclasses must implement the create_socket() method to create and bind the socket that will be used to
  receive and send datagrams.
"""

from __future__ import annotations


import asyncio
from asyncio import Future
import socket
from abc import ABC, abstractmethod

from ..internal_types import *
from ..pkg_logging import logger
from ..exceptions import AnthemReceiverError
from .dp_datagram import AnthemDpDatagram

MAX_QUEUE_SIZE = 1000

class AnthemDpSocketBinding:
    """
    An encapsulation of the binding of an AnthemDpSocket to a single low-level
    bound datagram socket. There is one instance of this class created for each
    low-level socket that is in use (typically one per network interface).

    Instances of this class are created prior to loop.create_datagram_endpoint,
    and are later bound to the _AnthemDpSocketProtocol instance that is created by
    loop.create_datagram_endpoint.
    """

    dp_socket: Optional[AnthemDpSocket] = None
    """The AnthemDpSocket that is bound to this low-level socket. """

    index: int = -1
    """The index of this socket binding within AnthemDpSocket. Set to -1 until this socket binding is added."""

    sock: Optional[socket.socket] = None
    """The low-level socket that is bound to this AnthemDpSocket."""

    _protocol: Optional[_AnthemDpSocketProtocol] = None
    """The adapter between the asyncio transport and this AnthemDpSocket.
       This is set when the _AnthemDpSocketProtocol instance is created by
       loop.create_datagram_endpoint()."""

    _transport: Optional[asyncio.DatagramTransport] = None
    """The asyncio transport that is bound to this AnthemDpSocket. This is set
       either when _AnthemDpSocketProtocol.connection_made() is called, or
       when the transport is returned to AnthemDpSocket by
       loop.create_datagram_endpoint()."""

    unicast_addr: HostAndPort
    """The unicast ip address and port associated with this binding. If
       the binding is unicast then this will be the same as the socket
       local IP address."""

    sockname: str
    """The name of the socket as it should be displayed in logs, etc"""

    def __init__(
            self,
            sock: socket.socket,
            unicast_addr: Optional[HostAndPort]=None,
            sockname: Optional[str]=None):
        self.sock = sock
        if unicast_addr is None:
            unicast_addr = sock.getsockname()
            assert isinstance(unicast_addr, tuple)
        self.unicast_addr = unicast_addr
        if sockname is None:
            bound_addr = sock.getsockname()
            if bound_addr == unicast_addr:
                sockname = str(bound_addr)
            else:
                sockname = f"{bound_addr}@{unicast_addr}"
        self.sockname = sockname

    async def attach_to_dp_socket(self, dp_socket: AnthemDpSocket, index: int) -> None:
        if self.index >= 0:
            raise AnthemReceiverError(f"Attempt to reattach AnthemDpSocketBinding: {self}")
        assert self.dp_socket is None or self.dp_socket == dp_socket
        self.dp_socket = dp_socket
        self.index = index

    @property
    def transport(self) -> Optional[asyncio.DatagramTransport]:
        return self._transport

    @transport.setter
    def transport(self, transport: Optional[asyncio.DatagramTransport]) -> None:
        if transport != self._transport:
            assert self._transport is None or transport is None
        self._transport = transport

    @property
    def protocol(self) -> Optional[_AnthemDpSocketProtocol]:
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: _AnthemDpSocketProtocol) -> None:
        if protocol != self._protocol:
            assert self._protocol is None
        self._protocol = protocol

    def sendto(self, datagram: AnthemDpDatagram, addr: HostAndPort) -> None:
        logger.debug(f"Sending AnthemDpDatagram via {self} to {addr}: {datagram}")
        assert not self.transport is None
        self.transport.sendto(datagram.raw_data, addr)

    def __str__(self) -> str:
        return f"AnthemDpSocketBinding({self.index}: {self.sockname})"

    def __repr__(self) -> str:
        return str(self)

class _AnthemDpSocketProtocol(asyncio.DatagramProtocol, ABC):
    """An adapter between the asyncio transport and AnthemDpSocket. There is one instance of this class
       created for each low-level socket that is created (typically one per network interface).
       """
    socket_binding: AnthemDpSocketBinding

    def __init__(self, socket_binding: AnthemDpSocketBinding):
        self.socket_binding = socket_binding
        socket_binding.protocol = self

    @property
    def dp_socket(self) -> AnthemDpSocket:
        assert self.socket_binding.dp_socket is not None
        return self.socket_binding.dp_socket

    @property
    def transport(self) -> Optional[asyncio.DatagramTransport]:
        return self.socket_binding.transport

    @transport.setter
    def transport(self, transport: Optional[asyncio.DatagramTransport]) -> None:
        self.socket_binding.transport = transport

    def connection_made(self, transport: asyncio.BaseTransport):
        """Called when a connection is made."""

        # Note: There is a problem with asyncio datagram transports in that they do not inherit from
        # asyncio.DatagramTransport.  It is not serious since they implement the same interface, but
        # it does cause this assertion to fail, so it is commented out here and the mypy warning is suppressed.
        # assert isinstance(transport, asyncio.DatagramTransport)
        assert self.transport is None
        try:
            self.transport = transport # type: ignore[assignment]
            self.dp_socket.connection_made(self.socket_binding)
        except BaseException as e:
            self.dp_socket.set_final_exception(e)
            raise

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """Called when some datagram is received."""
        try:
            self.dp_socket.datagram_received(self.socket_binding, addr, data)
        except BaseException as e:
            self.dp_socket.set_final_exception(e)
            raise

    def error_received(self, exc: Exception):
        """Called when a send or receive operation raises an OSError.

        (Other than BlockingIOError or InterruptedError.)
        """
        try:
            self.dp_socket.error_received(self.socket_binding, exc)
        except BaseException as e:
            self.dp_socket.set_final_exception(e)
            raise

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Called when the connection is lost or closed."""
        try:
            self.dp_socket.connection_lost(self.socket_binding, exc)
        except BaseException as e:
            self.dp_socket.set_final_exception(e)
            raise
        self.transport = None


class AnthemDpDatagramSubscriber(
        AsyncContextManager['AnthemDpDatagramSubscriber'],
        AsyncIterable[Tuple[AnthemDpSocketBinding, HostAndPort, AnthemDpDatagram]]
      ):
    dp_socket: AnthemDpSocket
    queue: asyncio.Queue[Optional[Tuple[AnthemDpSocketBinding, HostAndPort, AnthemDpDatagram]]]
    final_result: Future[None]
    eos: bool = False
    eos_exc: Optional[Exception] = None

    def __init__(self, dp_socket: AnthemDpSocket, max_queue_size: int=MAX_QUEUE_SIZE):
        self.dp_socket = dp_socket
        self.queue = asyncio.Queue(max_queue_size)
        self.final_result = Future()

    async def __aenter__(self) -> AnthemDpDatagramSubscriber:
        await self.dp_socket.add_subscriber(self)
        return self

    async def __aexit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType]
      ) -> bool:
        await self.dp_socket.remove_subscriber(self)
        self.set_final_result()
        try:
            # ensure that final_result has been awaited
            await self.final_result
        except BaseException as e:
            pass
        return False

    async def iter_datagrams(self) -> AsyncIterator[Tuple[AnthemDpSocketBinding, HostAndPort, AnthemDpDatagram]]:
        while True:
            result = await self.receive()
            if result is None:
                break
            yield result

    def __aiter__(self) -> AsyncIterator[Tuple[AnthemDpSocketBinding, HostAndPort, AnthemDpDatagram]]:
        return self.iter_datagrams()

    def set_final_result(self) -> None:
        if not self.final_result.done():
            self.final_result.set_result(None)
            if not self.queue is None:
                # wake up any waiting tasks
                try:
                    self.queue.put_nowait(None)
                except asyncio.QueueFull:
                    # queue is full so waiters will wake up soon
                    pass
            self.eos = True
            self.eos_exc = None

    def set_final_exception(self, e: BaseException) -> None:
        if not self.final_result.done():
            self.final_result.set_exception(e)
            if not self.queue is None:
                # wake up any waiting tasks
                try:
                    self.queue.put_nowait(None)
                except asyncio.QueueFull:
                    # queue is full so waiters will wake up soon
                    pass
            self.eos = True
            self.eos_exc = None

    async def receive(self) -> Optional[Tuple[AnthemDpSocketBinding, HostAndPort, AnthemDpDatagram]]:
        if self.final_result.done():
            await self.final_result
            return None
        if self.eos and self.queue.empty():
            if self.eos_exc is None:
                self.set_final_result()
            else:
                self.set_final_exception(self.eos_exc)
            await self.final_result
            return None
        try:
          result =  await self.queue.get()
          self.queue.task_done()
          if result is None:
              if not self.final_result.done():
                  assert self.eos
                  if self.eos_exc is None:
                      self.set_final_result()
                  else:
                      self.set_final_exception(self.eos_exc)
              await self.final_result
              return None
        except BaseException as e:
            self.set_final_exception(e)
            raise
        return result

    def on_datagram(self, socket_binding: AnthemDpSocketBinding, addr: HostAndPort, datagram: AnthemDpDatagram) -> None:
        if not self.eos and not self.final_result.done():
            try:
                self.queue.put_nowait((socket_binding, addr, datagram))
            except asyncio.QueueFull:
                logger.warning(f"Queue full, dropping datagram from {socket_binding} {addr}: {datagram}")

    def on_end_of_stream(self, exc: Optional[Exception]=None) -> None:
        if not self.eos and not self.final_result.done():
            self.eos = True
            self.eos_exc = exc
            try:
                # wake up any waiting tasks
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                # queue is full so waiters will wake up soon
                pass

class AnthemDpSocket(AsyncContextManager['AnthemDpSocket']):
    """
    An abstract async AnthemDp socket that can:

      1. Listen on either a multicast or unicast address
      2. Receive and decode AnthemDpDatagrams from remote nodes and deliver them to any number of async subscribers
      3. Send AnthemDpDatagrams to a remote multicast or unicast address

      The subscriber interface is a simple async iterator that returns a sequents of (HostAndPort, AnthemDpdatagram)
      tuples until the socket is closed.

      Subclasses must implement the create_socket() method to create and bind the socket that will be used to
      receive and send datagrams.
    """

    socket_bindings: List[AnthemDpSocketBinding]
    """A list of AnthemDpSocketBinding instances, one for each low-level socket that is in use."""

    final_result: Future[None]
    """A future that is set when the dp_socket is stopped."""

    datagram_subscribers: Set[AnthemDpDatagramSubscriber] = set()
    """A set of subscribers that wish to receive AnthemDp Datagrams."""

    def __init__(self):
        self.final_result = Future()
        self.socket_bindings = []

    async def add_subscriber(self, subscriber: AnthemDpDatagramSubscriber) -> None:
        self.datagram_subscribers.add(subscriber)

    async def remove_subscriber(self, subscriber: AnthemDpDatagramSubscriber) -> None:
        self.datagram_subscribers.remove(subscriber)

    async def add_socket_binding(self, socket_binding: AnthemDpSocketBinding) -> None:
        if socket_binding.index >= 0:
            raise AnthemReceiverError(f"Attempt to reattach AnthemDpSocketBinding: {socket_binding}")
        i = len(self.socket_bindings)
        self.socket_bindings.append(socket_binding)
        await socket_binding.attach_to_dp_socket(self, i)
        logger.debug(f"Added socket binding {i}: {socket_binding}")

    @abstractmethod
    async def add_socket_bindings(self) -> None:
        """Abstract method that creates and binds the sockets that will be used to receive
           and send datagrams (typically one per interface), and adds them with self.add_socket_binding().
           Must be overridden by subclasses."""
        raise NotImplementedError()

    async def finish_start(self) -> None:
        """Called after the socket is up and running.  Subclasses can override to do additional
           initialization."""
        pass

    async def start(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            await self.add_socket_bindings()
            if len(self.socket_bindings) == 0:
                raise AnthemReceiverError("No datagram sockets were added to AnthemDpSocket")

            for socket_binding in self.socket_bindings:
                untyped_transport, protocol = await loop.create_datagram_endpoint(
                    lambda: _AnthemDpSocketProtocol(socket_binding),
                    sock=socket_binding.sock
                  )
                # Note: There is a problem with asyncio datagram transports in that they do not inherit from
                # asyncio.DatagramTransport.  It is not serious since they implement the same interface, but
                # it does cause mypy to complain.  The following nonsense is a workaround to make mypy happy.
                # assert isinstance(transport, asyncio.DatagramTransport)
                transport: asyncio.DatagramTransport = untyped_transport # type: ignore[assignment]
                assert isinstance(protocol, _AnthemDpSocketProtocol)
                logger.debug(f"Created datagram endpoint for {socket_binding}. transport={transport}, protocol={protocol}")
                socket_binding.protocol = protocol
                socket_binding.transport = transport

            await self.finish_start()

        except BaseException as e:
            self.set_final_exception(e)
            try:
                await self.wait_for_done()
            except BaseException as e:
                pass
            raise

    async def stop(self) -> None:
        """Stops the AnthemDpSocket."""
        self._close_all_transports()

    async def wait_for_dependents_done(self) -> None:
        """Called after final_result has been awaited.  Subclasses can override to do additional
           cleanup."""
        pass

    async def wait_for_done(self) -> None:
        try:
            await self.final_result
        finally:
            await self.wait_for_dependents_done()

    async def stop_and_wait(self) -> None:
        await self.stop()
        await self.wait_for_done()

    def connection_made(self, socket_binding: AnthemDpSocketBinding) -> None:
        """Called when a connection is made."""
        logger.debug(f"Connection made: {socket_binding}")

    def datagram_received(self, socket_binding: AnthemDpSocketBinding, addr: HostAndPort, data: bytes):
        """Called when some datagram is received."""
        try:
            datagram = AnthemDpDatagram(raw_data=data)
            logger.debug(f"Received datagram from {socket_binding} {addr}: {datagram}")
            subscribers = list(self.datagram_subscribers)
            for subscriber in subscribers:
                try:
                    subscriber.on_datagram(socket_binding, addr, datagram)
                except BaseException as e:
                    logger.warning(f"Subscriber raised exception processing datagram {datagram}: {e}")
        except BaseException as e:
            logger.warning(f"Error parsing datagram from {addr}, raw=[{data!r}]: {e}")
        # self.transport.sendto(data, addr)

    def error_received(self, socket_binding: AnthemDpSocketBinding, exc: Exception) -> None:
        """Called when a send or receive operation raises an OSError.

        (Other than BlockingIOError or InterruptedError.)
        """
        logger.info(f"Error received from transport {socket_binding}: {exc}")
        # TODO: End all socket bindings if any socket fails
        subscribers = list(self.datagram_subscribers)
        for subscriber in subscribers:
            try:
                subscriber.on_end_of_stream(exc)
            except BaseException as e:
                logger.warning(f"Subscriber raised exception processing transport error: {e}")
        self.set_final_exception(exc)


    def connection_lost(self, socket_binding: AnthemDpSocketBinding, exc: Optional[Exception]) -> None:
        """Called when the connection is lost or closed."""
        logger.debug(f"Connection to transport lost on {socket_binding}, exc={exc}")
        self.transport = None
        # TODO: End all socket bindings if any socket fails
        subscribers = list(self.datagram_subscribers)
        for subscriber in subscribers:
            try:
                subscriber.on_end_of_stream(exc)
            except BaseException as e:
                logger.warning(f"Subscriber raised exception processing transport connection loss: {e}")
        if exc is None:
            self.set_final_result()
        else:
            self.set_final_exception(exc)

    def _close_all_transports(self) -> None:
        for socket_binding in self.socket_bindings:
            if not socket_binding.transport is None:
                try:
                    socket_binding.transport.close()
                except BaseException as e:
                    logger.error(f"Error closing transport on {socket_binding}: {e}")
                socket_binding.transport = None

    def _close_all_socks(self) -> None:
        for socket_binding in self.socket_bindings:
            if not socket_binding.sock is None:
                try:
                    socket_binding.sock.close()
                    socket_binding.sock = None
                except BaseException as e:
                    logger.error(f"Error closing socket on {socket_binding}: {e}")

    def set_final_exception(self, exc: BaseException) -> None:
        assert not exc is None
        if not self.final_result.done():
            logger.debug(f"AnthemDpSocket: Setting final exception: {exc}")
            self.final_result.set_exception(exc)
            self._close_all_transports()
            self._close_all_socks()

    def set_final_result(self) -> None:
        if not self.final_result.done():
            logger.debug(f"AnthemDpSocket: Setting final result to success")
            self.final_result.set_result(None)
            self._close_all_transports()
            self._close_all_socks()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType]
      ) -> bool:
        if exc is None:
            self.set_final_result()
        else:
            self.set_final_exception(exc)
        try:
            # ensure that final_result has been awaited
            await self.wait_for_done()
        except Exception as e:
            pass
        return False
