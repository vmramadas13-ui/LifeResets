from liferesets.health import is_healthy


def test_is_healthy() -> None:
    assert is_healthy() is True
