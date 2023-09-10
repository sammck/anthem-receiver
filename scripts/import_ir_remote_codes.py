#!/usr/bin/env python3

"""Simple script to import IR remote codes from a CSV file into python code for inclusion in command_codes.py"""

from typing import Dict, Tuple, List, Set

import os
import sys
import csv
import json
import re
import logging

ir_remote_code_fixed_prefix = b'\x21\x89\x01\x52\x43\x37\x33'
ir_remote_code_fixed_suffix = b'\x0a'

def fmt_bytes(b: bytes) -> str:
    """Formats a bytes object as a python literal with only hex escapes, e.g., b'\x01\x02\x03' -> "b'\\x01\\x02\\x03'"""
    return "b'" + "".join('\\x' + f"{x:02x}" for x in b) + "'"

def main() -> int:
    # logging.basicConfig(level=logging.DEBUG)

    cmd_name_map: Dict[bytes, Tuple[int, List[str]]] = {}   # Maps command prefix to tuple(next unused name index, list of names)
    cmds_by_name: Dict[str, Tuple[bytes, str]] = {}  # Maps command name to tuple(command prefix, description)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    cmd_name_map_path = os.path.join(src_dir, "command_name_map.json")
    if os.path.exists(cmd_name_map_path):
        with open(cmd_name_map_path, "r") as cmd_name_map_file:
            cmd_name_json: Dict[str, List[Dict[str, str]]] = json.load(cmd_name_map_file)
            for cmd_prefix_hex, cmd_desc_list in cmd_name_json.items():
                cmd_name_list = [cmd_desc['name'] for cmd_desc in cmd_desc_list]
                cmd_name_map[bytes.fromhex(cmd_prefix_hex)] = (0, cmd_name_list)

    csv_path = os.path.join(src_dir, "ir_remote_codes.csv")
    line_no = 1 # first line is eaten by csv.DictReader
    with open(csv_path, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            line_no += 1
            description = row["Command"].replace('\n', ' ').strip()
            hex_text = row['Hex Code'].strip()
            logging.debug(f"[Line {line_no}]: [{hex_text}]: '{description}'")
            try:
                hex_bytes = bytes.fromhex(hex_text)
            except ValueError as ex:
                raise RuntimeError(f"Line {line_no}: Invalid hex code: {hex_text}") from ex
            if len(hex_bytes) != 10:
                raise RuntimeError(f"Line {line_no}: IR remote code is not 10 bytes long (got {len(hex_bytes)}): {fmt_bytes(hex_bytes)}")
            if not hex_bytes.startswith(ir_remote_code_fixed_prefix):
                raise RuntimeError(f"Line {line_no}: IR remote code does not start with {fmt_bytes(ir_remote_code_fixed_prefix)}: {fmt_bytes(hex_bytes)}")
            if not hex_bytes.endswith(ir_remote_code_fixed_suffix):
                raise RuntimeError(f"Line {line_no}: IR remote code does not end with {fmt_bytes(ir_remote_code_fixed_suffix)}: {fmt_bytes(hex_bytes)}")
            cmd_prefix = hex_bytes[7:9]
            i_next_name, cmd_name_list2 = cmd_name_map.get(cmd_prefix, (0, None))
            if cmd_name_list2 is None:
                cmd_name_list2 = []
                cmd_name_map[cmd_prefix] = (0, cmd_name_list2)
            if i_next_name >= len(cmd_name_list2):
                cmd_name = description
                if '(' in cmd_name:
                    cmd_name = cmd_name[:cmd_name.index('(')]
                cmd_name = cmd_name.strip()
                cmd_name = cmd_name.replace("–", "-")  # m-dash
                if cmd_name.endswith("-"):
                    cmd_name = cmd_name[:-1] + " down"
                cmd_name = cmd_name.replace(
                    " ", "_").replace(
                    "▼", "_").replace(
                    "◄", "_").replace(
                    "►", "_").replace(
                    "▲", "_").replace(
                    "+", "up").replace(
                    "-", "_").replace(
                    "/", "_").replace(
                    ":", "_").replace(
                    ",", "_").replace(
                    "'", "").replace(
                    "!", "").replace(
                    "?", "").replace(
                    ".", "_").replace(
                    "&", "_").lower()
                while '__' in cmd_name:
                    cmd_name = cmd_name.replace('__', '_')
                while cmd_name.endswith("_"):
                    cmd_name = cmd_name[:-1]
                bare_cmd_name = cmd_name
                k = 1
                while cmd_name in cmds_by_name:
                    cmd_name = f"{bare_cmd_name}_v{k}"
                    k += 1
                cmd_name_list2.append(cmd_name)
            else:
                cmd_name = cmd_name_list2[i_next_name]
            cmd_name_map[cmd_prefix] = (i_next_name + 1, cmd_name_list2)
            cmds_by_name[cmd_name] = (cmd_prefix, description)

    cmd_name_json = {}
    for cmd_prefix, (i_next_name, cmd_name_list) in cmd_name_map.items():
        i_next_name = min(i_next_name, len(cmd_name_list))
        if i_next_name > 0:
            cmd_descs: List[Dict[str, str]] = []
            for cmd_name in cmd_name_list[:i_next_name]:
                cmd_descs.append(dict(name=cmd_name, description=cmds_by_name[cmd_name][1]))
            cmd_name_json[cmd_prefix.hex()] = cmd_descs
    with open(cmd_name_map_path, "w") as cmd_name_map_file:
        json.dump(cmd_name_json, cmd_name_map_file, indent=2)

    # _C("colour_space_next",         b'\x43\x44', "Colour Space - Cycles through Standard/Wide 1/Wide 2 (X3/X30/RS40/RS45)"),

    have_blank_line = True
    n = 0
    for cmd_prefix, (i_next_name, cmd_name_list) in cmd_name_map.items():
        i_next_name = min(i_next_name, len(cmd_name_list))
        if i_next_name > 0:
            for i, cmd_name in enumerate(cmd_name_list[:i_next_name]):
                if i == 0 and i_next_name > 1:
                    if not have_blank_line:
                        print()
                    print("        # overload")
                description = cmds_by_name[cmd_name][1]
                print(f"        _C({json.dumps(cmd_name)}, {fmt_bytes(cmd_prefix)}, {json.dumps(description)}),")
                n += 1
                have_blank_line = False
                if i == i_next_name - 1 and i_next_name > 1:
                     print()
                     have_blank_line = True

    sys.stdout.flush()
    print(f"Successfully imported {n} named commands", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
