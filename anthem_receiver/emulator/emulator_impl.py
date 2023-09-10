# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver emulator.

Provides a simple emulation of a Anthem receiver on TCP/IP.
"""

from __future__ import annotations

import asyncio
import sddp_discovery_protocol as sddp

from ..internal_types import *
from ..pkg_logging import logger
from ..protocol import (
    Packet,
    AnthemModel,
    models,
    AnthemCommand,
    AnthemResponse,
    bytes_to_command_meta,
    name_to_command_meta,
    CommandMeta,
  )
from ..constants import DEFAULT_PORT
from ..exceptions import AnthemReceiverError

from .session import AnthemReceiverEmulatorSession

EMULATOR_WARMUP_TIME = 10.0

class AnthemReceiverEmulator(AsyncContextManager['AnthemReceiverEmulator']):
    model: AnthemModel
    password: Optional[str]
    bind_addr: str
    port: int
    sessions: Dict[int, AnthemReceiverEmulatorSession]
    next_session_id: int = 0
    requests: asyncio.Queue[Optional[Tuple[AnthemReceiverEmulatorSession, Packet]]]
    server: Optional[asyncio.Server] = None
    handler_task: Optional[asyncio.Task[None]] = None
    server_task: Optional[asyncio.Task[None]] = None
    final_result: asyncio.Future[None]
    warmup_time: float
    cooldown_time: float

    power_status_payload: bytes
    input_status_payload: bytes
    gamma_table_status_payload: bytes
    gamma_value_status_payload: bytes
    source_status_payload: bytes

    power_status_query_meta = name_to_command_meta("power_status.query")
    input_status_query_meta = name_to_command_meta("input_status.query")
    gamma_table_status_query_meta = name_to_command_meta("gamma_table_status.query")
    gamma_value_status_query_meta = name_to_command_meta("gamma_value_status.query")
    source_status_query_meta = name_to_command_meta("source_status.query")

    warmup_timer: Optional[asyncio.Task[None]] = None
    cooldown_timer: Optional[asyncio.Task[None]] = None
    sddp_server_task: Optional[asyncio.Task[None]] = None
    with_sddp: bool
    sddp_multicast_address: str
    sddp_port: int
    sddp_bind_addresses: Optional[List[str]]
    sddp_headers: Dict[str, Union[str, int, float]]
    sddp_include_loopback: bool

    def __init__(
            self,
            model: Optional[Union[AnthemModel, str]] = None,
            password: Optional[str] = None,
            bind_addr: Optional[str] = None,
            port: int = DEFAULT_PORT,
            initial_power_status: str = "Standby",
            initial_input_status: str = "HDMI 1",
            initial_gamma_table: str = "Normal",
            initial_gamma_value: str = "2.2",
            initial_source_status: str = "Signal OK",
            warmup_time: float = EMULATOR_WARMUP_TIME,
            cooldown_time: Optional[float] = None,
            with_sddp: bool = True,
            sddp_multicast_address: str=sddp.SDDP_MULTICAST_ADDRESS,
            sddp_port: int = sddp.SDDP_PORT,
            sddp_bind_addresses: Optional[Iterable[str]]=['127.0.0.1'],
            sddp_include_loopback: bool = True,
            sddp_headers: Optional[Mapping[str, Union[str, int, float]]] = None,
          ):
        if model is None:
            model = 'DLA-NZ8'
        if isinstance(model, str):
            if not model in models:
                raise AnthemReceiverError(f"Unknown model {model}")
            model = models[model]
        self.model = model
        self.password = password
        self.bind_addr = '0.0.0.0' if bind_addr is None else bind_addr
        self.port = port
        self.sessions = {}
        self.requests = asyncio.Queue()
        self.final_result = asyncio.get_event_loop().create_future()
        self.warmup_time = warmup_time
        self.cooldown_time = cooldown_time if cooldown_time is not None else warmup_time
        self.with_sddp = with_sddp
        self.sddp_multicast_address = sddp_multicast_address
        self.with_sddp = with_sddp
        self.sddp_port = sddp_port
        self.sddp_bind_addresses = None if sddp_bind_addresses is None else list(sddp_bind_addresses)
        self.sddp_include_loopback = sddp_include_loopback
        sddp_model_name = self.model.sddp_name
        self.sddp_headers = {
            "Driver": f"receiver_nthemKENWOOD_{sddp_model_name}.c4i",
            "Host": "anthem_receiver-E0DADC152802",
            "Manufacturer": "AnthemKENWOOD",
            "Model": sddp_model_name,
            "Primary-Proxy": "receiver",
            "Proxies": "receiver",
            "Type": "AnthemKENWOOD:Receiver"
        }
        if self.port != DEFAULT_PORT:
            # A nonstandard header is required to advertise nonstandard ports
            self.sddp_headers["Port"] = self.port
        if sddp_headers is not None:
            self.sddp_headers.update(sddp_headers)
        self.set_power_status_str(initial_power_status)
        self.set_input_status_str(initial_input_status)
        self.set_gamma_table_status_str(initial_gamma_table)
        self.set_gamma_value_status_str(initial_gamma_value)
        self.set_source_status_str(initial_source_status)

    async def _run_sddp_server(self) -> None:
        try:
            async with sddp.SddpServer(
                    device_headers=self.sddp_headers,
                    multicast_address=self.sddp_multicast_address,
                    multicast_port=self.sddp_port,
                    bind_addresses=self.sddp_bind_addresses,
                    include_loopback=self.sddp_include_loopback,
                  ) as server:
                # This will wait forever unless another task stops the server
                await server.wait_for_done()
        except asyncio.CancelledError:
            logger.debug("SDDP server cancelled")
            raise
        except BaseException as e:
            logger.debug(f"SDDP server error: {e}")
            self.set_final_result(e)
            raise
        else:
            logger.debug(f"SDDP server stopped prematurely")
            self.set_final_result(AnthemReceiverError("SDDP server stopped prematurely"))

    def _start_one_shot_timer(
            self,
            delay: float,
            callback: Callable[[], Coroutine[Any, Any, None]]
          ) -> asyncio.Task[None]:
        async def timer() -> None:
            await asyncio.sleep(delay)
            await callback()
        return asyncio.create_task(timer())

    async def _on_warmup_done(self) -> None:
        self.warmup_timer = None
        if self.get_power_status_str() == "Warming":
            logger.info("Emulator warmup complete, powering on")
            self.set_power_status_str("On")

    async def _on_cooldown_done(self) -> None:
        self.cooldown_timer = None
        if self.get_power_status_str() == "Cooling":
            logger.info("Emulator cooldown complete, entering standby")
            self.set_power_status_str("Standby")

    def get_power_status_str(self) -> str:
        result = self.power_status_query_meta.response_map.response_payload_to_str(
            self.power_status_payload)
        assert result is not None
        return result

    def set_power_status_str(self, power_status: str) -> None:
        logger.debug(f"Setting receiver emulator power status to '{power_status}'")
        if self.warmup_timer is not None:
            self.warmup_timer.cancel()
            self.warmup_timer = None
        if self.cooldown_timer is not None:
            self.cooldown_timer.cancel()
            self.cooldown_timer = None
        power_status_payload = self.power_status_query_meta.response_map.str_to_response_payload(
            power_status)
        if power_status_payload is None:
            raise AnthemReceiverError(f"Unknown power status string '{power_status}'")
        self.power_status_payload = power_status_payload
        if not self.final_result.done():
            if power_status == "Warming":
                self.warmup_timer = self._start_one_shot_timer(self.warmup_time, self._on_warmup_done)
            elif power_status == "Cooling":
                self.cooldown_timer = self._start_one_shot_timer(self.cooldown_time, self._on_cooldown_done)

    def set_input_status_str(self, input_status: str) -> None:
        logger.debug(f"Setting receiver emulator input status to '{input_status}'")
        input_status_payload = self.input_status_query_meta.response_map.str_to_response_payload(
            input_status)
        if input_status_payload is None:
            raise AnthemReceiverError(f"Unknown input status string '{input_status}'")
        self.input_status_payload = input_status_payload

    def set_gamma_table_status_str(self, gamma_table: str) -> None:
        logger.debug(f"Setting receiver emulator gamma table to '{gamma_table}'")
        gamma_table_status_payload = self.gamma_table_status_query_meta.response_map.str_to_response_payload(
            gamma_table)
        if gamma_table_status_payload is None:
            raise AnthemReceiverError(f"Unknown gamma table string '{gamma_table}'")
        self.gamma_table_status_payload = gamma_table_status_payload

    def set_gamma_value_status_str(self, gamma_value: str) -> None:
        logger.debug(f"Setting receiver emulator gamma value to '{gamma_value}'")
        gamma_value_status_payload = self.gamma_value_status_query_meta.response_map.str_to_response_payload(
            gamma_value)
        if gamma_value_status_payload is None:
            raise AnthemReceiverError(f"Unknown gamma value string '{gamma_value}'")
        self.gamma_value_status_payload = gamma_value_status_payload

    def set_source_status_str(self, source_status: str) -> None:
        logger.debug(f"Setting receiver emulator source status to '{source_status}'")
        source_status_payload = self.source_status_query_meta.response_map.str_to_response_payload(
            source_status)
        if source_status_payload is None:
            raise AnthemReceiverError(f"Unknown source status string '{source_status}'")
        self.source_status_payload = source_status_payload

    def alloc_session_id(self, session: AnthemReceiverEmulatorSession) -> int:
        result = self.next_session_id
        self.next_session_id += 1
        self.sessions[result] = session
        return result

    def free_session_id(self, session_id: int) -> None:
        self.sessions.pop(session_id, None)

    def on_packet_received(self, session: AnthemReceiverEmulatorSession, packet: Packet) -> None:
        """Called when a packet is received from a session."""
        self.requests.put_nowait((session, packet))

    async def _handle_power_on(
            self,
            session: AnthemReceiverEmulatorSession,
            command: AnthemCommand
          ) -> Union[AnthemResponse, bytes, str, None, bool]:
        """Handle a power.on command, and return a response.

        Transitions from Standby to Warming state.

        NOTE: To emulate the behavior of some or all Anthem receivers, this
              does not return any response and has no effect if the receiver
              is not in Standby mode.
        """
        result: Union[AnthemResponse, bytes, str, None, bool]
        if self.get_power_status_str() == "Standby":
            self.set_power_status_str("Warming")
            result = True
        else:
            result = False
        return result

    async def _handle_power_off(
            self,
            session: AnthemReceiverEmulatorSession,
            command: AnthemCommand
          ) -> Union[AnthemResponse, bytes, str, None, bool]:
        """Handle a power.off command, and return a response.

        Transitions from On to Cooling state.

        NOTE: To emulate the behavior of some or all Anthem receivers, this
              does not return any response and has no effect if the receiver
              is not in On mode.
        """
        result: Union[AnthemResponse, bytes, str, None, bool]
        if self.get_power_status_str() == "On":
            self.set_power_status_str("Cooling")
            result = True
        else:
            result = False
        return result

    async def handle_command(
            self,
            session: AnthemReceiverEmulatorSession,
            command: AnthemCommand
          ) -> Union[AnthemResponse, bytes, str, None, bool]:
        """Handle a single command, and return a response.
        If a AnthemResponse is returned, it is used to form and send the response.
        If None, True, or a 0-byte bytes is returned, a basic response is sent.
        If False is returned, no response is sent.
        If a str is returned, it is used to look up an advanced response payload
           in the command's friendly string response table.
        """

        result: Union[AnthemResponse, bytes, str, None, bool] = None

        if command.name == 'model_status.query':
            logger.debug(f"{session}: Responding to model_status.query with {self.model}")
            result = self.model.model_status_payload
        if command.name == 'power_status.query':
            logger.debug(f"{session}: Responding to power_status.query with {self.get_power_status_str()}")
            result = self.power_status_payload
        elif command.name == 'power.on':
            result = await self._handle_power_on(session, command)
        elif command.name == 'power.off':
            result = await self._handle_power_off(session, command)
        else:
            if not command.is_advanced:
                # Just acknowledge any basic command
                result = None
            else:
                # for advanced commands, just return the lowest sorted response payload
                payload_set = command.response_map.valid_response_payloads()
                if payload_set is None or len(payload_set) == 0:
                    raise AnthemReceiverError(f"No valid response payloads for advanced command {command}")
                payloads = sorted(payload_set)
                result = payloads[0]
        return result

    async def handle_request_packet(
            self,
            session: AnthemReceiverEmulatorSession,
            packet: Packet
          ) -> Optional[List[Packet]]:
        """Handle a single request packet, and return response packets.

        If an exception is raised, the session is closed.
        """
        if not packet.is_valid:
            raise AnthemReceiverError(f"Invalid request packet: {packet}")
        if not packet.is_command:
            raise AnthemReceiverError(f"Invalid command packet type {packet.packet_type}: {packet}")

        command = AnthemCommand.create_from_command_packet(packet, model=self.model)
        logger.debug(f"{session}: Received command: {command}")
        gen_response = await self.handle_command(session, command)
        if isinstance(gen_response, bool) and not gen_response:
            logger.debug(f"{session}: Sending NO response to command {command}")
            packets: List[Packet] = []
        else:
            response: AnthemResponse
            if isinstance(gen_response, AnthemResponse):
                response = gen_response
            else:
                basic_response_packet = command.create_basic_response_packet()
                advanced_response_packet: Optional[Packet] = None
                if not gen_response is None and not isinstance(gen_response, bool):
                    response_payload = b''
                    if isinstance(gen_response, str):
                        opt_response_payload = command.response_map.str_to_response_payload(
                            gen_response)
                        if opt_response_payload is None:
                            raise AnthemReceiverError(f"Unknown advanced string response '{gen_response}' for command {command}")
                        response_payload = opt_response_payload
                    elif isinstance(gen_response, bytes):
                        response_payload = gen_response
                    else:
                        raise AnthemReceiverError(f"Invalid response type {type(gen_response)} for command {command}")
                    if command.is_advanced:
                        advanced_response_packet = command.create_advanced_response_packet(response_payload)
                    else:
                        if len(response_payload) > 0:
                            raise AnthemReceiverError(f"Payload provided for response to basic command {command}: {response_payload.hex(' ')}")
                response = AnthemResponse(command, basic_response_packet, advanced_response_packet)

            logger.debug(f"{session}: Sending response: {response}")
            packets = [response.basic_response_packet]
            if not response.advanced_response_packet is None:
                packets.append(response.advanced_response_packet)

        return packets

    async def handle_requests(self) -> None:
        """Handle requests from sessions."""
        while True:
            session_and_packet = await self.requests.get()
            try:
                if session_and_packet is None:
                    logger.debug("Emulator handler: Received EOF; exiting")
                    break
                session, packet = session_and_packet
                try:
                    logger.debug(f"{session}: Emulator handler: received packet: {packet}")
                    response_packets = await self.handle_request_packet(session, packet)
                    if not response_packets is None:
                        for response_packet in response_packets:
                            logger.debug(f"{session}: Emulator handler: Sending response packet: {response_packet}")
                            session.write(response_packet.raw_data)
                except asyncio.CancelledError as e:
                    logger.debug(f"{session}: Handler task cancelled; exiting")
                    break
                except Exception as e:
                    logger.exception(f"{session}: Handler task: Exception while handling request; killing session: {e}")
                    break
            finally:
                self.requests.task_done()

    async def finish_start(self) -> None:
        """Called after the socket is up and running.  Subclasses can override to do additional
           initialization."""
        pass

    async def run(self) -> None:
        """Runs the Emulator until it is closed."""
        async with self:
            await self.wait_closed()

    async def start(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            self.handler_task = asyncio.create_task(self.handle_requests())
            self.server = await loop.create_server(
                lambda: AnthemReceiverEmulatorSession(self),
                host=self.bind_addr,
                port=self.port)
            logger.debug(f"Emulator: Listening on {self.bind_addr}:{self.port}")
            await self.server.start_serving()
            if self.with_sddp:
                self.sddp_server_task = asyncio.create_task(self._run_sddp_server())
            await self.finish_start()
        except BaseException as e:
            self.set_final_result(e)
            try:
                await self.wait_closed()
            except BaseException as e:
                pass
            raise

    def close(self, exc: Optional[BaseException]=None) -> None:
        """Stops the Emulator."""
        self.set_final_result(exc)

    async def wait_closed(self) -> None:
        """Waits for the emulator to be fully closed. Does not initiate shutdown.
           Does not raise an exception based on final status."""
        try:
            await self.final_result
        finally:
            try:
                if self.server is not None:
                    try:
                        self.server.close()
                    finally:
                        await self.server.wait_closed()
            finally:
                self.server = None
                if self.sddp_server_task is not None:
                    try:
                        self.sddp_server_task.cancel()
                        try:
                            await self.sddp_server_task
                        except asyncio.CancelledError:
                            pass
                    finally:
                        self.sddp_server_task = None
                        if self.handler_task is not None:
                            try:
                                await self.handler_task
                            finally:
                                self.handler_task = None

    async def close_and_wait(self, exc: Optional[BaseException]=None) -> None:
        self.close(exc)
        await self.wait_closed()

    def set_final_result(self, exc: Optional[BaseException]=None) -> None:
        if not self.final_result.done():
            if exc is None:
                logger.debug(f"Emulator: Setting final result to success")
                self.final_result.set_result(None)
            else:
                logger.debug(f"Emulator: Setting final exception: {exc}")
                self.final_result.set_exception(exc)
            if self.sddp_server_task is not None:
                self.sddp_server_task.cancel()
            if self.warmup_timer is not None:
                self.warmup_timer.cancel()
                self.warmup_timer = None
            if self.warmup_timer is not None:
                self.cooldown_timer.cancel()
                self.cooldown_timer = None
            self.requests.put_nowait(None)
            if self.server is not None:
                self.server.close()

    async def __aenter__(self) -> AnthemReceiverEmulator:
        await self.start()
        return self

    async def __aexit__(self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType]
      ) -> None:
        self.set_final_result(exc)
        try:
            # ensure that final_result has been awaited
            await self.wait_closed()
        except Exception as e:
            pass

