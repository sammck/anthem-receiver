anthem-receiver: Client library for control of Anthem A/V Receivers over TCP/IP
=================================================

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Latest release](https://img.shields.io/github/v/release/sammck/anthem-receiver.svg?style=flat-square&color=b44e88)](https://github.com/sammck/anthem-receiver/releases)

A tool and API for controlling Anthem A/V receivers via their proprietary TCP/IP protocol.

Table of contents
-----------------

* [Introduction](#introduction)
* [Installation](#installation)
* [Usage](#usage)
  * [Command line](#command-line)
  * [API](api)
* [Known issues and limitations](#known-issues-and-limitations)
* [Getting help](#getting-help)
* [Contributing](#contributing)
* [License](#license)
* [Authors and history](#authors-and-history)


Introduction
------------

Python package `anthem-receiver` provides a command-line tool as well as a runtime API for controlling many Anthem receiver models that include
an Ethernet port for TCP/IP control.

Some key features of anthem-receiver:

* JSON results
* Query receiver model
* Query power status
* Power on
* Power standby
* Wait for warmup/cooldown

Installation
------------

### Prerequisites

**Python**: Python 3.8+ is required. See your OS documentation for instructions.

### From PyPi

The current released version of `anthem-receiver` can be installed with 

```bash
pip3 install anthem-receiver
```

### From GitHub

[Poetry](https://python-poetry.org/docs/master/#installing-with-the-official-installer) is required; it can be installed with:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Clone the repository and install anthem-receiver into a private virtualenv with:

```bash
cd <parent-folder>
git clone https://github.com/sammck/anthem-receiver.git
cd anthem-receiver
poetry install
```

You can then launch a bash shell with the virtualenv activated using:

```bash
poetry shell
```


Usage
=====

Command Line
------------

There is a single command tool `anthem-receiver` that is installed with the package.


API
---

TBD

Known issues and limitations
----------------------------

* Import/export are not yet supported.

Getting help
------------

Please report any problems/issues [here](https://github.com/sammck/anthem-receiver/issues).

Contributing
------------

Pull requests welcome.

License
-------

anthem-receiver is distributed under the terms of the [MIT License](https://opensource.org/licenses/MIT).
The license applies to this file and other files in the [GitHub repository](http://github.com/sammck/anthem-receiver)
hosting this file.

References
----------

* [Hubitat community thread](https://community.openhab.org/t/binding-request-anthem-receiver/2519/21)
* [Anthem D-ILA Receiver RS-232C, LAN and Infrared Remote Control Guide](https://support.Anthem.com/consumer/support/documents/DILAremoteControlGuide.pdf)

Authors and history
---------------------------

The author of anthem-receiver is [Sam McKelvie](https://github.com/sammck).
