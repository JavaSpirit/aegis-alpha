def test_is_history_store_available_returns_bool():
    from aegis_alpha.history_store import is_history_store_available

    val = is_history_store_available()
    assert isinstance(val, bool)


def test_history_store_unavailable_error_message():
    from aegis_alpha.history_store import history_store_unavailable_error

    msg = history_store_unavailable_error()
    assert "history-store extras not installed" in msg
