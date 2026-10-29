"""Offline tests for the existing SIMBAD resolver."""
import pytest
from astropy.table import Table

from objects import resolve_object


def test_resolve_ngc_7023(monkeypatch):
    def query(name):
        assert name == "NGC 7023"
        return Table({"main_id": ["NGC  7023"], "ra": [315.403], "dec": [68.163]})

    monkeypatch.setattr("objects.Simbad.query_object", query)
    result = resolve_object("NGC 7023")
    assert result["name"] == "NGC  7023"
    assert result["ra_deg"] == pytest.approx(315.403)
    assert result["dec_deg"] == pytest.approx(68.163)


def test_unknown_object(monkeypatch):
    monkeypatch.setattr("objects.Simbad.query_object", lambda name: None)
    with pytest.raises(ValueError, match="^Object not found: unknown-object$"):
        resolve_object("unknown-object")
