# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
General utility functions
"""
from __future__ import annotations

from .internal_types import *

def full_name_of_class(cls: Type[object]) -> str:
    """Return the full name of a class, including the module name."""
    module = cls.__module__
    if module == 'builtins':
        return cls.__qualname__
    return f"{module}.{cls.__qualname__}"

def full_class_name(o: object) -> str:
    """Return the full name of an object's class, including the module name."""
    return full_name_of_class(o.__class__)
