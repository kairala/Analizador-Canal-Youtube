# tests/test_desktop.py
from desktop import _free_port


def test_free_port_returns_a_usable_port_number():
    port = _free_port()

    assert isinstance(port, int)
    assert 1024 <= port <= 65535
