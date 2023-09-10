#!/usr/bin/env python3

# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
A REST FastAPI server that controls a Anthem receiver.
"""

from __future__ import annotations

import logging

logger = logging.getLogger('anthem_receiver.rest_server')
