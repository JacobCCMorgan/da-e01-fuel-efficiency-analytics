import json
from pathlib import Path

import duckdb

from fleet_fuel.public_normalization import append_public_prices


ROOT = Path(__file__).resolve().parents[1]


def _database():
    con = duckdb.connect(":memory:")
    contract = json.loads((ROOT / "contracts/da_e01_contract.json").read_text())
    con.execute("CREATE SCHEMA normalized")
    for table in ("core_tenant", "fuel_market_price", "provenance_record"):
        fields = [f for f in contract["fields"] if f["table"] == table]
        columns = ",".join(f'"{f["name"]}" {f["type"]}' for f in fields)
        con.execute(f'CREATE TABLE normalized."{table}" ({columns})')
    con.execute("INSERT INTO normalized.core_tenant VALUES ('T01','Example','America/Los_Angeles','USD')")
    return con


def test_both_public_series_are_retrospective_only_and_idempotent():
    con = _database()
    first = append_public_prices(ROOT, con)
    assert first["new_price_rows"] == 62
    assert first["new_provenance_rows"] == 62
    assert con.execute("SELECT count(DISTINCT eia_series_id) FROM normalized.fuel_market_price").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM normalized.fuel_market_price WHERE price_published_at IS NOT NULL OR publication_precision <> 'unknown'").fetchone()[0] == 0
    assert con.execute("""SELECT count(*) FROM normalized.fuel_market_price m
        JOIN normalized.provenance_record p USING(provenance_id)
        WHERE p.available_time <= '2025-07-31T23:59:59Z'::TIMESTAMPTZ""").fetchone()[0] == 0
    assert con.execute("""SELECT count(*) FROM normalized.fuel_market_price m
        JOIN normalized.provenance_record p USING(provenance_id)
        WHERE p.available_time <= (SELECT max(retrieved_at) FROM normalized.provenance_record)""").fetchone()[0] == 62
    second = append_public_prices(ROOT, con)
    assert second["new_price_rows"] == second["new_provenance_rows"] == 0
    assert con.execute("SELECT count(*) FROM normalized.fuel_market_price").fetchone()[0] == 62
    con.close()


def test_historical_snapshot_keeps_simulated_prices_but_excludes_public_snapshot():
    con = _database()
    append_public_prices(ROOT, con)
    con.execute("""INSERT INTO normalized.provenance_record
        (provenance_id,tenant_id,origin_type,available_time,retrieved_at,availability_basis)
        VALUES ('SYN-P','T01','synthetic','2025-01-06T16:00:00Z',
                '2026-10-25T12:00:00Z','simulated')""")
    con.execute("""INSERT INTO normalized.fuel_market_price
        (provenance_id,tenant_id,market_price_version_id,market_week_price,market_region,
        price_observation_date,price_published_at,origin_label,publication_precision)
        VALUES ('SYN-P','T01','SYN-M',4.5,'CA','2025-01-06','2025-01-06T16:00:00Z',
                'synthetic','timestamp')""")
    result = con.execute("""SELECT m.origin_label,count(*)
        FROM normalized.fuel_market_price m JOIN normalized.provenance_record p USING(provenance_id)
        WHERE p.available_time <= '2025-01-15T08:00:00Z'::TIMESTAMPTZ GROUP BY 1""").fetchall()
    assert result == [('synthetic', 1)]
    con.close()


def test_tenant_projection_preserves_source_identity_without_cross_tenant_links():
    con = _database()
    con.execute("INSERT INTO normalized.core_tenant VALUES ('T02','Example2','America/Los_Angeles','USD')")
    result = append_public_prices(ROOT, con)
    assert result["tenant_scoped_price_rows"] == 124
    assert con.execute("SELECT count(DISTINCT source_record_id) FROM normalized.provenance_record").fetchone()[0] == 62
    assert con.execute("""SELECT count(*) FROM normalized.fuel_market_price m
        JOIN normalized.provenance_record p USING(provenance_id) WHERE m.tenant_id <> p.tenant_id""").fetchone()[0] == 0
    assert con.execute("SELECT count(*)-count(DISTINCT provenance_id) FROM normalized.provenance_record").fetchone()[0] == 0
    con.close()
