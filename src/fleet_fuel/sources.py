"""EIA diesel-price acquisition with immutable evidence and offline replay.

This adapter downloads official files over HTTPS. It is not an EIA API client.
Public historic prices are retrospective context, never 2025 as-of evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_ID = "S22-PUB-001"
SOURCE_VERSION = "eia-html-xls-1.0.1"
START, END = date(2024, 12, 1), date(2025, 6, 30)
SERIES = {
    "EMD_EPD2D_PTE_SCA_DPG": ("California", "eia_california.html"),
    "EMD_EPD2D_PTE_R5XCA_DPG": (
        "West Coast except California", "eia_west_coast_ex_ca.html"
    ),
}
REGION_CODES = {"EMD_EPD2D_PTE_SCA_DPG": "CA", "EMD_EPD2D_PTE_R5XCA_DPG": "WEST_COAST_EX_CA"}
TARGETS = {
    filename: "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=" + series
    for series, (_, filename) in SERIES.items()
}
TARGETS["eia_diesel_history.xls"] = (
    "https://www.eia.gov/petroleum/gasdiesel/xls/psw18vwall.xls"
)
RIGHTS_URL = "https://www.eia.gov/about/copyrights_reuse.php"
METHOD_URL = "https://www.eia.gov/petroleum/gasdiesel/diesel_proc-methods.php"
MAX_BYTES = 5 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


class HistoryRows(HTMLParser):
    """Read the EIA history table without relying on cosmetic CSS selectors."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] = []
        self.cell: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        if tag == "tr":
            self.row = []
        if tag in ("td", "th"):
            self.cell = ""

    def handle_data(self, value: str) -> None:
        if self.cell is not None:
            self.cell += value

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        if tag == "tr" and self.row:
            self.rows.append(self.row)


def parse_history(data: bytes, series_id: str) -> list[dict]:
    parser = HistoryRows()
    parser.feed(data.decode("utf-8-sig"))
    parsed: dict[str, dict] = {}
    for row in parser.rows:
        if not row or not re.fullmatch(r"\d{4}-[A-Za-z]{3}", row[0]):
            continue
        year = int(row[0][:4])
        for i in range(1, len(row) - 1, 2):
            if not re.fullmatch(r"\d{2}/\d{2}", row[i]):
                continue
            obs = date.fromisoformat(f"{year}-{row[i].replace('/', '-')}")
            if not START <= obs <= END:
                continue
            value = row[i + 1]
            if value in {"-", "--", "NA", "W", ""}:
                price, state = None, value or "missing"
            else:
                price, state = str(Decimal(value).quantize(Decimal("0.001"))), "observed"
                if Decimal(price) <= 0:
                    raise ValueError("EIA non-positive price")
            if obs.weekday() != 0:
                raise ValueError(f"Unexpected non-Monday observation {obs}")
            record = {
                "eia_series_id": series_id,
                "market_region": REGION_CODES[series_id],
                "market_region_label": SERIES[series_id][0],
                "price_observation_date": obs.isoformat(),
                "market_week_price": price,
                "value_state": state,
                "source_locator": f"{row[0]}/{row[i]}",
            }
            key = obs.isoformat()
            if key in parsed and parsed[key] != record:
                raise ValueError(f"Conflicting source rows {series_id} {key}")
            parsed[key] = record
    expected = set()
    cur = START
    while cur <= END:
        if cur.weekday() == 0:
            expected.add(cur.isoformat())
        cur += timedelta(days=1)
    if set(parsed) != expected:
        raise ValueError(f"Missing/excess EIA weekly dates: {sorted(expected ^ set(parsed))}")
    return [parsed[k] for k in sorted(parsed)]


def _download(url: str, target: Path) -> dict:
    """Bounded retries; keep each failed attempt in the receipt."""
    attempts = []
    for attempt in range(1, 4):
        started = datetime.now(timezone.utc).isoformat()
        try:
            request = Request(url, headers={
                "User-Agent": "FleetFuelAnalytics/1.0",
                "Accept-Encoding": "identity",
            })
            with urlopen(request, timeout=30) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Source exceeds the 5 MiB acquisition limit")
                if response.status != 200:
                    raise ValueError(f"Expected complete HTTP 200, received {response.status}")
                receipt = {
                    "name": target.name, "url": url, "status": response.status,
                    "retrieved_at": started, "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data), "method": "GET",
                    "headers": {key: response.headers.get(key) for key in (
                        "Content-Type", "Last-Modified", "ETag", "Content-Length", "Date")},
                    "prior_failed_attempts": attempts,
                }
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError("Immutable snapshot path already exists")
            target.write_bytes(data)
            _write_json(target.with_name(target.name + ".receipt.json"), receipt)
            return receipt
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            code = getattr(exc, "code", None)
            attempts.append({"attempt": attempt, "at": started, "status": code, "error": str(exc)})
            if isinstance(exc, ValueError) or (code is not None and code not in (429, 500, 502, 503, 504)) or attempt == 3:
                _write_json(target.with_name(target.name + ".failed.json"), {"url": url, "attempts": attempts})
                raise
            time.sleep(attempt)
    raise RuntimeError("unreachable")


def _check_xls(path: Path, rows: list[dict]) -> dict:
    import xlrd

    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_name("Data 1")
    keys = sheet.row_values(1)
    columns = {series: keys.index(series) for series in SERIES}
    actual = {}
    for i in range(3, sheet.nrows):
        if sheet.cell_type(i, 0) != xlrd.XL_CELL_DATE:
            continue
        obs = xlrd.xldate_as_datetime(sheet.cell_value(i, 0), book.datemode).date()
        if not START <= obs <= END:
            continue
        for series, column in columns.items():
            value = sheet.cell_value(i, column)
            actual[(series, obs.isoformat())] = (
                str(Decimal(str(value)).quantize(Decimal("0.001"))) if isinstance(value, (int, float)) else None
            )
    mismatches = [r for r in rows if actual.get((r["eia_series_id"], r["price_observation_date"])) != r["market_week_price"]]
    if mismatches:
        raise ValueError(f"HTML/XLS source disagreement: {len(mismatches)} rows")
    return {
        "status": "passed", "html_rows_compared_to_xls": len(rows),
        "comparison": "independent formats of the same EIA publication, not an independent measurement",
        "sheet": "Data 1", "source_key_row": 2, "mismatches": 0,
    }


def acquire(root: Path, refresh: bool = False) -> dict:
    """Acquire once; default calls validate and reuse the exact cached snapshot.

    Failed public acquisition raises an explicit error. The caller may use the
    separate synthetic market-price tables, retaining the failure status.
    """
    root = Path(root)
    base = root / "data/public"
    manifest_path = base / "source_manifest.json"
    if manifest_path.exists() and not refresh and json.loads(manifest_path.read_text()).get("adapter_version") == SOURCE_VERSION:
        result = json.loads(manifest_path.read_text())
        for raw in result["files"]:
            if sha256(root / raw["path"]) != raw["sha256"]:
                raise ValueError(f"Changed cached source: {raw['path']}")
        if sha256(root / result["normalized_path"]) != result["normalized_sha256"]:
            raise ValueError("Changed normalized public prices")
        if sha256(base / "fuel_prices.jsonl") != result["normalized_sha256"]:
            raise ValueError("Changed current public-price export")
        return result
    # Existing original receipts are the first source acquisition, not re-dated.
    legacy = base / "raw"
    existing = all((legacy / n).exists() and (legacy / (n + ".receipt.json")).exists() for n in TARGETS)
    if existing and not refresh:
        raw_dir = legacy
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        raw_dir = base / "raw" / stamp
        for filename, url in TARGETS.items():
            _download(url, raw_dir / filename)
    files, rows = [], []
    for filename, url in TARGETS.items():
        path = raw_dir / filename
        receipt = json.loads(path.with_name(path.name + ".receipt.json").read_text())
        if receipt["sha256"] != sha256(path) or receipt["url"] != url:
            raise ValueError(f"Receipt mismatch {filename}")
        files.append({**receipt, "path": path.relative_to(root).as_posix(),
                      "receipt_path": path.with_name(path.name + ".receipt.json").relative_to(root).as_posix()})
        if filename.endswith("html"):
            series = next(k for k, v in SERIES.items() if v[1] == filename)
            release_match = re.search(r"(?<!Next )Release Date:\s*(\d{2}/\d{2}/\d{4})", path.read_text())
            page_release_date = datetime.strptime(release_match.group(1), "%m/%d/%Y").date().isoformat() if release_match else None
            for row in parse_history(path.read_bytes(), series):
                row.update({
                    "source_id": SOURCE_ID, "origin_type": "public",
                    "origin_label": "public_EIA_retrospective",
                    "currency": "USD", "unit": "USD/US_gal", "tax_basis": "including_taxes",
                    "price_published_at": None, "publication_precision": "unknown",
                    "price_retrieved_at": receipt["retrieved_at"],
                    "price_snapshot_ref": path.relative_to(root).as_posix(),
                    "price_method_version": SOURCE_VERSION,
                    "source_page_release_date": page_release_date,
                    "historical_available_time": None,
                    "allowed_use": "retrospective_context_only",
                    "source_url": url, "raw_sha256": receipt["sha256"],
                })
                rows.append(row)
    rows.sort(key=lambda r: (r["eia_series_id"], r["price_observation_date"]))
    xls_check = _check_xls(raw_dir / "eia_diesel_history.xls", rows)
    snapshot_id = hashlib.sha256(("".join(x["sha256"] for x in files) + SOURCE_VERSION).encode()).hexdigest()[:16]
    normalized = base / "snapshots" / snapshot_id / "fuel_prices.jsonl"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    if normalized.exists() and normalized.read_text() != body:
        raise ValueError("Snapshot ID collision or changed normalizer")
    normalized.write_text(body)
    # Convenience current exports; immutable version stays under snapshots/.
    (base / "fuel_prices.jsonl").write_text(body)
    with (base / "fuel_prices.csv").open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "source_id": SOURCE_ID, "adapter_version": SOURCE_VERSION,
        "status": "public_download_verified", "access_mode": "official_https_file_download_not_api",
        "snapshot_id": snapshot_id, "files": files, "rows": len(rows),
        "observation_start": min(r["price_observation_date"] for r in rows),
        "observation_end": max(r["price_observation_date"] for r in rows),
        "series_count": len(SERIES), "main_period_rows": sum(r["price_observation_date"] >= "2025-01-01" for r in rows),
        "missing_values": sum(r["market_week_price"] is None for r in rows),
        "normalized_path": normalized.relative_to(root).as_posix(),
        "normalized_sha256": sha256(normalized), "xls_crosscheck": xls_check,
        "rights_url": RIGHTS_URL, "methodology_url": METHOD_URL,
        "attribution": "Source: U.S. Energy Information Administration. Source-page release dates: " + ", ".join(sorted({r["source_page_release_date"] or "unknown" for r in rows})) + ". Retrieved: " + ", ".join(sorted({r["price_retrieved_at"][:10] for r in rows})) + ". Historical individual publication dates unknown.",
        "rights_scope": "EIA numeric data; no logos, photographs, or protected third-party material included in reports",
        "historical_availability": "unknown; no 2025 as-of joins",
        "geography_limit": "California is state-level; West Coast except California is regional, not AZ/NV state prices",
    }
    _write_json(normalized.parent / "manifest.json", result)
    _write_json(manifest_path, result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print(json.dumps(acquire(args.root, args.refresh), ensure_ascii=False, indent=2))
