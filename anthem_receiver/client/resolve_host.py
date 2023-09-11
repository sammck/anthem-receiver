# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver host IP/Port resolver.

Provides a method that can resolve various host pathnames, environment variables,
AnthemDp discovery, etc. into a receiver IP address and port.
"""

from __future__ import annotations

import os
import asyncio
from asyncio import Future
from abc import ABC, abstractmethod

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT
from ..pkg_logging import logger
from ..protocol import Packet, PJ_OK, PJREQ, PJACK, PJNAK

from .client_transport import (
    AnthemReceiverClientTransport,
    ResponsePackets
  )
from .client_config import AnthemReceiverClientConfig

_cached_dp_responses: Dict[str, AnthemDpResponseInfo] = {}
"""A cache of all known AnthemDp responses, keyed by AnthemDp host name."""

_last_cached_dp_response: Optional[AnthemDpResponseInfo] = None
"""The last AnthemDp response info that was cached."""

_dp_cache_mutex: asyncio.Lock = asyncio.Lock()
"""A mutex to protect the shared AnthemDp cache."""

import dp_discovery_protocol as dp
from dp_discovery_protocol import AnthemDpClient, AnthemDpResponseInfo

async def resolve_receiver_tcp_host(
        host: Optional[str]=None,
        default_port: Optional[int]=None,
        config: Optional[AnthemReceiverClientConfig]=None,
      ) -> Tuple[str, int, Optional[AnthemDpResponseInfo]]:
    """Resolves a receiver host string into a TCP/IP hostname and port.

        Args:
            host: The hostname or IPV4 address of the receiver.
                    may optionally be prefixed with "tcp://".
                    May be suffixed with ":<port>" to specify a
                    non-default port, which will override the default_port argument.
                    May be "dp://" or "dp://<dp-hostname>" to use
                    SSDP to discover the receiver.
                    If None, the default host in config is used.
            default_port: The default TCP/IP port number to use. If None, the port
                    will be taken from the config.

        Returns:
            A tuple of (hostname: str, port: int, dp_response_info: Optional[AnthemDpResponseInfo]) where:
                hostname: The resolved IP address or DNS name.
                port:     The resolved port number.
                dp_response_info:
                          The AnthemDp response info, if AnthemDp was used to
                          discover the receiver. None otherwise.
    """
    global _last_cached_dp_response

    config = AnthemReceiverClientConfig(
        default_host=host,
        default_port=default_port,
        base_config=config
    )
    host = config.default_host
    assert host is not None
    default_port = config.default_port
    assert default_port is not None

    result_host: Optional[str] = None
    dp_response_info: Optional[dp.AnthemDpResponseInfo] = None

    if host.startswith('dp://'):
        dp_host: Optional[str] = host[7:]
        if dp_host == '':
            dp_host = None
        async with _dp_cache_mutex:
            if config.cache_dp:
                if dp_host is None:
                    if _last_cached_dp_response is not None:
                        dp_response_info = _last_cached_dp_response
                else:
                    dp_response_info = _cached_dp_responses.get(dp_host)
            if dp_response_info is None:
                filter_headers: Dict[str, str] ={
                    "Manufacturer": "AnthemKENWOOD",
                    "Primary-Proxy": "receiver",
                }

                async with AnthemDpClient(include_loopback=True) as dp_client:
                    async with dp_client.search(filter_headers=filter_headers) as search_request:
                        async for response in search_request:
                            if dp_host is None or response.datagram.hdr_host == dp_host:
                                dp_response_info = response
                                break
                        else:
                            raise AnthemReceiverError("AnthemDp discovery failed to find a receiver")

                assert dp_response_info is not None
                _last_cached_dp_response = dp_response_info
                dp_hostname = dp_response_info.datagram.hdr_host
                if dp_hostname is not None:
                    _cached_dp_responses[dp_hostname] = dp_response_info
        result_host = dp_response_info.src_addr[0]
        optional_port = dp_response_info.datagram.headers.get('Port')
        if optional_port is None:
            port = default_port
        else:
            port = int(optional_port)
    else:
        if host.startswith('tcp://'):
            host = host[6:]
        if ':' in host:
            host, port_str = host.rsplit(':', 1)
            port = int(port_str)
        else:
            port = default_port
        result_host = host

    return (result_host, port, dp_response_info)
