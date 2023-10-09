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
import dotenv
import aioconsole
import colorama # type: ignore[import]
from colorama import Fore, Back, Style
from signal import SIGINT, SIGTERM
import traceback

from anthem_receiver.internal_types import *
from anthem_receiver.pkg_logging import logger

from anthem_receiver import (
    __version__ as pkg_version,
  )

from anthem_receiver.client import TcpBarePacketStreamConnector, AnthemReceiverClientConfig, resolve_receiver_tcp_host
from anthem_receiver.protocol import PacketStreamTransport, PacketType, Packet

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
    _receiver_address: Optional[HostAndPort] = None
    _transport: Optional[PacketStreamTransport] = None
    _console_task: Optional[asyncio.Task] = None
    _receive_task: Optional[asyncio.Task] = None
    _colorize_stdout: bool = True
    _colorize_stderr: bool = True
    _client_config: Optional[AnthemReceiverClientConfig] = None

    def __init__(self, argv: Optional[Sequence[str]]=None):
        self._argv = argv

    def ocolor(self, codes: str) -> str:
        return codes if self._colorize_stdout else ""

    def ecolor(self, codes: str) -> str:
        return codes if self._colorize_stderr else ""

    async def get_client_config(self) -> AnthemReceiverClientConfig:
        if self._client_config is None:
            self._client_config = AnthemReceiverClientConfig(
                default_host=self._args.ip_address,
                default_port=self._args.port,
              )
        return self._client_config

    async def connect_receiver(self) -> PacketStreamTransport:
        connector = TcpBarePacketStreamConnector(
            config=await self.get_client_config(),
          )
        transport = await connector.connect()
        return transport

    async def get_receiver_address(self) -> HostAndPort:
        host, port, _ = await resolve_receiver_tcp_host(config=await self.get_client_config())
        return (host, port)

    async def handle_console_input(self) -> None:
        try:
            while True:
                raw_data = await aioconsole.ainput(">>> ")
                if raw_data == "":
                    continue
                if raw_data == "exit" or raw_data == "quit" or raw_data == "q":
                    break
                packet: Optional[Packet] = None
                try:
                    packet = Packet.anthem_packet(raw_data)
                except Exception as e:
                    if self._provide_traceback:
                        print(f"\r{self.ocolor(Fore.RED)}Invalid packet: {e}\n{traceback.format_exc()}{self.ocolor(Style.RESET_ALL)}")
                    else:
                        print(f"\r{self.ocolor(Fore.RED)}Invalid packet: {e}{self.ocolor(Style.RESET_ALL)}")
                if packet is not None:
                    print(f"\r{self.ocolor(Fore.GREEN)}{packet.raw_data.decode('utf-8') + ';':<20} ->{self.ocolor(Style.RESET_ALL)}")
                    await self._transport.write(packet)
                    await self._transport.flush()
                ### allow a response to be printed before the next prompt
                await asyncio.sleep(0.3)
        except EOFError:
            print()
            pass
        except Exception as e:
            logger.debug("Exception in console input handler", exc_info=e)
            raise
        finally:
            logger.debug("Console input handler exiting")
            self._receive_task.cancel()

    async def handle_received_data(self) -> None:
        try:
            async for packet in self._transport:
                packet_type = packet.packet_type
                if packet_type == PacketType.ANTHEM:
                    print(f"\r{' '*20}    <- {self.ocolor(Fore.BLUE)}{packet.raw_data.decode('utf-8')};{self.ocolor(Style.RESET_ALL)}")
                elif packet_type == PacketType.INVALID_ANTHEM:
                    print(f"\r{' '*20}    <- {self.ocolor(Fore.RED)}Invalid Anthem packet {packet.raw_data!r}{self.ocolor(Style.RESET_ALL)}")
                else:
                    print(f"\r{' '*20}    <- {self.ocolor(Fore.RED)}Unknown Anthem packet type: {packet}{self.ocolor(Style.RESET_ALL)}")
        except Exception as e:
            logger.debug("Exception in Receive data handler", exc_info=e)
            raise
        finally:
            logger.debug("Receive data handler exiting")
            self._console_task.cancel()

    async def cmd_bare(self) -> int:
        async with await self.connect_receiver() as transport:
            self._transport = transport
            self._console_task = asyncio.create_task(self.handle_console_input())
            try:
                self._receive_task = asyncio.create_task(self.handle_received_data())
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
            finally:
                logger.debug("Command exiting")
                self._console_task.cancel()

        return 0

    async def arun(self) -> int:
        """Run the dp command-line tool with provided arguments

        Args:
            argv (Optional[Sequence[str]], optional):
                A list of commandline arguments (NOT including the program as argv[0]!),
                or None to use sys.argv[1:]. Defaults to None.

        Returns:
            int: The exit code that would be returned if this were run as a standalone command.
        """
        import argparse

        parser = argparse.ArgumentParser(description="Access a secret key/value database.")


        self._parser = parser
        parser.add_argument('--traceback', "--tb", action='store_true', default=False,
                            help='Display detailed exception information')
        parser.add_argument('--log-level', dest='log_level', default='warning',
                            choices=['debug', 'info', 'warning', 'error', 'critical'],
                            help='''The logging level to use. Default: warning''')
        parser.set_defaults(func=self.cmd_bare)

        parser.add_argument('-d', '--device-name', default=None,
                            help='''The device name to match for discovery. Default: Fail if more than one device is found''')
        parser.add_argument('-p', '--port', default=None, type=int,
                            help='''The port number to connect to. Default: Use discovery response or 14999 if not using discovery''')
        parser.add_argument('ip_address', default=None, nargs='?',
                            help='''The local LAN IP address of the receiver. Default: Use discovery protocol to locate receiver.''')

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
            rc = await self.cmd_bare()
            logging.debug(f"Command returned {rc}")
        except Exception as ex:
            if isinstance(ex, CmdExitError):
                rc = ex.exit_code
            else:
                rc = 1
            if rc != 0:
                if traceback:
                    raise
            print(f"raw_console: error: {ex}", file=sys.stderr)
        except BaseException as ex:
            print(f"raw_console: Unhandled exception: {ex}", file=sys.stderr)
            raise

        return rc

    def run(self) -> int:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            try:
                rc = loop.run_until_complete(self.arun())
            finally:
                # make sure all cancelled tasks are cleaned up before closing the loop
                loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop)))
        finally:
            loop.close()
        return rc

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
    dotenv.load_dotenv()
    sys.exit(run())

