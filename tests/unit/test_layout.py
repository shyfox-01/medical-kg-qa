from pathlib import Path


def test_package_and_archival_boundary():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/medkg/__init__.py").exists()
    assert not (root / "requirements.txt").exists()
    assert "data/raw/" in (root / ".gitignore").read_text()
