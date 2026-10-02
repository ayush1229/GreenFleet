from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_fixture_validation_ui():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("synthetic" in x.value.lower() for x in app.warning)
    assert any("valid" in x.value.lower() for x in app.success)
