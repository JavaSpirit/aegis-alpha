import importlib

import pytest


def test_scoring_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("aegis_alpha.adapters.jvquant.scoring")
