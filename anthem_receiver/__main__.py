#!/usr/bin/env python3

# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

from __future__ import annotations

import os
import sys
import argparse
import json
import base64
import asyncio
import logging
from signal import SIGINT, SIGTERM

from anthem_receiver.internal_types import *
from anthem_receiver import (
    __version__ as pkg_version,
    DEFAULT_PORT,
    AnthemReceiverClient,
    AnthemCommand,
    AnthemResponse,
    AnthemModel,
    models,
    anthem_receiver_connect,
    AnthemReceiverClientConfig,
    full_class_name,
  )

from dp_discovery_protocol import (
    AnthemDpClient,
    AnthemDpSearchRequest,
    AnthemDpResponseInfo,
  )

class CmdExitError(RuntimeError):
    exit_code: int

    def __init__(self, exit_code: int, msg: Optional[str]=None):
        if msg is None:
            msg = f"Command exited with return code {exit_code}"
        super().__init__(msg)
        self.exit_code = exit_code

class ArgparseExitError(CmdExitError):
    pass

class NoExitArgumentParser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        raise ArgparseExitError(status, message)

class CommandHandler:
    _argv: Optional[Sequence[str]]
    _parser: argparse.ArgumentParser
    _args: argparse.Namespace
    _provide_traceback: bool = True
    _model: Optional[AnthemModel] = None

    def __init__(self, argv: Optional[Sequence[str]]=None):
        self._argv = argv

    async def cmd_bare(self) -> int:
        print("A command is required", file=sys.stderr)
        return 1

    async def discover_receiver(self, bind_addresses: Optional[List[str]]=None) -> Optional[AnthemDpResponseInfo]:
        if not bind_addresses is None and len(bind_addresses) == 0:
            bind_addresses = None
        filter_headers: Dict[str, Union[str, int]] ={
            "Manufacturer": "AnthemKENWOOD",
            "Primary-Proxy": "receiver",
          }

        async with AnthemDpClient(bind_addresses=bind_addresses, include_loopback=True) as client:
            async with AnthemDpSearchRequest(
                    client,
                    filter_headers=filter_headers,
              ) as search_request:
                async for info in search_request.iter_responses():
                    return info
        return None

    async def cmd_find_ip(self) -> int:
        proj_info = await self.discover_receiver(self._args.bind_addresses)
        if proj_info is None:
            raise CmdExitError(1, "No receiver found")
        proj_ip = proj_info.src_addr[0]
        print(proj_ip)
        return 0

    async def cmd_emulator(self) -> int:
        bind_addr: str = self._args.bind
        port: int = self._args.port
        password: Optional[str] = self._args.password
        from anthem_receiver.emulator import AnthemReceiverEmulator
        emulator = AnthemReceiverEmulator(
            password=password,
            bind_addr=bind_addr,
            port=port,
            model=self._model,
          )
        def sigint_cleanup() -> None:
            emulator.close(CmdExitError(1, "Emulator terminated with SIGINT or SIGTERM"))
        loop = asyncio.get_running_loop()
        for signal in (SIGINT, SIGTERM):
            loop.add_signal_handler(signal, sigint_cleanup)
        try:
            await emulator.run()
        finally:
            for signal in (SIGINT, SIGTERM):
                loop.remove_signal_handler(signal)
        return 0

    async def cmd_exec(self) -> int:
        continue_on_error: bool = self._args.continue_on_error
        config = AnthemReceiverClientConfig(
            default_host=self._args.host,
            password=self._args.password,
            default_port=self._args.port,
          )

        cmd_names = self._args.exec_command
        if len(cmd_names) == 0:
            raise CmdExitError(1, "No receiver commands specified")
        response_datas: List[JsonableDict] = []
        try:
            async with await anthem_receiver_connect(config=config) as client:
                for cmd_name in cmd_names:
                    response: Optional[AnthemResponse] = None
                    response_data: JsonableDict = dict(name=cmd_name)
                    try:
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
                        else:
                            response = await client.transact_by_name(cmd_name)
                        if not response is None:
                            payload = response.payload
                            if len(payload) > 0:
                                response_data["payload_hex"] = response.payload.hex(' ')
                                response_str = response.response_str()
                                if not response_str is None:
                                    response_data["response_str"] = response_str
                    except Exception as exc:
                        error_classname = full_class_name(exc)
                        error_message = str(exc)
                        if error_message == "":
                            error_message = error_classname

                        response_data.update(
                            error=error_classname,
                            error_message=error_message,
                          )
                        response_datas.append(response_data)
                        if not continue_on_error:
                            raise
                    else:
                        response_datas.append(response_data)
        except Exception as exc:
            raise
        finally:
            print(json.dumps(response_datas, indent=2))
        return 0

    async def cmd_version(self) -> int:
        print(pkg_version)
        return 0

    async def arun(self) -> int:
        """Run the anthem-receiver command-line tool with provided arguments

        Args:
            argv (Optional[Sequence[str]], optional):
                A list of commandline arguments (NOT including the program as argv[0]!),
                or None to use sys.argv[1:]. Defaults to None.

        Returns:
            int: The exit code that would be returned if this were run as a standalone command.
        """
        import argparse

        parser = argparse.ArgumentParser(description="Control a Anthem receiver.")


        # ======================= Main command

        self._parser = parser
        parser.add_argument('--traceback', "--tb", action='store_true', default=False,
                            help='Display detailed exception information')
        parser.add_argument('--log-level', dest='log_level', default='warning',
                            choices=['debug', 'info', 'warning', 'error', 'critical'],
                            help='''The logging level to use. Default: warning''')
        parser.add_argument('--model', default=None,
                            choices=sorted(models.keys()),
                            help='''The logging level to use. Default: warning''')
        parser.set_defaults(func=self.cmd_bare)

        subparsers = parser.add_subparsers(
                            title='Commands',
                            description='Valid commands',
                            help='Additional help available with "<command-name> -h"')

        # ======================= find-ip

        parser_search = subparsers.add_parser('find-ip', description="Use the AnthemDp protocol to find the IP address of a Anthem receiver on the local subnet")
        parser_search.add_argument('-b', '--bind', dest="bind_addresses", action='append', default=[],
                            help='''The local unicast IP address to bind to on the desired subnet. May be repeated. Default: all local non-loopback unicast addresses.''')
        parser_search.set_defaults(func=self.cmd_find_ip)

        # ======================= emulator

        parser_emulator = subparsers.add_parser('emulator', description="Run a receiver emulator for testing purposes.")
        parser_emulator.add_argument("--port", default=DEFAULT_PORT, type=int,
            help=f"Anthem receiver port number to connect to. Default: {DEFAULT_PORT}")
        parser_emulator.add_argument("-p", "--password", default=None,
            help="Password to use for authentication. Default: None (no password required).")
        parser_emulator.add_argument('-b', '--bind', default="0.0.0.0",
                            help='''The local unicast IP address to bind to. Default: 0.0.0.0.''')

        parser_emulator.set_defaults(func=self.cmd_emulator)

        # ======================= exec

        parser_exec = subparsers.add_parser('exec', description="Execute one or more commands in the receiver.")
        parser_exec.add_argument('--host', default=None,
                            help='''The receiver host address. Default: use env var anthem_receiver_HOST.''')
        parser_exec.add_argument("--port", default=DEFAULT_PORT, type=int,
            help=f"Default receiver port number to connect to. Default: {DEFAULT_PORT}")
        parser_exec.add_argument("-p", "--password", default=None,
            help="Password to use for authentication. Default: None (no password required).")
        parser_exec.add_argument('--continue', dest="continue_on_error", action='store_true', default=False,
                            help='Continue running commands on error. Default: False')
        parser_exec.add_argument('exec_command', nargs=argparse.REMAINDER,
                            help='''One or more named commands to execute; e.g., "power.on".''')

        parser_exec.set_defaults(func=self.cmd_exec)

        # ======================= version

        parser_version = subparsers.add_parser('version',
                                description='''Display version information.''')
        parser_version.set_defaults(func=self.cmd_version)

        # =========================================================

        try:
            args = parser.parse_args(self._argv)
        except ArgparseExitError as ex:
            return ex.exit_code
        traceback: bool = args.traceback
        self._provide_traceback = traceback

        try:
            logging.basicConfig(
                level=logging.getLevelName(args.log_level.upper()),
            )
            self._args = args
            if args.model is not None:
                self._model = models[args.model]
            func: Callable[[], Awaitable[int]] = args.func
            logging.debug(f"Running command {func.__name__}, tb = {traceback}")
            rc = await func()
            logging.debug(f"Command {func.__name__} returned {rc}")
        except Exception as ex:
            if isinstance(ex, CmdExitError):
                rc = ex.exit_code
            else:
                rc = 1
            if rc != 0:
                if traceback:
                    raise
            ex_desc = str(ex)
            if len(ex_desc) == 0:
                ex_desc = ex.__class__.__name__
            print(f"anthem-receiver: error: {ex_desc}", file=sys.stderr)
        except BaseException as ex:
            print(f"anthem-receiver: Unhandled exception {ex.__class__.__name__}: {ex}", file=sys.stderr)
            raise

        return rc

    def run(self) -> int:
        return asyncio.run(self.arun())

def run(argv: Optional[Sequence[str]]=None) -> int:
    try:
        rc = CommandHandler(argv).run()
    except CmdExitError as ex:
        rc = ex.exit_code
    return rc

async def arun(argv: Optional[Sequence[str]]=None) -> int:
    try:
        rc = await CommandHandler(argv).arun()
    except CmdExitError as ex:
        rc = ex.exit_code
    return rc

# allow running with "python3 -m", or as a standalone script
if __name__ == "__main__":
    sys.exit(run())
