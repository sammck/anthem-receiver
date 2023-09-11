# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Anthem receiver client configuration.

Provides general config object for a AnthemReceiverClientTransport over
supported transport protocols.
"""

from __future__ import annotations

import os
import json

from ..internal_types import *
from ..exceptions import AnthemReceiverError
from ..constants import (
    DEFAULT_TIMEOUT,
    DEFAULT_PORT,
    STABLE_POWER_TIMEOUT,
    IDLE_DISCONNECT_TIMEOUT,
    CONNECT_TIMEOUT,
    CONNECT_RETRY_INTERVAL,
  )
from ..pkg_logging import logger
from ..protocol import AnthemModel, models

class AnthemReceiverClientConfig:
    """Anthem receiver client configuration."""
    default_host: Optional[str]
    default_port: Optional[int]
    password: Optional[str]
    timeout_secs: float
    model: Optional[AnthemModel]
    stable_power_timeout_secs: float
    idle_disconnect_secs: float
    auto_reconnect: bool
    cache_dp: bool
    connect_timeout_secs: float
    connect_retry_interval_secs: float

    def __init__(
            self,
            default_host: Optional[str]=None,
            password: Optional[str]=None,
            *,
            default_port: Optional[int]=None,
            timeout_secs: Optional[float] = None,
            model: Optional[Union[AnthemModel, str]]=None,
            stable_power_timeout_secs: Optional[float] = None,
            idle_disconnect_secs: Optional[float] = None,
            auto_reconnect: Optional[bool] = None,
            cache_dp: Optional[bool] = None,
            connect_timeout_secs: Optional[float] = None,
            connect_retry_interval_secs: Optional[float] = None,
            base_config: Optional[AnthemReceiverClientConfig]=None,
            use_config_file: bool = True,
          ) -> None:
        """Creates a configuration for a Anthem receiver client.

           Args:
             default_host: The default hostname or IPV4 address of the receiver.
                   may optionally be prefixed with "tcp://".
                   May be suffixed with ":<port>" to specify a
                   non-default port, which will override the default_port argument.
                   May be "dp://" or "dp://<host>" to use
                   SSDP to discover the receiver.
                   If None, the default host will be taken from the
                     anthem_receiver_HOST environment variable.
             default_port: For TCP/IP transports, the default TCP/IP port number to use.
                    If None, the default port will be taken from the anthem_receiver_PORT.
                    If that environment variable is not found, the default Anthem
                    receiver port (20554) will be used.
             password:
                   The receiver password. If None, the password
                   will be taken from the anthem_receiver_PASSWORD
                   environment variable. If an empty string or the
                   environment variable is not found, no password
                   will be used.
             timeout_secs:
                   The timeout for all client operations, in seconds.
                   If None, the timeout will be taken from the
                   anthem_receiver_TIMEOUT environment variable.
                   If the environment variable is not found, the
                   default timeout will be used.
             idle_disconnect_secs:
                   For auto-connect transports, the timeout for
                   disconnecting from the receiver when idle, in seconds.
                   If None, IDLE_DISCONNECT_TIMOUT is used.
             model:
                   The receiver model. If None, the model will be
                   inferred if necessary from AnthemDp, model_status.query,
                   etc.
             stable_power_timeout_secs:
                   The timeout for the receiver to reach a stable power state
                   from WARMING or COOLING, in seconds. If None, a default
                   of 30 seconds is used.

             auto_reconnect:
                   For TCP transports, if True, the client transport will
                   automatically be wrapped in a transport that reconnects
                   on demand, and disconnects after an idle period. If None,
                   the base configuration is used. If no base configuration
                   is provided, the default is True.

             cache_dp:
                   For dp:// host names, cache the results of AnthemDp discovery
                   and use them for subsequent connections. If None, the base
                   configuration is used. If no base configuration is provided,
                   the default is True.

             connect_timeout_secs:
                    For TCP transports, the timeout for connecting to the
                    receiver, in seconds. If None, the base configuration
                    is used. If no base configuration is provided,
                    CONNECT_TIMEOUT is used.

             connect_retry_interval_secs:
                    For TCP transports, the interval between connection
                    attempts, in seconds. If None, the base configuration
                    is used. If no base configuration is provided,
                    CONNECT_RETRY_INTERVAL is used. Connection retry is
                    necessary because Anthem receivers only allow one
                    connection at a time, and the receiver may be
                    connected to another client.

             base_config:
                     An optional base configuration to use.
        """
        if base_config is None:
            self.init_from_defaults(use_config_file=use_config_file)
        else:
            self.init_from_base_config(base_config)

        if default_host is not None and default_host != '':
            self.default_host = default_host

        if default_port is not None and default_port > 0:
            self.default_port = default_port

        if password is not None:
            self.password = password

        if timeout_secs is not None:
            self.timeout_secs = timeout_secs

        if model is not None:
            if isinstance(model, str):
                if not model in models:
                    raise AnthemReceiverError(f"Unknown Anthem receiver model: {model}")
                self.model = models[model]
            else:
                assert isinstance(model, AnthemModel)
                self.model = model

        if stable_power_timeout_secs is not None:
            self.stable_power_timeout_secs = stable_power_timeout_secs

        if idle_disconnect_secs is not None:
            self.idle_disconnect_secs = idle_disconnect_secs

        if auto_reconnect is not None:
            self.auto_reconnect = auto_reconnect

        if cache_dp is not None:
            self.cache_dp = cache_dp

        if connect_timeout_secs is not None:
            self.connect_timeout_secs = connect_timeout_secs

        if connect_retry_interval_secs is not None:
            self.connect_retry_interval_secs = connect_retry_interval_secs

    def init_from_defaults(self, use_config_file: bool=True) -> None:
        """Initializes the configuration from defaults."""
        self.default_host = 'dp://'
        self.default_port = DEFAULT_PORT
        self.password = ''
        self.timeout_secs = DEFAULT_TIMEOUT
        self.model = None
        self.stable_power_timeout_secs = STABLE_POWER_TIMEOUT
        self.idle_disconnect_secs = IDLE_DISCONNECT_TIMEOUT
        self.auto_reconnect = True
        self.cache_dp = True
        self.connect_timeout_secs = CONNECT_TIMEOUT
        self.connect_retry_interval_secs = CONNECT_RETRY_INTERVAL

        if use_config_file:
            config_file = os.environ.get('anthem_receiver_CONFIG_FILE')
            if config_file is not None and config_file != '':
                with open(config_file, 'r') as f:
                    config_jsonable = json.load(f)
                self.update_from_jsonable(config_jsonable)

        default_host: Optional[str] = os.environ.get('anthem_receiver_HOST')
        if default_host is not None and default_host != '':
            self.default_host = default_host
        default_port_str = os.environ.get('anthem_receiver_PORT')
        default_port: Optional[int] = None
        if default_port_str is not None and default_port_str != '':
            self.default_port = str(default_port_str)
        password = os.environ.get('anthem_receiver_PASSWORD')
        if password is not None and password != '':
            self.password = password

    def init_from_base_config(self, base_config: AnthemReceiverClientConfig) -> None:
        """Initializes the configuration from a base configuration."""
        self.default_host = base_config.default_host
        self.default_port = base_config.default_port
        self.password = base_config.password
        self.timeout_secs = base_config.timeout_secs
        self.model = base_config.model
        self.stable_power_timeout_secs = base_config.stable_power_timeout_secs
        self.idle_disconnect_secs = base_config.idle_disconnect_secs
        self.auto_reconnect = base_config.auto_reconnect
        self.cache_dp = base_config.cache_dp
        self.connect_timeout_secs = base_config.connect_timeout_secs
        self.connect_retry_interval_secs = base_config.connect_retry_interval_secs

    def to_jsonable(self) -> JsonableDict:
        """Returns a JSON-serializable representation of the configuration."""
        result: JsonableDict = dict(
            default_host=self.default_host,
            default_port=self.default_port,
            password=self.password,
            timeout_secs=self.timeout_secs,
            stable_power_timeout_secs=self.stable_power_timeout_secs,
            idle_disconnect_secs=self.idle_disconnect_secs,
            auto_reconnect=self.auto_reconnect,
            cache_dp=self.cache_dp,
            connect_timeout_secs=self.connect_timeout_secs,
            connect_retry_interval_secs=self.connect_retry_interval_secs,
          )
        if self.model is not None:
            result['model'] = self.model.name
        return result

    def to_json(self) -> str:
        """Returns a JSON representation of the configuration."""
        return json.dumps(self.to_jsonable())

    def update_from_jsonable(self, jsonable: JsonableDict) -> None:
        """Creates a configuration from a JSON-serializable representation."""
        default_host=jsonable.get('default_host')
        if default_host is not None and default_host != '':
            self.default_host = default_host
        default_port=jsonable.get('default_port')
        if default_port is not None and default_port != '':
            self.default_port = int(default_port)
        password=jsonable.get('password')
        if password is not None and password != '':
            self.password = password
        timeout_secs=jsonable.get('timeout_secs')
        if timeout_secs is not None and timeout_secs != '':
            self.timeout_secs = int(timeout_secs)
        model=jsonable.get('model')
        if model is not None and model != '':
            self.model = models[model]
        stable_power_timeout_secs=jsonable.get('stable_power_timeout_secs')
        if stable_power_timeout_secs is not None and stable_power_timeout_secs != '':
            self.stable_power_timeout_secs = int(stable_power_timeout_secs)
        idle_disconnect_secs=jsonable.get('idle_disconnect_secs')
        if idle_disconnect_secs is not None and idle_disconnect_secs != '':
            self.idle_disconnect_secs = int(idle_disconnect_secs)
        auto_reconnect=jsonable.get('auto_reconnect')
        if auto_reconnect is not None and auto_reconnect != '':
            self.auto_reconnect = bool(auto_reconnect)
        cache_dp=jsonable.get('cache_dp')
        if cache_dp is not None and cache_dp != '':
            self.cache_dp = bool(cache_dp)
        connect_timeout_secs=jsonable.get('connect_timeout_secs')
        if connect_timeout_secs is not None and connect_timeout_secs != '':
            self.connect_timeout_secs = int(connect_timeout_secs)
        connect_retry_interval_secs=jsonable.get('connect_retry_interval_secs')
        if connect_retry_interval_secs is not None and connect_retry_interval_secs != '':
            self.connect_retry_interval_secs = int(connect_retry_interval_secs)

    @classmethod
    def from_jsonable(cls, jsonable: JsonableDict, use_config_file: bool=True) -> 'AnthemReceiverClientConfig':
        """Creates a configuration from a JSON-serializable representation."""
        result = cls(use_config_file=use_config_file)
        result.update_from_jsonable(jsonable)
        return result

    @classmethod
    def from_json(cls, json_str: str, use_config_file: bool=True) -> 'AnthemReceiverClientConfig':
        """Creates a configuration from a JSON representation."""
        jsonable = json.loads(json_str)
        return cls.from_jsonable(jsonable, use_config_file=use_config_file)

    @classmethod
    def from_config_file(cls, filename: str) -> 'AnthemReceiverClientConfig':
        """Creates a configuration from a JSON-serialized config file."""
        with open(filename, 'r') as f:
            jsonable: JsonableDict = json.load(f)

        result = cls.from_jsonable(jsonable, use_config_file=False)
        return result

    def __str__(self) -> str:
        return (
            f"AnthemReceiverConfig("
            f"default_host={self.default_host}, "
            f"default_port={self.default_port}, "
            f"timeout_secs={self.timeout_secs!r})"
          )

    def __repr__(self) -> str:
        return str(self)
