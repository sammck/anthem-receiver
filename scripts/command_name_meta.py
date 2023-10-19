#!/usr/bin/env python3

"""Simple script to import command/notification codes from a CSV file into python code for inclusion in command_meta.py"""

from __future__ import annotations

from anthem_receiver.internal_types import *

import os
import json

"""
A record in the CSV file looks like this:

    Command:
        * The original spreadsheet command "pattern". Upper-case letters represent command; lower-case letters represent data bytes.
        * Commands prefixes with Zx are zone-specific commands, where x is the zone number (1-numzones).
          Currently there are only two zones Z1 and Z2.
        * Commands prefixed with Tx are tuner-specific commands, where x is the tuner number (1-numtuners).
          Currently, there is only one tuner T1.
        * Commands prefixed with Rx are trigger-specific commands, where x is the trigger number (1-2).
          Currently, there are only two triggers R1 and R2.
        * Commands ending in ? are queries, and the receiver will response with a response packet that starts with
          the characters before the '?', and has additional patameters after. There may be variable parameters before
          the '?'; in that case, the value of the parameter is considered part of the "name" of the state object;
          e.g., "ILNyy?" returns a distinct zzzz state value for each input value of yy, of the form "ILNyyzzzz...".
        * As a special case, simulated IR commands are enumerated individually even though they are all variants of ZxSIMyyyy.
          This is done to allow separate descriptions for each IR code in the CSV file.
    Description:
        A human-readable description of the command.
    Related Query Command:
        More descriptive text about how to query the value set by the command, etc. if "Command" is not a query, the first
        word of this field may be an additional query command that will query the value set by the command.

    Report:
        "yes" if unsolicited change notifications associated with the value set by the command are asynchronously sent out by the receiver
        when ECH1 is enabled. An empty string otherwise. Such change notifications will appear in the protocol to be identical to
        the query response for the command.

A record in command_name_map.json is keyed by Command in CSV above and looks
    "<csv_command>": {
        "csv_command": "<csv_command>",
        "description": "<Description from CSV, possibly edited>",
        "related_query_description": "<Related Query Description from CSV, possibly edited>",
        "fields": [ <field_descriptor>... ],
        "is_settable": <true|false>,  # true if can be used as a non-query set command
        "report": <true|false>,  # true if unsolicited change notifications are sent out for this command
    }

and a field_descriptor is a dict that looks like one of:

    {
        # A 'Z' followed by a single digit
        "name": "zone",
        "field_type": "zone_prefix",
        "min_value": 1,
        "max_value": 2,
    }

    {
        # A 'T' followed by a single digit
        "name": "tuner",
        "field_type": "tuner_prefix",
        "min_value": 1,
        "max_value": 1,
    }

    {
        # An 'R' followed by a single digit
        "name": "trigger",
        "field_type": "trigger_prefix",
        "min_value": 1,
        "max_value": 1,
    }

    {
        # A command code (3-4 letters)
        "name": "command_code",
        "field_type": "command_code",
        "value": "<command_code>",
    }

    {
        # A query placeholder; the position where '?' would go for
        # a query. In an actual query, all subsequent fields are omitted.
        # in a response or set-command, this field is omitted.
        "field_type": "query",
        "description": "<query_description>",
    }

    {
        # An integer value
        "pattern_letter": "<pattern_letter>",
        "name": "<field_name>",
        "description": "<field_description>",
        "field_type": "int",
        "require_sign": <true|false>, # if True, a +/- is mandatory as first char
        "min_length": <min_length>,
        "max_length": <max_length>,
        "min_value": <min_value>,
        "max_value": <max_value>,
        "value_map": "<value_map_name>"
    }

    {
        # A string value
        "pattern_letter": "<pattern_letter>",
        "name": "<field_name>",
        "description": "<field_description>",
        "field_type": "str",
        "min_length": <min_length>,
        "max_length": <max_length>,
        "value_map": "<value_map_name>"
        "blank_pad: <true|false>", # if True, the string is padded with spaces to the min_length
        "null_pad": <true|false>, # if True, the string is padded with nulls to the min_length
        "rstrip": <true|false>, # if True, trailing spaces are removed
        "null_rstrip": <true|false>, # if True, trailing nulls are removed
    }

"""

class FieldDescriptor:
    field_type: str
    field_name: str
    user_type: str = ''

    def __init__(self) -> None:
        self.field_name = self.field_type

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> FieldDescriptor:
        try:
            field_type =  jsonable['field_type']
            assert isinstance(field_type, str)
            field_class: Type[FieldDescriptor]
            if field_type == ZonePrefixFieldDescriptor.field_type:
                field_class = ZonePrefixFieldDescriptor
            elif field_type == TunerPrefixFieldDescriptor.field_type:
                field_class = TunerPrefixFieldDescriptor
            elif field_type == TriggerPrefixFieldDescriptor.field_type:
                field_class = TriggerPrefixFieldDescriptor
            elif field_type == CommandCodeFieldDescriptor.field_type:
                field_class = CommandCodeFieldDescriptor
            elif field_type == QueryPlaceholderDescriptor.field_type:
                field_class = QueryPlaceholderDescriptor
            elif field_type == IntegerDescriptor.field_type:
                field_class = IntegerDescriptor
            elif field_type == FloatDescriptor.field_type:
                field_class = FloatDescriptor
            elif field_type == StringDescriptor.field_type:
                field_class = StringDescriptor
            else:
                raise RuntimeError(f"Unknown field type {field_type}")
            return field_class.from_jsonable(jsonable)
        except Exception as e:
            raise RuntimeError(f"Exception in FieldDescriptor.from_jsonable({jsonable!r})") from e


class ZonePrefixFieldDescriptor(FieldDescriptor):
    field_type: str = "zone_prefix"
    field_name: str = "zone"
    min_value: int
    max_value: int
    user_type: str = 'ZoneId'

    def __init__(self, min_value: int=1, max_value: int=2):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            min_value=self.min_value,
            max_value=self.max_value,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        return cls(
            min_value=jsonable['min_value'],
            max_value=jsonable['max_value'],
        )


class TunerPrefixFieldDescriptor(FieldDescriptor):
    field_type: str = "tuner_prefix"
    field_name: str = "tuner"
    min_value: int
    max_value: int
    user_type: str = 'TunerId'

    def __init__(self, min_value: int=1, max_value: int=1):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            min_value=self.min_value,
            max_value=self.max_value,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        return cls(
            min_value=jsonable['min_value'],
            max_value=jsonable['max_value'],
        )

class TriggerPrefixFieldDescriptor(FieldDescriptor):
    field_type: str = "trigger_prefix"
    field_name: str = "trigger"
    min_value: int
    max_value: int
    user_type: str = 'TriggerId'

    def __init__(self, min_value: int=1, max_value: int=1):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            min_value=self.min_value,
            max_value=self.max_value,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        return cls(
            min_value=jsonable['min_value'],
            max_value=jsonable['max_value'],
        )

class CommandCodeFieldDescriptor(FieldDescriptor):
    field_type: str = "command_code"
    field_name: str = "command_code"
    value: str
    user_type: str = 'str'

    def __init__(self, value: str):
        super().__init__()
        self.value = value

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            value=self.value,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        return cls(
            value=jsonable['value'],
        )

class QueryPlaceholderDescriptor(FieldDescriptor):
    field_type: str = "query_placeholder"
    field_name: str = "query_placeholder"
    description: str

    def __init__(self, description: str):
        self.description = description

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            description=self.description,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        return cls(
            description=jsonable['description'],
        )

class IntegerDescriptor(FieldDescriptor):
    field_type: str = "integer"
    pattern_letter: str
    description: str
    require_sign: bool
    min_length: int
    max_length: int
    min_value: int
    max_value: int
    value_map_name: str
    user_type: str = 'int'

    def __init__(
            self, field_name: str, pattern_letter: str, description: str, require_sign: bool=False,
            min_length: int=1, max_length: int=1, min_value: int=0, max_value: int=0, value_map_name: str='',
            user_type: str = 'int'):
        super().__init__()
        self.field_name = field_name
        self.pattern_letter = pattern_letter
        self.description = description
        self.require_sign = require_sign
        self.min_length = min_length
        self.max_length = max_length
        self.min_value = min_value
        self.max_value = max_value
        value_map_name = 'IntFieldConverter' if value_map_name == '' else value_map_name
        self.value_map_name = value_map_name
        self.user_type = user_type

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            pattern_letter=self.pattern_letter,
            description=self.description,
            require_sign=self.require_sign,
            min_length=self.min_length,
            max_length=self.max_length,
            min_value=self.min_value,
            max_value=self.max_value,
            value_map_name=self.value_map_name,
            user_type=self.user_type,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        field_name = jsonable.get('field_name', jsonable['pattern_letter'])
        return cls(
            field_name=field_name,
            pattern_letter=jsonable['pattern_letter'],
            description=jsonable['description'],
            require_sign=jsonable['require_sign'],
            min_length=jsonable['min_length'],
            max_length=jsonable['max_length'],
            min_value=jsonable['min_value'],
            max_value=jsonable['max_value'],
            value_map_name=jsonable['value_map_name'],
            user_type=jsonable.get('user_type', 'int'),
        )

class FloatDescriptor(FieldDescriptor):
    field_type: str = "float"
    pattern_letter: str
    description: str
    min_length: int
    max_length: int
    min_value: int
    max_value: int
    digs_after_decimal: int
    value_map_name: str
    user_type: str = 'float'

    def __init__(
            self, field_name: str, pattern_letter: str, description: str, require_sign: bool=False,
            min_length: int=1, max_length: int=1, min_value: int=0, max_value: int=0,
            digs_after_decimal: int=2, value_map_name: str='', user_type: str = 'float'):
        super().__init__()
        self.field_name = field_name
        self.pattern_letter = pattern_letter
        self.description = description
        self.require_sign = require_sign
        self.min_length = min_length
        self.max_length = max_length
        self.min_value = min_value
        self.max_value = max_value
        self.digs_after_decimal = digs_after_decimal
        value_map_name = 'FloatFieldConverter' if value_map_name == '' else value_map_name
        self.value_map_name = value_map_name
        self.user_type = user_type

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_type=self.field_type,
            field_name=self.field_name,
            pattern_letter=self.pattern_letter,
            description=self.description,
            require_sign=self.require_sign,
            min_length=self.min_length,
            max_length=self.max_length,
            min_value=self.min_value,
            max_value=self.max_value,
            digs_after_decimal=self.digs_after_decimal,
            value_map_name=self.value_map_name,
            user_type=self.user_type,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        field_name = jsonable.get('field_name', jsonable['pattern_letter'])
        return cls(
            field_name=field_name,
            pattern_letter=jsonable['pattern_letter'],
            description=jsonable['description'],
            require_sign=jsonable['require_sign'],
            min_length=jsonable['min_length'],
            max_length=jsonable['max_length'],
            min_value=jsonable['min_value'],
            max_value=jsonable['max_value'],
            digs_after_decimal=jsonable['digs_after_decimal'],
            value_map_name=jsonable['value_map_name'],
            user_type=jsonable.get('user_type', 'float'),
        )


class StringDescriptor(FieldDescriptor):
    field_type: str = "string"
    pattern_letter: str
    description: str
    min_length: int
    max_length: int
    value_map_name: str
    blank_pad: bool # if True, the string is padded with spaces to the min_length
    null_pad: bool # if True, the string is padded with nulls to the min_length
    rstrip: bool # if True, trailing spaces are removed
    null_rstrip: bool # if True, trailing nulls are removed
    user_type: str = 'str'

    def __init__(
            self, field_name: str, pattern_letter: str, description: str, min_length: int=1,
            max_length: int=1, value_map_name: str='', blank_pad: bool=False,
            null_pad: bool=False, rstrip: bool=False, null_rstrip: bool=False,
            user_type: str = 'str'):
        super().__init__()
        self.field_name = field_name
        self.pattern_letter = pattern_letter
        self.description = description
        self.min_length = min_length
        self.max_length = max_length
        value_map_name = 'StrFieldConverter' if value_map_name == '' else value_map_name
        self.value_map_name = value_map_name
        self.blank_pad = blank_pad
        self.null_pad = null_pad
        self.rstrip = rstrip
        self.null_rstrip = null_rstrip
        self.user_type = user_type

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            field_name=self.field_name,
            field_type=self.field_type,
            pattern_letter=self.pattern_letter,
            description=self.description,
            min_length=self.min_length,
            max_length=self.max_length,
            value_map_name=self.value_map_name,
            blank_pad=self.blank_pad,
            null_pad=self.null_pad,
            rstrip=self.rstrip,
            null_rstrip=self.null_rstrip,
            user_type=self.user_type,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        assert jsonable['field_type'] == cls.field_type
        field_name = jsonable.get('field_name', jsonable['pattern_letter'])
        return cls(
            field_name=field_name,
            pattern_letter=jsonable['pattern_letter'],
            description=jsonable['description'],
            min_length=jsonable['min_length'],
            max_length=jsonable['max_length'],
            value_map_name=jsonable['value_map_name'],
            blank_pad=jsonable['blank_pad'],
            null_pad=jsonable['null_pad'],
            rstrip=jsonable['rstrip'],
            null_rstrip=jsonable['null_rstrip'],
            user_type=jsonable.get('user_type', 'str'),
        )


class CommandDescriptor:
    command_name: str
    name: str
    description: str
    related_query_description: str
    fields: List[FieldDescriptor]
    is_settable: bool
    report: bool

    def __init__(self, command_name: str, name: str, description: str, related_query_description: str, fields: List[FieldDescriptor], is_settable: bool, report: bool):
        self.command_name = command_name
        self.name = name
        self.description = description
        self.related_query_description = related_query_description
        self.fields = fields
        self.is_settable = is_settable
        self.report = report

    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            command_name=self.command_name,
            name=self.name,
            description=self.description,
            related_query_description=self.related_query_description,
            fields=[field.to_jsonable() for field in self.fields],
            is_settable=self.is_settable,
            report=self.report,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        try:
            return cls(
                command_name=jsonable['command_name'],
                name=jsonable['name'],
                description=jsonable['description'],
                related_query_description=jsonable['related_query_description'],
                fields=[FieldDescriptor.from_jsonable(field_jsonable) for field_jsonable in jsonable['fields']],
                is_settable=jsonable['is_settable'],
                report=jsonable['report'],
            )
        except Exception as e:
            raise RuntimeError(f"Exception in CommandDescriptor.from_jsonable({jsonable!r})") from e

class IRSimValue:
    code: int
    name: str
    description: str
    min_zone: int
    max_zone: int

    def __init__(self, code: int, name: str, description: str, min_zone: int=1, max_zone: int=2):
        self.code = code
        self.name = name
        self.description = description
        self.min_zone = min_zone
        self.max_zone = max_zone


    def to_jsonable(self) -> Dict[str, int]:
        return dict(
            code=self.code,
            name=self.name,
            description=self.description,
            min_zone=self.min_zone,
            max_zone=self.max_zone,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> ZonePrefixFieldDescriptor:
        try:
            return cls(
                code=jsonable['code'],
                name=jsonable['name'],
                description=jsonable['description'],
                min_zone=jsonable['min_zone'],
                max_zone=jsonable['max_zone'],
            )
        except Exception as e:
            raise RuntimeError(f"Exception in IRSimValue.from_jsonable({jsonable!r})") from e

class CommandsMetadata:
    cmds_by_name: Dict[str, CommandDescriptor]
    ir_sim_values: Dict[int, IRSimValue]

    def __init__(self, cmds_by_name: Dict[str, CommandDescriptor], ir_sim_values: Dict[int, IRSimValue]):
        self.cmds_by_name = cmds_by_name
        self.ir_sim_values = ir_sim_values

    def to_jsonable(self) -> Dict[str, int]:
        cmd_data = dict((k, v.to_jsonable()) for k, v in self.cmds_by_name.items())
        ir_sim_data = dict((f"{k:04d}", v.to_jsonable()) for k, v in self.ir_sim_values.items())
        return dict(
            commands=cmd_data,
            ir_sim_values=ir_sim_data,
        )

    @classmethod
    def from_jsonable(cls, jsonable: Dict[str, int]) -> CommandsMetadata:
        cmds_jsonable = jsonable.get('commands') or {}
        ir_sim_jsonable = jsonable.get('ir_sim_values') or {}
        cmds_by_name = dict((k, CommandDescriptor.from_jsonable(v)) for k, v in cmds_jsonable.items())
        ir_sim_values = dict((int(k), IRSimValue.from_jsonable(v)) for k, v in ir_sim_jsonable.items())
        return cls(
            cmds_by_name=cmds_by_name,
            ir_sim_values=ir_sim_values,
        )

src_dir = os.path.dirname(os.path.abspath(__file__))
cmd_name_map_path = os.path.join(src_dir, "command_name_map.json")

def load_meta() -> CommandsMetadata:
    if os.path.exists(cmd_name_map_path):
        with open(cmd_name_map_path, "r") as cmd_name_map_file:
            cmds_jsonable: Dict[str, JsonableDict] = json.load(cmd_name_map_file)
            cmds_metadata = CommandsMetadata.from_jsonable(cmds_jsonable)
    else:
        cmds_metadata = CommandsMetadata({}, {})
    return cmds_metadata

def save_meta(cmds_metadata: CommandsMetadata):
    tmp_file = f"{cmd_name_map_path}.tmp"
    cmds_jsonable = cmds_metadata.to_jsonable()
    try:
        if os.path.exists(tmp_file):
            os.unlink(tmp_file)
        with open(tmp_file, "w") as cmd_name_map_file:
            json.dump(cmds_jsonable, cmd_name_map_file, indent=2)
        os.rename(tmp_file, cmd_name_map_path)
    finally:
        if os.path.exists(tmp_file):
            os.unlink(tmp_file)

