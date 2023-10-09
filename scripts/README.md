Development utility scripts for anthem-receiver project
=================================================

Contains useful scripts and files used during development


serial_commands.csv
-------------------

File `serial_commands.csv` contains a sanitized CSV-formatted version of the "Serial Commands" sheet in
the spreadsheet published by Anthem as [Official Protocol Documentation](https://www.anthemav.com/downloads/MRX-x20-AVM-60-IP-RS-232.xls),
and is not subject to the terms of the MIT License for this project. All blank and extraneous comment lines have been removed
and simulated IR key command names have been expanded in column 1. The first row ";" has been replaced to reflect
an empty packet as representing a command ACK.

This file should not be edited unless a new version of Anthem documentation is released.

command_name_map.json
---------------------

A cached copy of current local metadata inferences derived from `serial_commands.csv`. This file
is created and updated by `import_serial_commands.py`. It can be edited to override inferred
metadata, and when `import_serial_commands.py` is run again, the edited inferences will be retained.

import_serial_commands.py
-------------------------

Reads `serial_commands.csv` and `command_name_map.json`, updates all inferred local metadata inferences,
saves results in `command_name_map.json`, then edits the python source file in `<project-dir>/anthem_receiver/protocol/command_meta.py`,
replacing all content between `{{ begin_auto_meta }}` and `{{ end_auto_meta }}` markers with auto-generated
python code.
