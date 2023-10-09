# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
PVC Receiver known command codes and metadata.

This module contains the known command codes and metadata for the Anthem receiver protocol.
Much of the information in this module is derived from Anthem's documentation here:

https://www.anthemav.com/downloads/MRX-x20-AVM-60-IP-RS-232.xls

There is no protocol implementation here; only metadata about the protocol.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..pkg_logging import logger
from ..internal_types import *
from ..exceptions import AnthemReceiverError
from .constants import (
    PacketType,
    PACKET_MAGIC,
    END_OF_PACKET_BYTES,
  )

class Field:
    

class FieldType(ABC):
    name: str

    def __init__(self, name: str, ) -> None:
        self.name = name

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        return str(self)
    
    @abstractmethod
    def
    
class ZoneFieldType(FieldType):
    def __init__(self, name: str) -> None:
        super().__init__(name)
