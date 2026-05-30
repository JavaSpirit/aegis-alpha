from __future__ import annotations

from aegis_alpha.mcp import dependencies


def test_mcp_dependencies_reuse_singletons(monkeypatch) -> None:
    dependencies.reset_singletons()
    adapter_calls = 0
    store_calls = 0

    class FakeAdapter:
        pass

    class FakeStore:
        pass

    def create_adapter() -> FakeAdapter:
        nonlocal adapter_calls
        adapter_calls += 1
        return FakeAdapter()

    def create_store() -> FakeStore:
        nonlocal store_calls
        store_calls += 1
        return FakeStore()

    monkeypatch.setattr(dependencies, "create_market_data_adapter", create_adapter)
    monkeypatch.setattr(dependencies, "AegisAlphaStore", create_store)

    assert dependencies.get_market_data_adapter() is dependencies.get_market_data_adapter()
    assert dependencies.get_store() is dependencies.get_store()
    assert adapter_calls == 1
    assert store_calls == 1
    dependencies.reset_singletons()
