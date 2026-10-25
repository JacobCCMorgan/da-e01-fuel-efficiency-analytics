from decimal import Decimal
from pathlib import Path
import json
import shutil
from urllib.error import HTTPError

import pytest

from fleet_fuel.sources import acquire, parse_history, _download


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_public_snapshot_matches_both_formats():
    manifest = acquire(ROOT)
    assert manifest["status"] == "public_download_verified"
    assert manifest["rows"] == 62
    assert manifest["main_period_rows"] == 52
    assert manifest["missing_values"] == 0
    assert manifest["xls_crosscheck"]["html_rows_compared_to_xls"] == 62
    assert manifest["xls_crosscheck"]["mismatches"] == 0


def test_previously_reviewed_price_points_are_preserved():
    # Independently recorded source checks from the earlier requirements stage.
    cases = {
        "eia_california.html": ("EMD_EPD2D_PTE_SCA_DPG", {
            "2025-01-06": "4.618", "2025-03-31": "4.776", "2025-06-30": "4.866"}),
        "eia_west_coast_ex_ca.html": ("EMD_EPD2D_PTE_R5XCA_DPG", {
            "2025-01-06": "3.739", "2025-03-31": "3.811", "2025-06-30": "4.035"}),
    }
    for filename, (series, expected) in cases.items():
        rows = parse_history((ROOT / "data/public/raw" / filename).read_bytes(), series)
        actual = {r["price_observation_date"]: r["market_week_price"] for r in rows}
        assert all(Decimal(actual[day]) == Decimal(value) for day, value in expected.items())


def test_incomplete_history_is_rejected():
    with pytest.raises(ValueError, match="Missing/excess"):
        parse_history(b"<table><tr><td>2025-Jan</td><td>01/06</td><td>4.618</td></tr></table>",
                      "EMD_EPD2D_PTE_SCA_DPG")


def test_cached_current_export_cannot_be_silently_changed(tmp_path):
    shutil.copytree(ROOT / "data/public", tmp_path / "data/public")
    with (tmp_path / "data/public/fuel_prices.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="Changed current"):
        acquire(tmp_path)


def test_transient_download_retry_is_bounded_and_recorded(tmp_path, monkeypatch):
    attempts = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit):
            return b"verified source bytes"

    def fake_open(request, timeout):
        attempts.append(request.full_url)
        if len(attempts) < 3:
            raise HTTPError(request.full_url, 503, "temporary", None, None)
        return Response()

    monkeypatch.setattr("fleet_fuel.sources.urlopen", fake_open)
    monkeypatch.setattr("fleet_fuel.sources.time.sleep", lambda seconds: None)
    destination = tmp_path / "price-source.dat"
    receipt = _download("https://example.invalid/eia-test-fixture", destination)
    assert len(attempts) == 3
    assert destination.read_bytes() == b"verified source bytes"
    assert [row["status"] for row in receipt["prior_failed_attempts"]] == [503, 503]
    assert json.loads((tmp_path / "price-source.dat.receipt.json").read_text())["status"] == 200
