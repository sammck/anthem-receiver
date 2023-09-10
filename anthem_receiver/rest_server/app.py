#!/usr/bin/env python3

# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
A REST FastAPI server that controls a Anthem receiver.
"""

from __future__ import annotations

from fastapi import FastAPI

import time
import os
import sys
import json
import asyncio

from signal import SIGINT, SIGTERM
from contextlib import asynccontextmanager

from .logger import logger
from ..internal_types import *
from .. import (
    __version__ as pkg_version,
    DEFAULT_PORT,
    AnthemReceiverClient,
    AnthemCommand,
    AnthemResponse,
    AnthemModel,
    models,
    anthem_receiver_connect,
    AnthemReceiverClientConfig,
    full_class_name
  )

from .api import router as api_router

@asynccontextmanager
async def fastapi_lifetime(app: FastAPI) -> None:
    """
    A context manager that initializes and cleans up for FastAPI.
    """

    try:
        logger.info("Receiver REST server starting up--initializing...")
        config_file = os.environ.get("anthem_receiver_CONFIG", None)
        if config_file is None:
            if os.path.exists("anthem_receiver_config.json"):
                config_file = "anthem_receiver_config.json"
        if config_file is None:
            raw_config: JsonableDict = {}
        else:
            with open(config_file, "r") as f:
                raw_config: JsonableDict = json.load(f)
        app.state.raw_config = raw_config
        Anthem_config = AnthemReceiverClientConfig.from_jsonable(raw_config)
        app.state.Anthem_config = Anthem_config
        app.state.launch_time = time.monotonic()
        Anthem_client = await anthem_receiver_connect(config=Anthem_config)
        app.state.Anthem_client = Anthem_client
        logger.info(f"Serving API for receiver at {Anthem_client}...")

        logger.info("Receiver REST server initialization done; starting server...")
        yield
    finally:
        logger.info("Receiver REST server shutting down--cleaning up...")

proj_api = FastAPI(lifespan=fastapi_lifetime)
proj_api.include_router(api_router)

def get_receiver_client() -> AnthemReceiverClient:
    return proj_api.state.Anthem_client

def get_receiver_config() -> AnthemReceiverClientConfig:
    return proj_api.state.Anthem_config

def get_raw_config() -> JsonableDict:
    return proj_api.state.raw_config

