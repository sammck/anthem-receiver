# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Enum of IR codes for Anthem receivers.

This file is auto-generated by scripts/gen_ir_codes.py. Do not edit.
"""

from __future__ import annotations

from ..internal_types import *

from .field_converter import ExpandableIntEnumFieldConverter

from enum import Enum


class IRCodeValue(Enum):
    KEY_0                =    0    # Key 0
    KEY_1                =    1    # Key 1
    KEY_2                =    2    # Key 2
    KEY_3                =    3    # Key 3
    KEY_4                =    4    # Key 4
    KEY_5                =    5    # Key 5
    KEY_6                =    6    # Key 6
    KEY_7                =    7    # Key 7
    KEY_8                =    8    # Key 8
    KEY_9                =    9    # Key 9
    POWER_ON             =   10    # Power On
    POWER_OFF            =   11    # Power Off
    SETUP                =   12    # Setup
    INPUT                =   13    # Input
    MODE                 =   14    # Mode
    DIM                  =   15    # Dim
    LEVEL                =   16    # Level
    INFO                 =   17    # Info
    UP                   =   18    # Up
    DOWN                 =   19    # Down
    LEFT                 =   20    # Left
    RIGHT                =   21    # Right
    SELECT               =   22    # Select
    PAGE_UP              =   23    # Page Up
    PAGE_DOWN            =   24    # Page Down
    VOLUME_UP            =   25    # Volume Up
    VOLUME_DOWN          =   26    # Volume Down
    MUTE_TOGGLE          =   27    # Mute Toggle
    LAST                 =   28    # Last
    TONE                 =   29    # Tone
    BASS                 =   30    # Bass
    TREBLE               =   31    # Treble
    LIP_SYNC             =   32    # Lip Sync
    BALANCE              =   33    # Balance
    DYNAMICS             =   34    # Dynamics
    CLEAR                =   35    # Clear
    PRESET               =   36    # Preset

IRCode = Union[IRCodeValue, int]

ir_code_converter: ExpandableIntEnumFieldConverter[IRCodeValue] = ExpandableIntEnumFieldConverter(min_length=4, max_length=4, min_value=0, max_value=9999)
