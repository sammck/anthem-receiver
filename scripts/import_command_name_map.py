#!/usr/bin/env python3

"""Simple script to import command/notification codes from a CSV file into python code for inclusion in command_meta.py"""

from __future__ import annotations

from command_name_meta import *
from anthem_receiver.internal_types import *

import os
import sys
import csv
import logging

def main() -> int:
    logging.basicConfig(level=logging.DEBUG)

    cmds_metadata = load_meta()

    cmds_by_name = cmds_metadata.cmds_by_name
    ir_sim_values = cmds_metadata.ir_sim_values

    csv_path = os.path.join(src_dir, "serial_commands.csv")
    line_no = 1 # first line is eaten by csv.DictReader
    n: int = 0
    with open(csv_path, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            line_no += 1
            try:
                is_settable = False
                cmd_name = row["Command"].strip()
                if cmd_name.startswith("Simulated IR") or cmd_name == 'yyyy':
                    continue
                cmd_description = row["Description"].strip()
                related_query_desc = row["Related Query Command"].strip()
                report_str = row["Report"].strip()
                if report_str == "yes":
                    report = True
                elif report_str == "":
                    report = False
                else:
                    raise RuntimeError(f"Line {line_no}: Invalid report value: {report_str}")
                if not cmd_name in cmds_by_name:
                    logging.debug(f"[Line {line_no}]: cmd={cmd_name!r} description={cmd_description!r} related_query={related_query_desc!r} report={report}")
                    if '?' in cmd_name and related_query_desc != "":
                        cmd_description = f"{cmd_description}. {related_query_desc}"
                        related_query_desc = ""
                    fields: List[FieldDescriptor] = []
                    cmd_name_with_query = cmd_name
                    for word in related_query_desc.split():
                        if word.endswith('?'):
                            prequery = word[:-1]
                            if not cmd_name.startswith(prequery):
                                raise RuntimeError(f"Line {line_no}: Invalid related query command: {word!r}--does not match {cmd_code!r}")
                            is_settable = True
                            cmd_name_with_query = cmd_name[:len(prequery)] + '?' + cmd_name[len(prequery):]
                    cmd_code = cmd_name_with_query
                    if cmd_code.startswith("Z") and cmd_code[1] in "12x":
                        min_value = 1 if cmd_code[1] in '1x' else 2
                        max_value = 1 if cmd_code[1] in '2x' else 1
                        fields.append(ZonePrefixFieldDescriptor(min_value=min_value, max_value=max_value))
                        cmd_code = cmd_code[2:]
                    elif cmd_code.startswith("T1"):
                        fields.append(TunerPrefixFieldDescriptor(min_value=1, max_value=1))
                        cmd_code = cmd_code[2:]
                    elif cmd_name.startswith("Rx"):
                        fields.append(TriggerPrefixFieldDescriptor(min_value=1, max_value=2))
                        cmd_code = cmd_code[2:]
                    assert 'A' <= cmd_code[0] <= 'Z'
                    cmd_tail = ''
                    for i in range(len(cmd_code)):
                        if not ('A' <= cmd_code[i] <= 'Z'):
                            cmd_tail = cmd_code[i:]
                            cmd_code = cmd_code[:i]
                            break
                    fields.append(CommandCodeFieldDescriptor(value=cmd_code))
                    if cmd_code == 'SIM':
                        cmd_name = f"ZxSIMyyyy"
                        if not cmd_name in cmds_by_name:
                            fields[0].max_value = 2
                            cmds_by_name[cmd_name] = CommandDescriptor(
                                command_name=cmd_name,
                                description="Simulated IR Command values for ZxSIMyyyy (use 0 to fill in blanks Ex: Key 1 = 0001)",
                                related_query_description='',
                                fields=fields,
                                is_settable=False,
                                report=False,
                            )
                            n += 1
                        if cmd_tail != 'yyyy':
                            code = int(cmd_tail)
                            if code in ir_sim_values:
                                ir_sim_values[code].max_zone = 2
                            else:
                                ir_name = cmd_description.lower().replace(' ', '_')
                                ir_sim_values[code] = IRSimValue(code=code, name=ir_name, description=cmd_description, max_zone=1)
                                n += 1
                    else:
                        assert not cmd_code in cmds_by_name
                        i = 0
                        while i < len(cmd_tail):
                            nc = 1
                            c = cmd_tail[i]
                            if c == '?':
                                fields.append(QueryPlaceholderDescriptor(description=related_query_desc))
                            else:
                                assert 'a' <= c <= 'z'
                                i_dot = -1
                                while i + nc < len(cmd_tail) and ((cmd_tail[i + nc] == c) or (cmd_tail[i + nc] == '.')):
                                    if cmd_tail[i + nc] == '.':
                                        assert i_dot < 0
                                        i_dot = i + nc
                                    nc += 1
                                if i_dot >= 0:
                                    fields.append(FloatDescriptor(pattern_letter=c, description='', min_length=nc, max_length=nc, digs_after_decimal=nc - i_dot - 1))
                                else:
                                    fields.append(IntegerDescriptor(pattern_letter=c, description='', min_length=nc, max_length=nc))
                            i += nc
                        cmds_by_name[cmd_name] = CommandDescriptor(
                            command_name=cmd_name,
                            name=cmd_name,
                            description=cmd_description,
                            related_query_description=related_query_desc,
                            fields=fields,
                            is_settable=is_settable,
                            report=report,
                        )

                        n += 1
            except Exception as e:
                raise RuntimeError(f"Exception at entry # {line_no} of command_name_map.json") from e

    save_meta(cmds_metadata)

    print(f"Successfully imported {n} named commands", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
