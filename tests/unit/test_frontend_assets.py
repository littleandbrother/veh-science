from __future__ import annotations

from pathlib import Path



def test_frontend_assets_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "frontend" / "index.html").exists()
    assert (root / "frontend" / "app.js").exists()
    assert (root / "frontend" / "styles.css").exists()
