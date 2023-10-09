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

import asyncio

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import DEFAULT_TIMEOUT, DEFAULT_PORT
from ..pkg_logging import logger

from .client_transport import (
    ResponsePackets
  )
from .client_config import AnthemReceiverClientConfig
from ..discovery import AnthemDpSearchRequest, AnthemDpResponseInfo, AnthemDpClient

_cached_dp_responses: Dict[str, AnthemDpResponseInfo] = {}
"""A cache of all known AnthemDp responses, keyed by AnthemDp host name."""

_last_cached_dp_response: Optional[AnthemDpResponseInfo] = None
"""The last AnthemDp response info that was cached."""

_dp_cache_mutex: asyncio.Lock = asyncio.Lock()
"""A mutex to protect the shared AnthemDp cache."""

from ..discovery import AnthemDpClient, AnthemDpResponseInfo

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
                    Anthem Discovery Protocol to discover the receiver.
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
    dp_response_info: Optional[AnthemDpResponseInfo] = None

    if host.startswith('dp://'):
        dp_device_name: Optional[str] = host[5:]
        if dp_device_name == '':
            dp_device_name = None
        async with _dp_cache_mutex:
            if config.cache_dp:
                if dp_device_name is None:
                    if _last_cached_dp_response is not None:
                        dp_response_info = _last_cached_dp_response
                else:
                    dp_response_info = _cached_dp_responses.get(dp_device_name)
            if dp_response_info is None:
                response_wait_time: float = 1.0 if dp_device_name is None else 4.0
                async with AnthemDpClient(response_wait_time=response_wait_time) as client:
                    result: Optional[AnthemDpResponseInfo] = None
                    async with AnthemDpSearchRequest(
                            client,
                            response_wait_time=response_wait_time,
                        ) as search_request:
                        async for info in search_request.iter_responses():
                            if dp_device_name is None:
                                if result is not None:
                                    raise RuntimeError(f"Multiple receivers found for {host}: {result} and {info}")
                                result = info
                            else:
                                if info.datagram.device_name == dp_device_name:
                                    assert result is None
                                    result = info
                                    break
                if result is None:
                    raise RuntimeError("No receiver found" if dp_device_name is None else f"No receiver found with name {dp_device_name!r}")
                dp_response_info = result
                _last_cached_dp_response = dp_response_info
                if dp_device_name is not None:
                    _cached_dp_responses[dp_device_name] = dp_response_info
        result_host = dp_response_info.src_address[0]
        port = dp_response_info.datagram.tcp_port
    elif host.startswith('tcp://') or not '/' in host:
        if host.startswith('tcp://'):
            host = host[6:]
        if ':' in host:
            host, port_str = host.rsplit(':', 1)
            port = int(port_str)
        else:
            port = default_port
        result_host = host
    else:
        raise AnthemReceiverError(f"Invalid host specifier for TCP transport: '{host}'")

    return (result_host, port, dp_response_info)
