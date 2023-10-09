# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""Constants used by anthem_receiver"""

DEFAULT_PORT = 14999
"""The listen port number used by the receiver for TCP/IP control."""

DEFAULT_TIMEOUT = 2.0
"""The default timeout for all TCP/IP control operations, in seconds."""

IDLE_DISCONNECT_TIMEOUT = 2.0
"""For autoconnect transports, the timeout for the client to disconnect after an idle period,
   in seconds."""

CONNECT_TIMEOUT = 15.0
"""The timeout for connecting to the receiver over TCP/IP, in seconds."""

CONNECT_RETRY_INTERVAL = 1.0
"""The interval between connection attempts over TCP/IP, in seconds."""
