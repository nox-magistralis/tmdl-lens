import platform

import pytest


@pytest.mark.skipif(platform.system() != "Linux", reason="probe for the linux job")
def test_gate_probe_red_on_linux():
    assert False
