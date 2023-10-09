# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
AnthemDpClient -- An AnthemDp client that can:

  1. Send a discovery request to a multicast UDP address (typically 255.255.255.255:14999)
  2. Receive and decode discovery response AnthemDpDatagram's from remote nodes
  3. Collect and return responses received within a configurable timeout period
"""

from __future__ import annotations


import asyncio
from asyncio import Future
import socket
import sys
import re
import time
import datetime
from contextlib import asynccontextmanager

from ..internal_types import *
from ..pkg_logging import logger
from .constants import ANTHEM_DP_MULTICAST_ADDRESS, ANTHEM_DP_PORT

from .dp_datagram import AnthemDpDatagram
from .dp_socket import AnthemDpSocket, AnthemDpSocketBinding, AnthemDpDatagramSubscriber
from .util import get_local_ip_addresses, CaseInsensitiveDict

ANTHEM_DP_DEFAULT_RESPONSE_WAIT_TIME = 4.0
"""The default amount of time (in seconds) to wait for responses to come in."""

class AnthemDpResponseInfo:
    socket_binding: AnthemDpSocketBinding
    """The socket binding on which the response was received"""

    src_addr: HostAndPort
    """The source address of the response"""

    datagram: AnthemDpDatagram
    """The response datagram"""

    monotonic_time: float
    """The local time (in seconds) since an arbitrary point in the past at which
       the advertisement was received, as returned by time.monotonic(). This
       value is useful for calculating the age of the advertisement and expiring
       after Max-Age seconds."""

    utc_time: datetime.datetime
    """The UTC time at which the advertisement was received, as returned by
        datetime.datetime.utcnow()."""

    def __init__(
            self,
            socket_binding: AnthemDpSocketBinding,
            src_addr: HostAndPort,
            datagram: AnthemDpDatagram,
          ) -> None:
        self.socket_binding = socket_binding
        self.src_addr = src_addr
        self.datagram = datagram
        self.monotonic_time = time.monotonic()
        self.utc_time = datetime.datetime.utcnow()

    def __str__(self) -> str:
        return f"AnthemDpResponse(addr={self.src_addr}, {self.datagram})"

    def __repr__(self) -> str:
        return str(self)
class AnthemDpSearchRequest(
        AsyncContextManager['AnthemDpSearchRequest'],
        AsyncIterable[AnthemDpResponseInfo]
      ):
    """An object that manages a single search request on an AnthemDpClient and all of the received responses
       within an AsyncContextManager/AsyncInterable interface."""

    dp_client: AnthemDpClient

    dg_subscriber: AnthemDpDatagramSubscriber
    response_wait_time: float
    max_responses: int
    end_time: float = 0.0

    def __init__(
            self,
            dp_client: AnthemDpClient,
            response_wait_time: Optional[float]=None,
            max_responses: int=0,
          ):
        """Create an async context manager/iterable that sends a multicast search request and returns the responses
        as they arrive.

        Parameters:
            dp_client:             The AnthemDpClient instance to use for sending the search request and receiving responses.
            response_wait_time:      The amount of time (in seconds) to wait for responses to come in. Defaults to
                                        dp_client.response_wait_time.
            max_responses:           The maximum number of responses to return. If 0 (the default), all responses received
                                        within response_wait_time will be returned.

        Usage:
            async with AnthemDpSearchRequest(dp_client, ...) as search_request:
                async for response in search_request:
                    print(response.datagram.headers)
                    # It is possible to break out of the loop early if desired; e.g., if you got the response you were looking for..
        """
        self.dp_client = dp_client
        self.response_wait_time = dp_client.response_wait_time if response_wait_time is None else response_wait_time
        self.max_responses = max_responses
        self.dg_subscriber = AnthemDpDatagramSubscriber(self.dp_client)

    async def __aenter__(self) -> AnthemDpSearchRequest:
        # It is important that we start the subscriber before we send the search request so that we don't miss any responses.
        await self.dg_subscriber.__aenter__()
        try:
            for socket_binding in self.dp_client.socket_bindings:
                search_datagram = AnthemDpDatagram.new_query()
                socket_binding.sendto(search_datagram, (self.dp_client.multicast_address, self.dp_client.multicast_port))
            self.end_time = time.monotonic() + self.response_wait_time
        except BaseException as e:
            # A call to __aenter__ that raises an exception will not be paired with a call to __aexit__; since we successfully called __aenter__
            # on the dg_subscriber, we need to call __aexit__ on it to ensure that it is cleaned up properly.
            await self.dg_subscriber.__aexit__(type(e), e, e.__traceback__)
            raise
        return self

    async def __aexit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType]
      ) -> bool:
        return await self.dg_subscriber.__aexit__(exc_type, exc, tb)

    async def iter_responses(self) -> AsyncIterator[AnthemDpResponseInfo]:
        n = 0
        while True:
            if self.max_responses > 0 and n >= self.max_responses:
                break
            remaining_time = self.end_time - time.monotonic()
            if remaining_time <= 0.0:
                break
            try:
                resp_tuple = await asyncio.wait_for(self.dg_subscriber.receive(), remaining_time)
            except asyncio.TimeoutError:
                break
            if resp_tuple is None:
                break
            socket_binding, addr, datagram = resp_tuple
            if not datagram.announce_request and datagram.device_name != '':
                info = AnthemDpResponseInfo(socket_binding, addr, datagram)
                logger.debug(f"Received AnthemDp response from {addr} on {socket_binding}: {datagram}")
                n += 1
                yield info

    def __aiter__(self) -> AsyncIterator[AnthemDpResponseInfo]:
        return self.iter_responses()


class AnthemDpClient(AnthemDpSocket, AsyncContextManager['AnthemDpClient']):
    """
    An AnthemDp client that can:

      1. Send a discovery request to a multicast UDP address (typically 255.255.255.255:14999)
      2. Receive and decode discovery response AnthemDpDatagram's from remote nodes
      3. Collect and return responses received within a configurable timeout period
    """
    response_wait_time: float
    """The amount of time (in seconds) to wait for all responses to come in. By default,
       this is set to 3.0 seconds."""

    multicast_address: str = ANTHEM_DP_MULTICAST_ADDRESS
    """The multicast address to send requests to."""

    multicast_port: int = ANTHEM_DP_PORT
    """The multicast port to send requests to."""

    bind_addresses: List[str]
    """The local IP addresses to bind to. If None, all local IP addresses will be used."""

    include_loopback: bool = False
    """If True, loopback addresses will be included in the list of local IP addresses to bind to."""

    def __init__(
            self,
            search_pattern: str="*",
            response_wait_time: float=ANTHEM_DP_DEFAULT_RESPONSE_WAIT_TIME,
            multicast_address: str=ANTHEM_DP_MULTICAST_ADDRESS,
            multicast_port: int=ANTHEM_DP_PORT,
            bind_addresses: Optional[Iterable[str]]=None,
            include_loopback: bool = False
          ) -> None:
        super().__init__()
        self.search_pattern = search_pattern
        self.response_wait_time = response_wait_time
        self.multicast_address = multicast_address
        self.multicast_port = multicast_port
        self.include_loopback = include_loopback
        if bind_addresses is None:
            bind_addresses = [ '' ]
        self.bind_addresses = list(bind_addresses)

    #@override
    async def add_socket_bindings(self) -> None:
        """Abstract method that creates and binds the sockets that will be used to receive
           and send datagrams (typically one per interface), and adds them with self.add_socket_binding().
           Must be overridden by subclasses."""

        # Create a socket for each bind address
        addrinfo = socket.getaddrinfo(self.multicast_address, self.multicast_port)[0]
        address_family = addrinfo[0]
        assert address_family in (socket.AF_INET, socket.AF_INET6)
        is_ipv6 = address_family == socket.AF_INET6
        group_bin = socket.inet_pton(address_family, addrinfo[4][0])
        logger.debug(f"Creating socket bindings to {self.bind_addresses}")
        for bind_address in self.bind_addresses:
            sock = socket.socket(address_family, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if sys.platform not in ( 'win32', 'cygwin' ):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind((bind_address, self.multicast_port))
            socket_binding = AnthemDpSocketBinding(sock, unicast_addr=sock.getsockname())
            await self.add_socket_binding(socket_binding)

    async def finish_start(self) -> None:
        """Called after the socket is up and running.  Subclasses can override to do additional
           initialization."""
        pass

    async def wait_for_dependents_done(self) -> None:
        """Called after final_result has been awaited.  Subclasses can override to do additional
           cleanup."""
        pass

    def search(
            self,
            response_wait_time: Optional[float]=None,
            max_responses: int=0,
          ) -> AnthemDpSearchRequest:
        """Create an async context manager/iterable that sends a multicast search request and returns the responses
           as they arrive.

        Parameters:
            search_pattern:          The search pattern to use. Defaults to "*" (all devices).
            response_wait_time:      The amount of time (in seconds) to wait for responses to come in. Defaults to
                                        dp_client.response_wait_time.
            max_responses:           The maximum number of responses to return. If 0 (the default), all responses received
                                        within response_wait_time will be returned.

        Usage:
            async with dp_client.search(...) as search_request:
                async for response in search_request:
                    print(response.datagram.headers)
                    # It is possible to break out of the loop early if desired; e.g., if you got the response you were looking for..
        """
        return AnthemDpSearchRequest(
                self,
                response_wait_time=response_wait_time,
                max_responses=max_responses,
              )

    async def simple_search(
            self,
            response_wait_time: Optional[float]=None,
            max_responses: int=0,
          ) -> List[AnthemDpResponseInfo]:
        """A simple search that creates a search request, waits for a fixed time for all responses to come in,
           and returns the responses. Does not allow for early termination of the search when
           a desired response is received.

           Early out/incremental results can be obtained by using the search() method.

        Parameters:
            dp_client:             The AnthemDpClient instance to use for sending the search request and receiving responses.
            search_pattern:          The search pattern to use. Defaults to "*" (all devices).
            response_wait_time:      The amount of time (in seconds) to wait for responses to come in. Defaults to
                                        dp_client.response_wait_time.
            max_responses:           The maximum number of responses to return. If 0 (the default), all responses received
                                        within response_wait_time will be returned.
        """
        results: List[AnthemDpResponseInfo] = []
        async with self.search(
                response_wait_time=response_wait_time,
                max_responses=max_responses,
              ) as search_request:
            async for response in search_request:
                results.append(response)
        return results

    async def __aenter__(self) -> AnthemDpClient:
        await super().__aenter__()
        return self
