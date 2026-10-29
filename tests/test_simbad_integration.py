"""Run explicitly with: python -m pytest -m integration."""
import pytest

from objects import resolve_object


@pytest.mark.integration
def test_live_ngc_7023():
    result = resolve_object("NGC 7023")
    assert "7023" in result["name"]
    assert result["ra_deg"] == pytest.approx(315.4, abs=0.1)
    assert result["dec_deg"] == pytest.approx(68.16, abs=0.1)
