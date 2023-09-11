#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Simple utility functions used by this package
"""

from __future__ import annotations

from typing_extensions import SupportsIndex

import netifaces
import sys
import socket
import ipaddress
from ipaddress import IPv4Address, IPv6Address

from ..internal_types import *

from email.parser import BytesHeaderParser
from email.message import Message as EmailParserMessage
from email.header import Header as EmailParserHeader
from requests.structures import CaseInsensitiveDict

def get_local_ip_addresses_and_interfaces(
        address_family: Union[socket.AddressFamily, int]=socket.AF_INET,
        include_loopback: bool=True
    ) -> List[Tuple[str, str]]:
    """Returns a list of Tuple[ip_address: str, interface_name: str] for the IP addresses of the local host
       in a requested address family. The result is sorted in a way that attempts to place the "preferred"
       canonical IP address first in the list, according to the following scheme:
           1. Addresses on the default gateway interface precede all other addresses.
           2. Non-loopback addresses precede loopback addresses.
           3. IPV4 addresses that begin with 172. follow other IPV4 addresses. This is a hack to
              deprioritize local docker network addresses.
    """
    result_with_priority: List[Tuple[int, str, str]] = []
    assert int(address_family) in (int(socket.AF_INET), int(socket.AF_INET6))
    is_ipv6 = int(address_family) == int(socket.AF_INET6)
    _, default_gateway_ifname = get_default_ip_gateway(address_family)
    netiface_family = netifaces.AF_INET6 if is_ipv6 else netifaces.AF_INET
    for ifname in netifaces.interfaces():
        ifinfo = netifaces.ifaddresses(ifname)
        if netiface_family in ifinfo:
            for addrinfo in ifinfo[netiface_family]:
              ip_str = addrinfo['addr']
              assert isinstance(ip_str, str)
              if ifname == default_gateway_ifname:
                  priority = 0
              elif is_ipv6 and IPv6Address(ip_str).is_loopback:
                  if not include_loopback:
                      continue
                  priority = 3
              elif not is_ipv6 and IPv4Address(ip_str).is_loopback:
                  if not include_loopback:
                      continue
                  priority = 3
              elif not is_ipv6 and ip_str.startswith('172.'):
                  priority = 2
              else:
                  priority = 1

              result_with_priority.append((priority, ip_str, ifname))
    return [ (ip, ifname) for _, ip, ifname in sorted(result_with_priority)]

def get_local_ip_addresses(address_family: Union[socket.AddressFamily, int]=socket.AF_INET, include_loopback: bool=True) -> List[str]:
    """Returns a List[ip_address: str] for the IP addresses of the local host
       in a requested address family. The result is sorted in a way that attempts to place the "preferred"
       canonical IP address first in the list, according to the following scheme:
           1. Addresses on the default gateway interface precede all other addresses.
           2. Non-loopback addresses precede loopback addresses.
           3. IPV4 addresses that begin with 172. follow other IPV4 addresses. This is a hack to
              deprioritize local docker network addresses."""
    return [ ip for ip, _ in get_local_ip_addresses_and_interfaces(address_family, include_loopback=include_loopback)]

def get_default_ip_gateway(address_family: socket.AddressFamily | int=socket.AF_INET) -> Tuple[Optional[str], Optional[str]]:
    """Returns the (gateway_ip_address: str, gateway_interface_name: str) for the default IP gateway in the
       requested family, if any.
       returns (None, None) if there is no default gateway in the requested family."""
    assert int(address_family) in (int(socket.AF_INET), int(socket.AF_INET6))
    netiface_family = netifaces.AF_INET if int(address_family) == int(socket.AF_INET) else netifaces.AF_INET6
    gws = netifaces.gateways()
    if "default" in gws:
        default_gateway_infos = gws["default"]
        if netiface_family in default_gateway_infos:
            gw_ip, gw_interface_name = default_gateway_infos[netiface_family][:2]
            return (gw_ip, gw_interface_name)
    return (None, None)
