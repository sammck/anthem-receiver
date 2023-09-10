# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver host IP/Port resolver.

Provides a method that can resolve various host pathnames, environment variables,
SDDP discovery, etc. into a receiver IP address and port.
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

_cached_sddp_responses: Dict[str, SddpResponseInfo] = {}
"""A cache of all known SDDP responses, keyed by SDDP host name."""

_last_cached_sddp_response: Optional[SddpResponseInfo] = None
"""The last SDDP response info that was cached."""

_sddp_cache_mutex: asyncio.Lock = asyncio.Lock()
"""A mutex to protect the shared SDDP cache."""

import sddp_discovery_protocol as sddp
from sddp_discovery_protocol import SddpClient, SddpResponseInfo

async def resolve_receiver_tcp_host(
        host: Optional[str]=None,
        default_port: Optional[int]=None,
        config: Optional[AnthemReceiverClientConfig]=None,
      ) -> Tuple[str, int, Optional[SddpResponseInfo]]:
    """Resolves a receiver host string into a TCP/IP hostname and port.

        Args:
            host: The hostname or IPV4 address of the receiver.
                    may optionally be prefixed with "tcp://".
                    May be suffixed with ":<port>" to specify a
                    non-default port, which will override the default_port argument.
                    May be "sddp://" or "sddp://<sddp-hostname>" to use
                    SSDP to discover the receiver.
                    If None, the default host in config is used.
            default_port: The default TCP/IP port number to use. If None, the port
                    will be taken from the config.

        Returns:
            A tuple of (hostname: str, port: int, sddp_response_info: Optional[SddpResponseInfo]) where:
                hostname: The resolved IP address or DNS name.
                port:     The resolved port number.
                sddp_response_info:
                          The SDDP response info, if SDDP was used to
                          discover the receiver. None otherwise.
    """
    global _last_cached_sddp_response

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
    sddp_response_info: Optional[sddp.SddpResponseInfo] = None

    if host.startswith('sddp://'):
        sddp_host: Optional[str] = host[7:]
        if sddp_host == '':
            sddp_host = None
        async with _sddp_cache_mutex:
            if config.cache_sddp:
                if sddp_host is None:
                    if _last_cached_sddp_response is not None:
                        sddp_response_info = _last_cached_sddp_response
                else:
                    sddp_response_info = _cached_sddp_responses.get(sddp_host)
            if sddp_response_info is None:
                filter_headers: Dict[str, str] ={
                    "Manufacturer": "AnthemKENWOOD",
                    "Primary-Proxy": "receiver",
                }

                async with SddpClient(include_loopback=True) as sddp_client:
                    async with sddp_client.search(filter_headers=filter_headers) as search_request:
                        async for response in search_request:
                            if sddp_host is None or response.datagram.hdr_host == sddp_host:
                                sddp_response_info = response
                                break
                        else:
                            raise AnthemReceiverError("SDDP discovery failed to find a receiver")

                assert sddp_response_info is not None
                _last_cached_sddp_response = sddp_response_info
                sddp_hostname = sddp_response_info.datagram.hdr_host
                if sddp_hostname is not None:
                    _cached_sddp_responses[sddp_hostname] = sddp_response_info
        result_host = sddp_response_info.src_addr[0]
        optional_port = sddp_response_info.datagram.headers.get('Port')
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

    return (result_host, port, sddp_response_info)
