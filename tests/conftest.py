import pytest


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    """Send run logs to a temp folder so pytest never writes into runs/."""
    folder = tmp_path / "runs"
    monkeypatch.setenv("RUNS_DIR", str(folder))
    return folder
