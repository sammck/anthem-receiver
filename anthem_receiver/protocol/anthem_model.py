# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
AnthemModel class
"""
from __future__ import annotations

from ..internal_types import *

class AnthemModel:
    name: str
    """The name for this model. This is the name that will be used when
       displaying, logging, etc."""

    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"AnthemModel('{self.name}')"

_known_models: List[str] = [
    "AVM-60",
  ]
"""A list of receiver models that are known at the time this metadata was
   defined."""

anthem_models: Dict[str, AnthemModel] = {}
"""A dictionary of receiver models, keyed by model name."""

for _model_name in _known_models:
    _model = AnthemModel(_model_name)
    anthem_models[_model_name] = _model
