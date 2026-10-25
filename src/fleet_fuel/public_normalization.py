"""Project EIA background observations into tenant-scoped canonical tables.

Each tenant receives a reference to the same public observation. This does not
create additional independent prices or identify EIA data with real vehicles.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fleet_fuel.sources import acquire


def _identifier(prefix: str, text: str) -> str:
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _insert_missing(con, table: str, rows: list[dict], fields: list[dict], key: str) -> int:
    if not rows:
        return 0
    columns = [field["name"] for field in fields]
    values = []
    for row in rows:
        values.append(tuple(
            json.dumps(row[column], sort_keys=True) if field["type"] == "JSON" else row[column]
            for column, field in zip(columns, fields)
        ))
    quoted = ",".join('"' + column + '"' for column in columns)
    slots = ",".join("?" for _ in columns)
    # All keys include tenant identity. No table constraint is assumed because
    # the normalized staging tables may have been materialized with CTAS.
    existing = {row[0] for row in con.execute(f'SELECT "{key}" FROM normalized."{table}"').fetchall()}
    new = [value for value, row in zip(values, rows) if row[key] not in existing]
    if new:
        con.executemany(f'INSERT INTO normalized."{table}" ({quoted}) VALUES ({slots})', new)
    return len(new)


def append_public_prices(root: Path, con) -> dict:
    """Append public facts and their provenance atomically; safe to rerun.

    The caller must provide an open DuckDB connection outside an active
    transaction with canonical tables already created. Raw inputs are read-only.
    """
    root = Path(root)
    source = acquire(root)
    facts = [json.loads(line) for line in (root / source["normalized_path"]).read_text().splitlines() if line]
    contract = json.loads((root / "contracts/da_e01_contract.json").read_text())
    fields = {name: [f for f in contract["fields"] if f["table"] == name]
              for name in ("fuel_market_price", "provenance_record")}
    tenants = [row[0] for row in con.execute("SELECT tenant_id FROM normalized.core_tenant ORDER BY tenant_id").fetchall()]
    if not tenants:
        raise ValueError("Cannot project public prices without registered tenants")
    prices, provenance = [], []
    for tenant in tenants:
        for fact in facts:
            observation_key = fact["eia_series_id"] + ":" + fact["price_observation_date"]
            version_key = tenant + ":" + observation_key + ":" + source["snapshot_id"]
            pid = _identifier("EIA-P-", version_key)
            market_id = _identifier("EIA-M-", version_key)
            raw_ref = (fact["price_snapshot_ref"] + "#locator=" + fact["source_locator"]
                       + "&sha256=" + fact["raw_sha256"])
            price = {
                "provenance_id": pid, "tenant_id": tenant,
                "market_price_version_id": market_id,
                "market_week_price": fact["market_week_price"],
                "market_region": fact["market_region"],
                "eia_series_id": fact["eia_series_id"],
                "price_observation_date": fact["price_observation_date"],
                "price_published_at": None,
                "price_retrieved_at": fact["price_retrieved_at"],
                "price_snapshot_ref": raw_ref + "&url=" + fact["source_url"],
                "price_method_version": "EIA-diesel-methodology-effective-2022-06-13;adapter=" + fact["price_method_version"],
                "origin_label": "public", "publication_precision": "unknown",
            }
            states = {
                "fuel_market_price." + key: {
                    "state": "unknown" if value is None else "observed",
                    "reason": "Historical release time is not evidenced" if key == "price_published_at"
                    else "EIA source observation projected to tenant scope",
                }
                for key, value in price.items()
            }
            for key in ("event_time", "source_timezone", "source_utc_offset_minutes"):
                states["provenance_record." + key] = {
                    "state": "unknown",
                    "reason": "Source provides an observation date, not one precise regional timestamp",
                }
            states["provenance_record.synthetic_scenario_id"] = {
                "state": "not_applicable", "reason": "Pure public observation; no simulated price",
            }
            origins = {
                "fuel_market_price." + key: {
                    "origin_type": "derived" if key in ("provenance_id", "tenant_id", "market_price_version_id") else "public",
                    "source_dataset_ids": ["EIA-" + source["snapshot_id"]],
                    "reference": "tenant-scoped stable identifier; " + raw_ref if key in ("provenance_id", "tenant_id", "market_price_version_id") else raw_ref,
                }
                for key in price
            }
            p = {
                "provenance_id": pid, "source_system_id": "US_EIA_official_history",
                "source_record_id": observation_key,
                "record_version": source["snapshot_id"], "record_state": "active",
                "event_time": None,
                "available_time": fact["price_retrieved_at"],
                "retrieved_at": fact["price_retrieved_at"],
                "extract_as_of": fact["price_retrieved_at"],
                "raw_record_reference": raw_ref, "origin_type": "public",
                "source_dataset_id": "EIA-" + source["snapshot_id"],
                "synthetic_scenario_id": None, "value_states": states,
                "source_timezone": None, "source_utc_offset_minutes": None,
                "tenant_id": tenant, "field_origins": origins,
                "availability_basis": "observed",
                "availability_evidence": fact["price_snapshot_ref"] + ".receipt.json; historical publication unknown; retrospective use only",
                "canonical_table": "fuel_market_price",
                "canonical_record_key": {"tenant_id": tenant, "market_price_version_id": market_id},
                "parent_provenance_ids": [],
            }
            prices.append(price)
            provenance.append(p)
    con.execute("BEGIN TRANSACTION")
    try:
        p_count = _insert_missing(con, "provenance_record", provenance, fields["provenance_record"], "provenance_id")
        m_count = _insert_missing(con, "fuel_market_price", prices, fields["fuel_market_price"], "market_price_version_id")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {
        "status": "completed", "source_observations": len(facts), "tenant_count": len(tenants),
        "tenant_scoped_price_rows": len(prices), "new_price_rows": m_count,
        "new_provenance_rows": p_count, "snapshot_id": source["snapshot_id"],
        "source_access_mode": source["access_mode"],
        "historical_2025_visibility": "excluded_by_actual_2026_available_time",
        "duplication_meaning": "Tenant-scoped references to the same public facts; not independent observations",
    }
