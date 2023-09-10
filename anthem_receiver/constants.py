# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""Constants used by anthem_receiver"""

DEFAULT_PORT = 20554
"""The listen port number used by the receiver for TCP/IP control."""

DEFAULT_TIMEOUT = 2.0
"""The default timeout for all TCP/IP control operations, in seconds."""

STABLE_POWER_TIMEOUT = 60.0
"""The timeout for the receiver to reach a stable power state from WARMING or COOLING, in seconds."""

IDLE_DISCONNECT_TIMEOUT = 2.0
"""For autoconnect transports, the timeout for the client to disconnect after an idle period,
   in seconds."""

CONNECT_TIMEOUT = 15.0
"""The timeout for connecting to the receiver over TCP/IP, in seconds."""

CONNECT_RETRY_INTERVAL = 1.0
"""The interval between connection attempts over TCP/IP, in seconds."""

# Initial connection handshake:
#   Receiver: "PJ_OK"
#   Client: "PJREQ", if there is no password, or f"PJREQ_{password}" if there is a password
#   Receiver: "PJACK" if the password is correct, or "PJNAK" if the password is incorrect
#   <Normal command/response session begins>

PJ_OK = b"PJ_OK"
"""Sent by the receiver immediately on connecting. Note there is no terminating newline"""

PJREQ = b"PJREQ"
"""Sent to the receiver after receiving PJ_OK, to request authentication.
   If a password is set, then f"_{password}" is appended to the byte string. Note
   that there is no terminating newline."""

PJACK = b"PJACK"
"""Sent by the receiver in response to a successful authentication. Note there is no terminating newline."""
