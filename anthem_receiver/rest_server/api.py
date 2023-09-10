#!/usr/bin/env python3

# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
A REST FastAPI server that controls a Anthem receiver.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

import time
import asyncio

from .logger import logger
from ..internal_types import *
from .. import (
    __version__ as pkg_version,
    AnthemReceiverClient,
    AnthemResponse,
    full_class_name,
    get_all_commands,
  )

router = APIRouter(prefix="/api/v1")

@router.get("/")
async def root(request: Request):
    client: AnthemReceiverClient = request.app.state.Anthem_client
    await client.cmd_null()
    return { "message": f"Hello World! Serving receiver at {client}" }

@router.get("/version")
async def version():
    """Returns the anthem-receiver package version"""
    return { "version": pkg_version }

@router.get("/config")
async def config_data(request: Request) -> Dict[str, Any]:
    """Returns the current configuration of anthem-receiver.

    The password is not included.
    """
    client: AnthemReceiverClient = request.app.state.Anthem_client
    config_data = client.config.to_jsonable()
    # don't reveal the configured password
    config_data.pop("password", None)
    return dict(config=config_data)

@router.get("/all-commands")
async def all_commands(request: Request) -> Dict[str, Any]:
    """Returns a dictionary of all commands supported by the execute() API."""
    results: Dict[str, Dict[str, Any]] = {}
    for cmd_name, cmd_meta in get_all_commands().items():
        result = dict(name=cmd_name)
        if cmd_meta.description is not None:
            result["description"] = cmd_meta.description
        if cmd_meta.payload_length is None or cmd_meta.payload_length != 0:
            result["payload_length"] = cmd_meta.payload_length
        if cmd_meta.response_payload_length is None or cmd_meta.response_payload_length != 0:
            result["response_payload_length"] = cmd_meta.response_payload_length
        results[cmd_name] = result

    return dict(commands=results)

async def execute_one_command(client: AnthemReceiverClient, cmd_name: str) -> JsonableDict:
    response: Optional[AnthemResponse] = None
    response_data: JsonableDict = dict(name=cmd_name)
    # pause commands are mainly for debugging timeouts
    if cmd_name == "pause1":
        await asyncio.sleep(1.0)
    elif cmd_name == "pause2":
        await asyncio.sleep(2.0)
    elif cmd_name == "pause5":
        await asyncio.sleep(5.0)
    elif cmd_name == "pause10":
        await asyncio.sleep(10.0)
    elif cmd_name == "on":
        response = await client.power_on_wait()
    elif cmd_name == "start_on":
        response = await client.power_on_wait(wait_for_final=False)
    elif cmd_name == "off":
        response = await client.power_off_wait()
    elif cmd_name == "start_off":
        response = await client.power_off_wait(wait_for_final=False)
    elif cmd_name == "power_status_wait":
        response = await client.power_status_wait()
    else:
        response = await client.transact_by_name(cmd_name)
    if not response is None:
        payload = response.payload
        if len(payload) > 0:
            response_data["payload_hex"] = response.payload.hex(' ')
            response_str = response.response_str()
            if not response_str is None:
                response_data["response_str"] = response_str
    return response_data

async def execute_one_command_with_errors(
        command_name: str,
        request: Request
      ) -> Dict[str, Any]:
    client: AnthemReceiverClient = request.app.state.Anthem_client
    logger.info(f"Executing command {command_name}")
    try:
        response_data = await execute_one_command(client, command_name)
    except Exception as exc:
        error_classname = full_class_name(exc)
        error_message = str(exc)
        if error_message == "":
            error_message = error_classname

        response_data = dict(
            name=command_name,
            error=error_classname,
            error_message=error_message,
            )
    return response_data

@router.get("/execute/{command_name}")
async def execute(
        command_name: str,
        request: Request
      ) -> Dict[str, Any]:
    """Executes a single receiver command by name and returns the result."""
    return await execute_one_command_with_errors(command_name, request)

@router.get("/multi-execute/{command_names}")
async def multi_execute(
        command_names: str,
        request: Request,
        continue_on_error: str=""
      ) -> Dict[str, Any]:
    """Executes one or commands by name (comma-delimited) and returns
       a list of results.

    If continue_on_error is True, then remaining commands are executed
    after a failure; Otherwise, execution stops at the
    the first error encountered. In any case, results from all commands attempted
    are returned.
    """
    client: AnthemReceiverClient = request.app.state.Anthem_client
    continue_on_error_flag = continue_on_error.lower() in ("true", "1", "yes", "y", "y", "on")
    cmd_names = command_names.split(',')
    logger.info(f"Executing commands {cmd_names} with continue_on_error={continue_on_error_flag}")
    response_datas: List[JsonableDict] = []
    for cmd_name in cmd_names:
        try:
            response_data = await execute_one_command(client, cmd_name)
        except Exception as exc:
            error_classname = full_class_name(exc)
            error_message = str(exc)
            if error_message == "":
                error_message = error_classname

            response_data = dict(
                name=cmd_name,
                error=error_classname,
                error_message=error_message,
              )
            response_datas.append(response_data)
            if not continue_on_error_flag:
                return { "responses": response_datas }
        else:
            response_datas.append(response_data)
    return { "responses": response_datas }

@router.get("/ping")
async def ping(
        request: Request
      ) -> Dict[str, Any]:
    """Returns the health status of the API server and the receiver."""
    client: AnthemReceiverClient = request.app.state.Anthem_client
    launch_time: float = request.app.state.launch_time
    up_time = time.monotonic() - launch_time
    result: Dict[str, Any] = dict(server_status="OK", up_time=up_time)
    try:
        await client.cmd_null()
    except Exception as exc:
        result["receiver_status"] = "ERROR"
        proj_error = full_class_name(exc)
        result["receiver_error"] = proj_error
        msg = str(exc)
        if msg == "":
            msg = proj_error
        result["receiver_error_message"] = msg
    else:
        result["receiver_status"] = "OK"
    return result

@router.get("/on")
async def power_on(
        request: Request
      ) -> Dict[str, Any]:
    """Turns the receiver on if necessary, and waits for the power on sequence to complete."""
    return await execute_one_command_with_errors("on", request)

@router.get("/off")
async def power_off(
        request: Request
      ) -> Dict[str, Any]:
    """Turns the receiver off if necessary, and waits for the power off sequence to complete."""
    return await execute_one_command_with_errors("off", request)

@router.get("/power_status")
async def power_status(
        request: Request
      ) -> Dict[str, Any]:
    """Returns the current power status of the receiver."""
    return await execute_one_command_with_errors("power_status.query", request)
