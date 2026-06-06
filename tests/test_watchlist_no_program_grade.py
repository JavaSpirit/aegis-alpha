from aegis_alpha.models import WatchlistEntry


def test_new_entry_has_no_program_seeded_grade():
    entry = WatchlistEntry(symbol="000001", added_at="2026-06-06T09:30:00+08:00")
    assert entry.agent_grade is None
    assert entry.agent_grade_history == []
