"""Physical, accounting and reproducibility checks independent of reporting SQL."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fleet_fuel.simulation import build_plan, generate, select_trips, sub_seed

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    with path.open() as handle:
        return [json.loads(line) for line in handle]


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fleet-fuel-simulation-")
        cls.root = Path(cls.temp.name)
        for directory in ("contracts", "config"):
            (cls.root / directory).mkdir()
        shutil.copy(ROOT / "contracts/da_e01_contract.json", cls.root / "contracts")
        shutil.copy(ROOT / "config/simulation.json", cls.root / "config")
        cls.manifest = generate(cls.root, "smoke")
        cls.tables = {
            path.stem: read_jsonl(path)
            for path in (cls.root / "data/raw/tables").glob("*.jsonl")
        }
        cls.contract = json.loads((cls.root / "contracts/da_e01_contract.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_world_has_stable_ids_and_valid_intervals(self):
        plan = build_plan()
        self.assertEqual(len(plan), 1800)
        self.assertEqual(len({t["trip_id"] for t in plan}), 1800)
        self.assertEqual(len({t["tenant_id"] for t in plan}), 3)
        self.assertEqual(len({t["vehicle_id"] for t in plan}), 30)
        self.assertEqual(len({t["driver_id"] for t in plan}), 45)
        self.assertEqual(build_plan(), plan)
        self.assertNotEqual(build_plan(seed=1)[0]["load_kg"], plan[0]["load_kg"])
        for t in plan:
            start = datetime.fromisoformat(t["start_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(t["end_at"].replace("Z", "+00:00"))
            self.assertEqual((end - start).total_seconds(), t["expected_seconds"])
            self.assertEqual(t["idle_seconds"] + t["pto_seconds"] + t["moving_seconds"], t["expected_seconds"])
            self.assertGreater(t["distance_km"], 0)
        self.assertEqual(len(select_trips(plan, "smoke")), 100)
        self.assertTrue(select_trips(plan, "smoke") <= select_trips(plan, "full"))
        with self.assertRaises(ValueError):
            select_trips(plan, "unrecognized")
        # Prefix128, separator and byte-order are part of the public replay contract.
        independent = int.from_bytes(hashlib.sha256(b"20261021\x1ftrip\x1fT01-V01-TR001").digest()[:16], "big")
        self.assertEqual(sub_seed(20261021, "trip", "T01-V01-TR001"), independent)

    def test_all_source_fields_unique_keys_and_explicit_null_states(self):
        fields = collections.defaultdict(set)
        for field in self.contract["fields"]:
            fields[field["table"]].add(field["name"])
        metadata = {table["name"]: table for table in self.contract["tables"]}
        provenance = {r["provenance_id"]: r for r in self.tables["provenance_record"]}
        self.assertEqual(len(self.tables), 22)
        for name, rows in self.tables.items():
            self.assertTrue(rows, name)
            pk = metadata[name]["primary_key"]
            keys = [tuple(row[column] for column in pk) for row in rows]
            self.assertEqual(len(set(keys)), len(rows), name)
            for row in rows:
                self.assertEqual(set(row), fields[name], name)
                if name == "provenance_record" or "provenance_id" not in row:
                    continue
                p = provenance[row["provenance_id"]]
                self.assertEqual(p["origin_type"], "synthetic")
                self.assertEqual(p["canonical_table"], name)
                self.assertLessEqual(p["available_time"], p["extract_as_of"])
                self.assertEqual(p["canonical_record_key"], {c: row[c] for c in pk})
                for key, value in row.items():
                    if value is None:
                        state = p["value_states"][f"{name}.{key}"]
                        self.assertTrue(state["state"])
                        self.assertTrue(state["reason"])

    def test_independent_monthly_statement_controls(self):
        latest = {}
        for row in self.tables["fuel_purchase_line"]:
            key = row["tenant_id"], row["purchase_line_id"]
            if key not in latest or int(row["line_version"]) > int(latest[key]["line_version"]):
                latest[key] = row
        totals = collections.defaultdict(lambda: [0.0, 0.0])
        for row in latest.values():
            category = "nonfuel" if row["purchase_fuel_type"] == "nonfuel" else "fuel"
            total = totals[row["statement_id"], category]
            total[0] += row["purchase_amount"]
            total[1] += row["purchase_quantity_l"]
            if row["adjustment_type"] == "amount_refund":
                self.assertEqual(row["purchase_quantity_l"], 0)
                self.assertLess(row["purchase_amount"], 0)
        for control in self.tables["fuel_statement_control"]:
            actual = totals[control["statement_id"], control["category_code"]]
            self.assertAlmostEqual(actual[0], control["statement_control_amount"], places=6)
            # Per-line 6-decimal litres introduce at most one microlitre per row.
            self.assertLess(abs(actual[1] - control["statement_control_quantity"]), 0.0001)

    def test_physical_mass_balance_and_planned_distance(self):
        truth = read_jsonl(self.root / "validation/expected/physical_trip_ledger.jsonl")
        consumed = collections.defaultdict(float)
        for row in truth:
            self.assertGreater(row["true_fuel_l"], 0)
            self.assertGreater(row["closing_volume_l"], 0)
            self.assertLessEqual(row["closing_volume_l"], 650)
            consumed[row["vehicle_id"]] += row["true_fuel_l"]
        measurements = collections.defaultdict(list)
        for row in self.tables["fuel_inventory_measurement"]:
            measurements[row["vehicle_id"]].append(row)
        movement_totals = collections.defaultdict(float)
        unknown = set()
        for row in self.tables["fuel_movement"]:
            amount = row["fuel_movement_quantity_l"]
            if amount is None:
                unknown.add(row["vehicle_id"])
                continue
            sign = 1 if row["fuel_movement_type"] in {"refuel", "transfer_in"} else -1
            movement_totals[row["vehicle_id"]] += sign * amount
        self.assertEqual(unknown, {"T03-V08"})
        for vehicle, rows in measurements.items():
            rows.sort(key=lambda row: row["measured_at"])
            if vehicle in unknown:
                continue  # Unknown source volume must remain unknown in the report.
            implied = rows[0]["quantity_l"] + movement_totals[vehicle] - rows[-1]["quantity_l"]
            self.assertLess(abs(implied - consumed[vehicle]), 0.0001, vehicle)

    def test_as_of_versions_transport_failures_and_truth_separation(self):
        provenance = {r["provenance_id"]: r for r in self.tables["provenance_record"]}
        revised = [r for r in self.tables["fuel_counter_observation"] if "T02-V03-TR040-OBS0050" in r["counter_observation_id"]]
        self.assertEqual(len(revised), 2)
        self.assertGreater(provenance[revised[1]["provenance_id"]]["available_time"], provenance[revised[0]["provenance_id"]]["available_time"])
        self.assertAlmostEqual(revised[0]["fuel_total_l"] - revised[1]["fuel_total_l"], 3)
        events = read_jsonl(self.root / "data/raw/events.jsonl")
        self.assertTrue(all(isinstance(e["revision"], int) for e in events))
        keys = [(e["event_id"], e["revision"]) for e in events]
        self.assertGreater(len(keys), len(set(keys)))
        self.assertNotIn("counter_observation_id", events[-1]["payload"])
        self.assertEqual(events[-1]["event_id"], "TRANSPORT-MISSING-KEY")
        self.assertTrue(any(r["fuel_raw_unit"] == "unknown" for r in self.tables["fuel_counter_observation"]))
        for name, rows in self.tables.items():
            self.assertNotIn("true_fuel_l", rows[0], name)
        malformed = (self.root / "validation/expected/malformed_transport.jsonl").read_text().splitlines()[0]
        with self.assertRaises(json.JSONDecodeError):
            json.loads(malformed)

    def test_independent_hand_cases_and_dst_elapsed_time(self):
        cases = {c["scenario_id"]: c for c in json.loads((self.root / "validation/expected/hand_cases.json").read_text())}
        self.assertAlmostEqual((100 / 1.609344) / (20 / 3.785411784), cases["HAND-001"]["expected"]["numeric_value"], places=6)
        self.assertEqual(200 + 100 + 20 - 10 - 180, cases["HAND-002"]["expected"]["numeric_value"])
        start = datetime(2025, 3, 9, tzinfo=ZoneInfo("America/Los_Angeles"))
        elapsed = ((start + timedelta(days=1)).astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
        self.assertEqual(elapsed, cases["HAND-007"]["expected"]["numeric_value"])
        self.assertIsNone(cases["HAND-004"]["expected"]["numeric_value"])
        self.assertEqual(cases["HAND-004"]["expected"]["state_value"], "unknown")

    def test_frozen_configuration_replays_identical_source_bytes(self):
        original = {s["path"]: s["sha256"] for s in self.manifest["sources"]}
        (self.root / "data/raw/.events.jsonl.pending").write_text("partial transport write")
        (self.root / "data/raw/tables/provenance_record.tmp").write_text("partial provenance write")
        replay = generate(self.root, "smoke")
        self.assertEqual(original, {s["path"]: s["sha256"] for s in replay["sources"]})
        self.assertEqual(self.manifest["table_row_counts"], replay["table_row_counts"])


if __name__ == "__main__":
    unittest.main()
