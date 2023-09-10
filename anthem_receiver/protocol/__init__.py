# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Low-level protocol definitions for Anthem receivers.

Refer to https://support.Anthem.com/consumer/support/documents/DILAremoteControlGuide.pdf
for the official protocol documentation.
"""

from .constants import (
    PacketType,
    PACKET_MAGIC,
    END_OF_PACKET,
    END_OF_PACKET_BYTES,
    MAX_PACKET_LENGTH,
    MIN_PACKET_LENGTH,
  )

from .packet import (
    Packet,
  )

from .response import (
    AnthemResponse,
  )

from .command import (
    AnthemCommand,
  )

from .handshake import (
    PJ_OK,
    PJREQ,
    PJACK,
    PJNAK,
)

from .command_meta import (
    CommandMeta,
    AnthemModel,
    models,
    get_all_commands,
    name_to_command_meta,
    bytes_to_command_meta,
    model_status_list_map,
  )
