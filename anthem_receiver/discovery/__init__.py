# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Discovery protocol for Anthem AVM receivers.

This subpackage provides a Python implementation of the Anthem AVM 60 discovery protocol.

The protocol uses UDP multicast to advertise the presence of AVM receivers on the network,
and to query existing devices.

Description of the protocol can be found here: https://www.anthemav.com/downloads/MRX-x20-AVM-60-IP-RS-232.xls
"""

from ..version import __version__

from ..internal_types import Jsonable, JsonableDict

from ..exceptions import AnthemReceiverError
from .constants import ANTHEM_DP_DEFAULT_RESPONSE_WAIT_TIME, ANTHEM_DP_MULTICAST_ADDRESS, ANTHEM_DP_PORT
from .dp_datagram import AnthemDpDatagram
from .dp_socket import AnthemDpSocket, AnthemDpSocketBinding, AnthemDpDatagramSubscriber
from .util import CaseInsensitiveDict
from .constants import ANTHEM_DP_MULTICAST_ADDRESS, ANTHEM_DP_PORT
from .client import AnthemDpClient, AnthemDpResponseInfo, AnthemDpSearchRequest
from .server import AnthemDpServer, AnthemDpAdvertisementInfo

__all__ = [
    '__version__',
    'Jsonable', 'JsonableDict',
    'AnthemReceiverError',
    'AnthemDpDatagram',
    'AnthemDpSocket', 'AnthemDpSocketBinding', 'AnthemDpDatagramSubscriber',
    'AnthemDpServer', 'AnthemDpAdvertisementInfo',
    'AnthemDpClient', 'AnthemDpResponseInfo',
    'CaseInsensitiveDict',
    'ANTHEM_DP_DEFAULT_RESPONSE_WAIT_TIME',
    'ANTHEM_DP_MULTICAST_ADDRESS', 'ANTHEM_DP_PORT',
]
