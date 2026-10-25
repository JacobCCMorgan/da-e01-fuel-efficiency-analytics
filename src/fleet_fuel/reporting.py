"""Reproducible analytical figures and an offline portfolio report.

The reporting layer reads calculated tables; it does not estimate hidden truth or
replace failed calculations with illustrative numbers. All filtering preserves a
single report view so initial, revised and retrospective records are never summed.
"""
from __future__ import annotations

import html
import json
import math
import textwrap
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from plotly.offline import get_plotlyjs

NAVY, TEAL, AMBER, RED, PALE = "#163247", "#147d85", "#d99836", "#bd514f", "#edf3f6"
COLORS = [TEAL, "#5578a2", AMBER, "#9472a0", RED]
MPG_FACTOR = 3.785411784 / 1.609344
SOURCE_NOTE = ("Fleet operations and follow-up cases are synthetic. Official EIA prices, "
               "when present, are retrospective context. Results describe the simulated "
               "portfolio dataset, not verified customer savings or causal effects.")


def _safe(value: Any) -> Any:
    """Convert pandas/NumPy values to strict JSON (no NaN or Infinity)."""
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_safe(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        pass
    if hasattr(value, "as_integer_ratio"):
        return float(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    return _safe(frame.to_dict(orient="records"))


def _read_table(con, table: str) -> pd.DataFrame:
    return con.sql(f'SELECT * FROM normalized."{table}"').df()


def _num(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _view(output_id: Any) -> str:
    value = str(output_id).lower()
    for label in ("retrospective", "revised", "initial"):
        if value.endswith(label):
            return label
    raise ValueError(f"Report view is not encoded in output_id: {output_id}")


def _comparison(con) -> pd.DataFrame:
    frame=con.sql("SELECT * FROM analytics.efficiency_comparison").df()
    frame["week"]=pd.to_datetime(frame.report_week_start,utc=True).dt.tz_convert("America/Los_Angeles").dt.strftime("%Y-%m-%d")
    return frame.sort_values(["report_view","tenant_id","vehicle_id","week","task_type"]).reset_index(drop=True)


def _weekly(con, root: Path) -> pd.DataFrame:
    weekly, runs = _read_table(con, "fuel_weekly_metric"), _read_table(con, "fuel_report_run")
    if weekly.empty or runs.empty:
        raise ValueError("Run analysis before report: weekly metrics/report runs are empty.")
    wanted = ["tenant_id", "output_id", "report_week_start", "report_week_end"]
    if runs.duplicated(["tenant_id", "output_id"]).any():
        raise ValueError("Report run identifiers are not unique.")
    frame = weekly.merge(runs[wanted], on=["tenant_id", "output_id"], how="left", validate="many_to_one")
    if frame.report_week_start.isna().any():
        raise ValueError("A weekly result has no report-run lineage.")
    frame["view"] = frame.output_id.map(_view)
    frame["report_week_start"] = pd.to_datetime(frame.report_week_start, utc=True)
    frame["report_week_end"] = pd.to_datetime(frame.report_week_end, utc=True)
    frame["week"] = frame.report_week_start.dt.tz_convert("America/Los_Angeles").dt.strftime("%Y-%m-%d")
    extra = con.sql("SELECT tenant_id, weekly_metric_id, purchase_l FROM analytics.weekly_result").df()
    frame = frame.merge(extra, on=["tenant_id", "weekly_metric_id"], validate="one_to_one")
    frame["full_week"] = ((frame.report_week_start >= pd.Timestamp("2025-01-01", tz="America/Los_Angeles")) &
                           (frame.report_week_end <= pd.Timestamp("2025-07-01", tz="America/Los_Angeles")))
    frame = _num(frame, ["fuel_used_l", "distance_travelled_km", "measurement_coverage", "mpg",
                         "comparable_fuel_amount", "weighted_purchase_price_usd_per_l",
                         "benchmark_amount", "benchmark_amount_gap", "benchmark_match_coverage",
                         "purchase_price_effect", "purchase_quantity_effect", "valid_paired_seconds",
                         "expected_observation_seconds", "benchmark_matched_quantity_l",
                         "benchmark_eligible_quantity_l", "purchase_l"])
    frame["l_per_100km"] = np.where(frame.distance_travelled_km > 0,
                                      frame.fuel_used_l / frame.distance_travelled_km * 100, np.nan)
    frame["quality"] = np.select([frame.expected_observation_seconds.eq(0),frame.measurement_coverage.isna(), frame.measurement_coverage < .95],
                                   ["No operating exposure","Unknown", "Coverage below 95%"], default="Coverage at least 95%")
    # Report rows roll task-specific comparisons up without pooling task baselines.
    comparisons=_comparison(con)
    comparisons["intensity_review"]=comparisons.review_flag.eq("review_load_pto_route")
    comparisons["peer_eligible"]=comparisons.comparison_status.eq("descriptive_peer_comparison")
    rollup=comparisons.groupby(["tenant_id","vehicle_id","week","report_view"],dropna=False).agg(
        intensity_review=("intensity_review","any"),task_comparison_rows=("task_type","size"),
        eligible_task_comparisons=("peer_eligible","sum")).reset_index().rename(columns={"report_view":"view"})
    frame=frame.merge(rollup,on=["tenant_id","vehicle_id","week","view"],how="left",validate="one_to_one")
    frame["intensity_review"]=frame.intensity_review.eq(True)
    frame["task_comparison_rows"]=frame.task_comparison_rows.fillna(0).astype(int)
    frame["eligible_task_comparisons"]=frame.eligible_task_comparisons.fillna(0).astype(int)
    frame["market_gap_usd_per_l"] = np.where(frame.benchmark_matched_quantity_l > 0,
                                               frame.benchmark_amount_gap / frame.benchmark_matched_quantity_l,
                                               np.nan)
    frame["price_review"] = ((frame.market_gap_usd_per_l > .05) & (frame.benchmark_match_coverage >= .8)).fillna(False)
    frame["review_reason"] = frame.apply(lambda r: "; ".join(x for flag, x in [
        (r["quality"] in ["Unknown", "Coverage below 95%"], "Inspect coverage"),
        (r["eligible_task_comparisons"]==0 and r["expected_observation_seconds"]>0, "No eligible peer baseline"),
        (r["intensity_review"], "Higher intensity within task group"),
        (r["price_review"], "Positive matched market gap")]
        if flag) or "No reporting flag", axis=1)
    # Context uses dispatch metadata only. Hidden physical fuel truth is never read.
    trips_path = root / "data/raw/operations/trips.jsonl"
    frame["average_load_kg"], frame["pto_share"] = np.nan, np.nan
    if trips_path.exists():
        trips = pd.read_json(trips_path, lines=True)
        start_col = next((c for c in ["start", "start_at", "trip_start_at", "started_at"] if c in trips), None)
        end_col = next((c for c in ["end", "end_at", "trip_end_at", "ended_at"] if c in trips), None)
        if start_col and end_col and "load_kg" in trips:
            trips["_start"] = pd.to_datetime(trips[start_col], utc=True)
            trips["_end"] = pd.to_datetime(trips[end_col], utc=True)
            ctx = {}
            for (tenant, vehicle, week), g in frame.groupby(["tenant_id", "vehicle_id", "week"]):
                lo, hi = g.iloc[0].report_week_start, g.iloc[0].report_week_end
                ts = trips[(trips.tenant_id == tenant) & (trips.vehicle_id == vehicle)
                           & (trips["_start"] < hi) & (trips["_end"] > lo)].copy()
                if ts.empty:
                    continue
                seconds = (ts["_end"].clip(upper=hi) - ts["_start"].clip(lower=lo)).dt.total_seconds().clip(lower=0)
                duration = (ts["_end"] - ts["_start"]).dt.total_seconds().clip(lower=1)
                good = pd.to_numeric(ts.load_kg, errors="coerce").notna() & (seconds > 0)
                if not good.any():
                    continue
                load = float(np.average(pd.to_numeric(ts.loc[good, "load_kg"]), weights=seconds[good]))
                pto = float((pd.to_numeric(ts.get("pto_seconds", pd.Series(0, index=ts.index)), errors="coerce")
                             .fillna(0) * seconds / duration).sum() / seconds.sum())
                ctx[(tenant, vehicle, week)] = (load, pto)
            frame["average_load_kg"] = frame.apply(lambda r: ctx.get((r.tenant_id, r.vehicle_id, r.week), (np.nan, np.nan))[0], axis=1)
            frame["pto_share"] = frame.apply(lambda r: ctx.get((r.tenant_id, r.vehicle_id, r.week), (np.nan, np.nan))[1], axis=1)
    return frame.sort_values(["view","tenant_id","vehicle_id","week"]).reset_index(drop=True)


def _aggregate(frame: pd.DataFrame, group: list[str]) -> pd.DataFrame:
    cols = ["fuel_used_l", "distance_travelled_km", "valid_paired_seconds", "expected_observation_seconds",
            "comparable_fuel_amount", "purchase_price_effect", "purchase_quantity_effect",
            "benchmark_amount_gap", "benchmark_matched_quantity_l", "benchmark_eligible_quantity_l", "purchase_l"]
    result = frame.groupby(group, dropna=False)[cols].sum(min_count=1).reset_index()
    result["mpg"] = np.where(result.fuel_used_l > 0, result.distance_travelled_km / result.fuel_used_l * MPG_FACTOR, np.nan)
    result["coverage"] = np.where(result.expected_observation_seconds > 0,
                                   result.valid_paired_seconds / result.expected_observation_seconds, np.nan)
    result["market_gap_usd_per_l"] = np.where(result.benchmark_matched_quantity_l > 0,
                                               result.benchmark_amount_gap / result.benchmark_matched_quantity_l, np.nan)
    return result


def _style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 14, "axes.titleweight": "bold", "axes.labelcolor": NAVY,
                         "text.color": NAVY, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#c1ced6", "grid.color": "#dde5ea",
                         "figure.facecolor": "white", "axes.facecolor": "white",
                         "savefig.facecolor": "white", "legend.frameon": False})


def _save(fig, root, stem, note):
    fig.text(.035, .012, note, fontsize=8, color="#596b78", va="bottom", wrap=True)
    fig.tight_layout(rect=[.02, .075, .99, .97])
    path = root / "outputs/figures" / (stem + ".png")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(root))


def _static_figures(root: Path, weekly, balance, reviews, followup, evaluation, comparisons) -> list[dict]:
    _style()
    selected = weekly[weekly.view == "revised"].copy()
    if selected.empty:
        raise ValueError("Revised analytical results are required for the report.")
    retrospective = weekly[weekly.view == "retrospective"]
    figures = []
    def add(stem, title, fig, note, why):
        path = _save(fig, root, stem, note)
        figures.append({"id": stem, "title": title, "path": path, "caption": note, "interpretation": why})

    fleet = _aggregate(selected, ["tenant_id", "week"])
    fig, ax = plt.subplots(2, 1, figsize=(12.5, 7.4), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for i, (tenant, g) in enumerate(fleet.groupby("tenant_id")):
        x = pd.to_datetime(g.week)
        ax[0].plot(x, g.mpg, "o-", color=COLORS[i % len(COLORS)], markersize=3, label=tenant)
        ax[1].plot(x, g.coverage * 100, "o-", color=COLORS[i % len(COLORS)], markersize=3)
    ax[0].set(title="Fuel efficiency in context", ylabel="Paired-distance MPG (US gal)")
    ax[0].legend(ncol=3, loc="upper left")
    ax[1].axhline(95, color=RED, ls="--", lw=1, label="Review threshold")
    ax[1].set(ylabel="Paired-time coverage (%)", xlabel="Reporting week (America/Los_Angeles)")
    ax[1].legend(loc="lower left")
    for a in ax: a.grid(axis="y", alpha=.7)
    add("01_efficiency_coverage", "Efficiency and usable observation coverage", fig,
        "Revised view. Fleet MPG = total paired km / total paired L × 2.35215. Coverage uses expected operating seconds; partial boundary weeks retained.",
        "效率與覆蓋率一起閱讀；低覆蓋週不可只憑 MPG 排名，車隊數值採總量比。")

    pivot = selected.pivot_table(index="vehicle_id", columns="week", values="mpg", aggfunc="first").reindex(
        index=sorted(selected.vehicle_id.unique()),columns=sorted(selected.week.unique()))
    coverage = selected.pivot_table(index="vehicle_id", columns="week", values="measurement_coverage", aggfunc="first").reindex_like(pivot)
    fig, ax = plt.subplots(figsize=(13, 9))
    cmap = plt.get_cmap("YlGnBu").copy(); cmap.set_bad("#e6e9ed")
    im = ax.imshow(np.ma.masked_invalid(pivot.to_numpy()), aspect="auto", cmap=cmap)
    ax.set_yticks(range(len(pivot)), labels=pivot.index)
    ticks = list(range(0, len(pivot.columns), 2))
    ax.set_xticks(ticks, labels=[pivot.columns[i][5:] for i in ticks], rotation=45, ha="right")
    low = np.argwhere(coverage.to_numpy() < .95)
    if len(low): ax.scatter(low[:, 1], low[:, 0], s=14, marker="x", c=RED, label="Coverage <95%")
    ax.set(title="Vehicle-week comparison with evidence gaps", xlabel="Week start", ylabel="Synthetic vehicle")
    fig.colorbar(im, ax=ax, shrink=.7, label="MPG (US gal)")
    if len(low): ax.legend(loc="upper left", bbox_to_anchor=(0, -.12))
    add("02_vehicle_week_heatmap", "Vehicle-week efficiency matrix", fig,
        "Revised view; grey = no usable MPG. Red cross = coverage below 95%. Task mix and vehicle class must be considered before ranking.",
        "橫向辨識同車變化，縱向比較前先核對任務與覆蓋；灰格表示沒有可用效率，不是零效率。")

    fig, ax = plt.subplots(figsize=(12.5, 6.7))
    usable = selected.dropna(subset=["average_load_kg", "l_per_100km"])
    for i, (task, g) in enumerate(usable.groupby("task_comparison_group", dropna=False)):
        ax.scatter(g.average_load_kg / 1000, g.l_per_100km,
                   s=25 + g.pto_share.fillna(0).clip(0, 1) * 450,
                   c=COLORS[i % len(COLORS)], alpha=.65, edgecolors="white", linewidth=.5, label=str(task))
    ax.set(title="Consumption intensity against operating load", xlabel="Time-weighted dispatched load (tonnes)", ylabel="L / 100 paired km")
    if not usable.empty: ax.legend(title="Task group", loc="upper left", bbox_to_anchor=(1, 1))
    else: ax.text(.5, .5, "Load context unavailable; no values imputed", ha="center", transform=ax.transAxes)
    ax.grid(alpha=.35)
    add("03_operating_context", "Operating context and consumption", fig,
        "Each point is one vehicle-week in the revised view. Bubble size reflects PTO share. Dispatch metadata is context, not a causal explanation.",
        "較高載重與 PTO 可能伴隨較高耗用；此圖用來選擇可比情境，不能將相關性當成浪費原因。")

    agg = _aggregate(selected[selected.full_week], ["week"]).sort_values("week")
    valid = agg[agg.comparable_fuel_amount.notna()]
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    if len(valid) >= 2:
        prev, curr = valid.iloc[-2], valid.iloc[-1]
        start, end = float(prev.comparable_fuel_amount), float(curr.comparable_fuel_amount)
        pe = float(curr.purchase_price_effect) if pd.notna(curr.purchase_price_effect) else 0
        qe = float(curr.purchase_quantity_effect) if pd.notna(curr.purchase_quantity_effect) else 0
        residual = end - start - pe - qe
        labels, values = ["Previous", "Price", "Quantity", "Mix /\nunmatched", "Current"], [start, pe, qe, residual, end]
        bottoms, running = [0], start
        for v in values[1:4]: bottoms.append(min(running, running + v)); running += v
        bottoms.append(0)
        heights = [start, abs(pe), abs(qe), abs(residual), end]
        cs = [NAVY, TEAL if pe < 0 else AMBER, TEAL if qe < 0 else AMBER, "#9baab5", NAVY]
        ax.bar(range(5), heights, bottom=bottoms, color=cs, width=.68)
        for i, v in enumerate(values): ax.text(i, bottoms[i]+heights[i], f"${v:,.0f}", ha="center", va="bottom", fontsize=9)
        ax.set_ylim(top=max(b+h for b,h in zip(bottoms,heights))*1.15)
        ax.set_xticks(range(5), labels=labels)
        ax.set_title(f"Purchase-spend bridge\n{prev.week} → {curr.week}")
    else: ax.text(.5, .5, "Two comparable weeks required", ha="center", transform=ax.transAxes)
    ax.set_ylabel("Comparable fuel purchases (USD)"); ax.grid(axis="y", alpha=.35)
    price_frame = retrospective if not retrospective.empty else selected
    p = _aggregate(price_frame, ["tenant_id", "week"])
    for i, (tenant, g) in enumerate(p.groupby("tenant_id")):
        axes[1].plot(pd.to_datetime(g.week), g.market_gap_usd_per_l, "o-", markersize=3, color=COLORS[i % len(COLORS)], label=tenant)
    axes[1].axhline(0, color="#9baab5", lw=1)
    axes[1].set(title="Matched market-price gap", ylabel="USD / matched purchase L", xlabel="Week start")
    axes[1].legend(); axes[1].grid(axis="y", alpha=.35)
    add("04_price_quantity_bridge", "Price, quantity and market background", fig,
        "Left: latest two full revised weeks; residual is disclosed, not forced to zero. Right: retrospective market context, not historical as-of or achievable savings.",
        "先拆解價格與購油量，再檢查未能分解的組合差異；市場差額僅供調查，不是可實現節省。")

    b = balance.copy()
    fig, axes = plt.subplots(1, 3, figsize=(16, 6.7), gridspec_kw={"width_ratios": [1.2, 1, 1]})
    if not b.empty:
        for c in ["opening_volume_l", "closing_volume_l", "refuel_volume_l", "transfer_in_l", "removed_l", "balance_consumption_l", "uncertainty_l"]:
            b[c] = pd.to_numeric(b[c], errors="coerce")
        known = b.dropna(subset=["opening_volume_l", "closing_volume_l", "refuel_volume_l", "transfer_in_l", "removed_l", "balance_consumption_l"])
        if not known.empty:
            row = known.sort_values(["balance_consumption_l","balance_id"], ascending=[False,True]).iloc[0]
            labels = ["Opening", "Refuel", "Transfer in", "Removed", "Balance use", "Closing"]
            values = [row.opening_volume_l, row.refuel_volume_l, row.transfer_in_l, -row.removed_l, -row.balance_consumption_l, row.closing_volume_l]
            bottoms, running = [0], values[0]
            for v in values[1:5]: bottoms.append(min(running, running+v)); running += v
            bottoms.append(0)
            axes[0].bar(range(6), [abs(v) for v in values], bottom=bottoms, color=[NAVY, TEAL, TEAL, AMBER, AMBER, NAVY])
            for i, v in enumerate(values): axes[0].text(i,bottoms[i]+abs(v), f"{v:,.1f}", ha="center", va="bottom", fontsize=8)
            axes[0].set_ylim(top=max(b+abs(v) for b,v in zip(bottoms,values))*1.15)
            axes[0].set_xticks(range(6), labels=labels, rotation=30, ha="right")
            axes[0].set_title(f"A traceable tank window\n{row.vehicle_id}")
        comp=b.dropna(subset=["ecu_minus_inventory_l", "uncertainty_l"])
        if not comp.empty:
            axes[1].scatter(comp.balance_consumption_l, comp.ecu_minus_inventory_l, c=TEAL, s=25, alpha=.7)
            axes[1].errorbar(comp.balance_consumption_l, np.zeros(len(comp)), yerr=comp.uncertainty_l,
                             fmt="none", ecolor="#9baab5", alpha=.5, lw=1, label="Inventory uncertainty")
            axes[1].axhline(0, color=NAVY, lw=.8)
            axes[1].legend(fontsize=8)
        axes[1].set(title="Cross-source residual", xlabel="Balance consumption (L)", ylabel="ECU − balance (L)")
        counts = b.groupby("reconciliation_status", dropna=False).size().sort_values()
        axes[2].barh([textwrap.fill(str(s).replace("_", " "), 20) for s in counts.index], counts.values,
                     color=[TEAL if s=="within_measurement_uncertainty" else AMBER for s in counts.index])
        for i,v in enumerate(counts.values):axes[2].text(v+max(counts.values)*.015,i,str(v),va="center",fontsize=9)
        axes[2].set_xlim(right=max(counts.values)*1.13)
        axes[2].set(title="Evidence state", xlabel="Windows")
    else:
        for a in axes:a.text(.5,.5,"No inventory windows produced",ha="center",transform=a.transAxes)
    axes[0].set_ylabel("Fuel volume (L)")
    for a in axes:a.grid(axis="y" if a is axes[0] else "x",alpha=.3)
    add("05_inventory_reconciliation", "Inventory reconciliation and uncertainty", fig,
        "Bridge: largest known window. Residual uses the same tank window; grey bars show inventory uncertainty. Coverage and unknown transfers require separate investigation.",
        "橋接圖說明單一窗口的燃料守恆；中圖比對相同窗口的 ECU 與油箱平衡量，並保留量測不確定範圍。差額仍可能來自覆蓋或移動缺口，不能直接判為偷油。")

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.6))
    comp=comparisons[comparisons.report_view=="revised"].copy()
    plot_comp=comp[comp.comparison_status=="descriptive_peer_comparison"].dropna(subset=["relative_to_prior","relative_to_peer"])
    for flag, color, label in [(False,"#9baab5","Other comparable task rows"),(True,AMBER,"High against eligible peers")]:
        g=plot_comp[plot_comp.review_flag.eq("review_load_pto_route")==flag]
        axes[0].scatter(g.relative_to_prior*100,g.relative_to_peer*100,color=color,s=22,alpha=.65,label=label)
    axes[0].axvline(0,color=NAVY,lw=.8);axes[0].axhline(0,color=NAVY,lw=.8)
    axes[0].axhline(20,color=RED,ls="--",lw=1)
    axes[0].set(title="Same-vehicle and task-peer comparison",xlabel="Intensity change vs prior vehicle/task week (%)",ylabel="Intensity above peer median (%)")
    axes[0].legend(fontsize=8)
    reason_counts = pd.Series({"Coverage / unknown review":int(selected.quality.isin(["Unknown","Coverage below 95%"]).sum()),
                              "No eligible peer baseline":int(((selected.eligible_task_comparisons==0)&(selected.expected_observation_seconds>0)).sum()),
                              "Intensity review":int(selected.intensity_review.sum()),
                              "Price review":int(selected.price_review.sum()),
                              "No reporting flag":int((selected.review_reason=="No reporting flag").sum())})
    axes[1].barh(reason_counts.index[::-1], reason_counts.values[::-1],color=["#9baab5",TEAL,AMBER,"#5578a2",RED])
    for i,v in enumerate(reason_counts.values[::-1]):axes[1].text(v+max(reason_counts.values)*.015,i,str(v),va="center",fontsize=9)
    axes[1].set_xlim(right=max(reason_counts.values)*1.13)
    axes[1].set(title="Reporting review reasons",xlabel="Vehicle-week rows (reasons may overlap)")
    for a in axes:a.grid(alpha=.25)
    add("06_review_priority", "Review priorities and confidence", fig,
        "Peers: same tenant, vehicle class, task and week; ≥95% coverage, ≥3 other vehicles. High vs peers means ≥20% above median. Prices: >$0.05/L gap with ≥80% match.",
        "先確認資料品質，再調查同任務耗用偏高與價格差異；旗標不是故障、舞弊或浪費的結論。")

    fig, axes = plt.subplots(1, 3, figsize=(16, 6.5), gridspec_kw={"width_ratios": [1, 1.1, 1.3]})
    if not reviews.empty:
        counts=reviews.groupby("adoption_status",dropna=False).size().sort_values()
        axes[0].barh(counts.index.astype(str), counts.values,color=TEAL)
        axes[0].set(title="Report review and adoption",xlabel="Review cases")
    if not evaluation.empty:
        counts=evaluation.groupby("comparison_status",dropna=False).size().sort_values()
        axes[1].barh([textwrap.fill(str(s).replace("_", " "), 20) for s in counts.index],counts.values,
                    color=[TEAL if s=="comparable_descriptive_only" else AMBER for s in counts.index])
        axes[1].set(title="Comparison eligibility",xlabel="Review cases")
        comparable=evaluation[evaluation.comparison_status=="comparable_descriptive_only"].sort_values(["tenant_id","vehicle_id","review_case_id"]).copy()
        for i,(_,r) in enumerate(comparable.iterrows()):
            color=COLORS[i%len(COLORS)]
            axes[2].plot([0,1],[r.baseline_l_per_100km,r.standardized_followup_l_per_100km],"o-",color=color,alpha=.8,label=r.vehicle_id)
            axes[2].scatter([1],[r.followup_l_per_100km],s=35,marker="D",facecolors="none",edgecolors=color,
                            label="Raw follow-up" if i==0 else None)
            axes[2].plot([1,1],[r.followup_l_per_100km,r.standardized_followup_l_per_100km],":",color=color,lw=1)
        axes[2].set_xticks([0,1],labels=["Baseline","Standardized\nfollow-up"])
        axes[2].set(title="Task mix standardized comparison",ylabel="L / 100 paired km")
        if len(comparable):axes[2].legend(fontsize=8)
        else:axes[2].text(.5,.5,"No comparable cases",transform=axes[2].transAxes,ha="center")
    for a in axes:a.grid(axis="x",alpha=.3)
    for a in axes[:2]:a.xaxis.set_major_locator(MaxNLocator(integer=True))
    add("07_action_followup", "From report to investigation and follow-up", fig,
        "Synthetic exercise. Mature windows, ≥95% coverage. Filled follow-up points use baseline task distance shares; hollow diamonds are raw rates. No causal savings established.",
        "先區分採用、成熟度與可比性，再用基準期各任務的里程占比加權後續耗用強度，降低任務組合不同的影響。原始與標準化差異均可回查；仍不能將變化當作措施的因果效果。")
    # Findings are derived from the same plotted frames and accompany every format.
    valid_fleet=fleet.dropna(subset=["mpg", "coverage"])
    figures[0]["findings"]=[f"有量測的租戶週 MPG 範圍為 {valid_fleet.mpg.min():.2f}–{valid_fleet.mpg.max():.2f}；配對時間覆蓋率範圍為 {valid_fleet.coverage.min():.1%}–{valid_fleet.coverage.max():.1%}。不同工況尚未調整，不能直接當排名。"] if len(valid_fleet) else []
    figures[1]["findings"]=[f"矩陣共有 {len(pivot)} 輛車、{len(pivot.columns)} 週；{int(pivot.isna().sum().sum())} 格沒有可用 MPG，{len(low)} 格配對時間覆蓋低於 95%。"]
    task_stats=usable.groupby("task_comparison_group",dropna=False).l_per_100km.agg(["median","count"])
    figures[2]["findings"]=[f"{task}：{int(r['count'])} 筆車輛週的耗用強度中位數為 {r['median']:.2f} L/100km。這是各組描述性數值，仍須核對載重與 PTO 差異。" for task,r in task_stats.iterrows()]
    figures[3]["findings"]=[]
    if len(valid)>=2:
        figures[3]["findings"]=[f"{prev.week} 至 {curr.week} 的可比購油淨額由 US${start:,.2f} 變為 US${end:,.2f}；價格效果 US${pe:,.2f}、數量效果 US${qe:,.2f}、未分解差額 US${residual:,.2f}。"]
    figures[4]["findings"]=[f"{str(state)}：{int(count)} 個庫存窗口。" for state,count in balance.reconciliation_status.value_counts().items()]
    figures[5]["findings"]=[f"覆蓋查核 {int((selected.measurement_coverage < .95).sum())} 筆、任務內強度查核 {int(selected.intensity_review.sum())} 筆、價格查核 {int(selected.price_review.sum())} 筆。類別可重疊；未知覆蓋另留於明細。"]
    figures[6]["findings"]=[f"{str(status)}：{int(count)} 筆審閱案例。" for status,count in evaluation.comparison_status.value_counts().items()]
    if not evaluation.empty:
        comp=evaluation[evaluation.comparison_status=="comparable_descriptive_only"]
        for _,r in comp.iterrows():
            figures[6]["findings"].append(f"{r.vehicle_id} 的 {r.review_case_id}：基準 {r.baseline_l_per_100km:.2f}、原始後續 {r.followup_l_per_100km:.2f}、按基準任務組合標準化後續 {r.standardized_followup_l_per_100km:.2f} L/100km；標準化差異 {r.standardized_change_l_per_100km:+.2f}，任務里程占比最大變動 {r.max_task_distance_share_change*100:.2f} 個百分點。僅為合成情境的描述性比較。")
    return figures


def _dashboard(root: Path, weekly: pd.DataFrame, balance: pd.DataFrame, reviews: pd.DataFrame, evaluation: pd.DataFrame, comparisons: pd.DataFrame) -> Path:
    cols=["tenant_id","vehicle_id","week","view","fuel_used_l","distance_travelled_km","mpg",
          "measurement_coverage","valid_paired_seconds","expected_observation_seconds","comparable_fuel_amount",
          "weighted_purchase_price_usd_per_l","benchmark_amount_gap","benchmark_matched_quantity_l",
          "benchmark_eligible_quantity_l","benchmark_match_coverage","purchase_price_effect","purchase_quantity_effect",
          "task_comparison_group","average_load_kg","pto_share","l_per_100km","quality","review_reason",
          "purchase_l","full_week","output_id","as_of_time","report_week_start","report_week_end",
          "task_comparison_rows","eligible_task_comparisons"]
    payload={"weekly":_records(weekly[cols]),"inventory":_records(balance),"reviews":_records(reviews),"followup":_records(evaluation),"comparisons":_records(comparisons)}
    data=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).replace("<","\\u003c")
    template=r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fleet Fuel Efficiency | DA-E01</title>
<style>
:root{--navy:#163247;--teal:#147d85;--amber:#d99836;--muted:#5a6d7a;--line:#dbe5eb}*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--navy);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}header{background:var(--navy);color:white;padding:38px max(4vw,20px) 32px}header p{max-width:920px;color:#c7dce4;margin:8px 0}header h1{font-size:34px;margin:0;font-weight:650;letter-spacing:-.6px}.eyebrow{font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#8ad3d1}main{max-width:1500px;margin:auto;padding:24px}.filters{position:sticky;top:0;z-index:5;background:rgba(243,246,248,.97);border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;padding:12px 0}label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:4px}select{padding:9px 11px;border:1px solid #bfd0da;border-radius:6px;background:white;color:var(--navy);min-width:145px}button{border:0;background:var(--teal);color:white;border-radius:6px;padding:10px 16px;cursor:pointer}button.secondary{background:#e4eef1;color:var(--navy)}.note{background:#e9f1f3;border-left:4px solid var(--teal);padding:12px 16px;margin:18px 0;font-size:13px}.cards{display:grid;grid-template-columns:repeat(6,minmax(140px,1fr));gap:14px;margin:20px 0}.card{background:white;padding:18px;border:1px solid var(--line);border-radius:8px}.card small{display:block;color:var(--muted);font-size:12px}.card strong{font-size:26px;display:block;margin:5px 0;font-weight:650}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.panel{background:white;border:1px solid var(--line);border-radius:8px;padding:18px;min-width:0}.panel.wide{grid-column:1/-1}.panel h2{font-size:19px;margin:0 0 4px}.panel p{font-size:13px;color:var(--muted);margin:0 0 10px}.plot{height:365px}.plot.tall{height:650px}.tablewrap{overflow:auto;max-height:480px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}th{background:#eaf1f5;position:sticky;top:0;color:var(--navy)}th:first-child,td:first-child,td:last-child{text-align:left}tr:hover td{background:#f0f6f7}.count{color:var(--muted);font-size:12px}.empty{padding:80px 20px;text-align:center;color:var(--muted)}footer{color:var(--muted);font-size:12px;padding:26px 0}.links{display:flex;gap:18px;flex-wrap:wrap}.links a{color:var(--teal)}@media(max-width:900px){.cards{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.panel.wide{grid-column:auto}header h1{font-size:27px}main{padding:14px}.filters{position:static}.plot{height:340px}}
</style><script>__PLOTLY__</script></head><body>
<header><div class="eyebrow">DA-E01 · Fleet analytics portfolio</div><h1>Fuel efficiency, prices and evidence</h1><p>Separate fuel consumed from fuel purchased. Compare like operating conditions. Follow each reporting flag through investigation and evidence.</p></header>
<main><section class="filters" aria-label="Report filters">
<label>Report view<select id="view"><option value="revised">Revised · week +7 days</option><option value="initial">Initial · week +48 hours</option><option value="retrospective">Retrospective context</option></select></label>
<label>Tenant<select id="tenant"></select></label><label>Vehicle<select id="vehicle"></select></label>
<label>From week<select id="from"></select></label><label>To week<select id="to"></select></label>
<label>Evidence quality<select id="quality"><option value="all">All evidence states</option><option>Coverage at least 95%</option><option>Coverage below 95%</option><option>Unknown</option><option>No operating exposure</option></select></label>
<label>&nbsp;<button id="reset" class="secondary">Reset filters</button></label></section>
<div class="note" id="context"></div><section class="cards" id="cards"></section>
<div class="grid">
<section class="panel"><h2>Efficiency and coverage</h2><p>Total paired distance / total paired fuel. Coverage uses operating seconds, not message count.</p><div id="trend" class="plot"></div></section>
<section class="panel"><h2>Operating context</h2><p>Each point is a vehicle-week; load is dispatch context. Bubble size reflects PTO share.</p><div id="contextplot" class="plot"></div></section>
<section class="panel wide"><h2>Vehicle-week matrix</h2><p>Compare changes within each vehicle; use task and coverage details before comparing vehicles.</p><div id="heat" class="plot tall"></div></section>
<section class="panel wide"><h2>Two baselines for each vehicle and task</h2><p>Compare the same vehicle/task with its previous week, and with other vehicles in the same tenant, class, task and week. Eligible rows require ≥95% coverage and at least three peers. The 20% peer threshold is a review rule.</p><div id="peer" class="plot"></div></section>
<section class="panel"><h2>Purchase-spend decomposition</h2><p>Latest two adjacent full weeks. Unexplained mix / cohort changes are disclosed as a residual.</p><div id="bridge" class="plot"></div></section>
<section class="panel"><h2>Matched market background</h2><p>USD gap per matched litre with matching coverage. Positive gap is a comparison, not achievable savings.</p><div id="market" class="plot"></div></section>
<section class="panel"><h2>Inventory cross-check</h2><p>ECU minus tank balance over the same window. Grey error bars show tank uncertainty; unmatched records remain in the exported reconciliation table.</p><div id="inventory" class="plot"></div></section>
<section class="panel"><h2>Review and follow-up</h2><p>All case dates for selected tenants/vehicles. Synthetic exercise: adoption and comparison eligibility are separate observations.</p><div id="actions" class="plot"></div></section>
<section class="panel wide"><h2>Comparable follow-up evidence</h2><p>Mature cases meeting task and ≥95% coverage checks. Follow-up task rates are weighted by baseline distance shares. Changes remain descriptive; hover for original rates and coverage.</p><div id="followup" class="plot"></div></section>
<section class="panel wide"><h2>Action evidence ledger</h2><p>All case dates for selected tenants/vehicles. Active review time excludes waiting; recorded baselines are synthetic scenario observations. Missing outcomes stay unknown.</p><div class="tablewrap" id="action_detail"></div></section>
<section class="panel wide"><h2>Selected vehicle-week records</h2><p>Review flags guide investigation. They do not establish waste, fraud or a maintenance fault.</p><div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0"><span class="count" id="rowcount"></span><button id="download">Download selected CSV</button></div><div class="tablewrap" id="detail"></div></section>
<section class="panel wide"><h2>Task comparison evidence</h2><p>Excluded or insufficient baselines remain visible; missing comparisons are not zero difference. Detailed machine-readable results are in efficiency_comparison.csv.</p><div class="tablewrap" id="peer_detail"></div></section>
</div><footer><p>__SOURCE__</p><p>Reporting rules: coverage &lt;95%; task intensity ≥20% above an eligible peer median; positive matched-price gap &gt;$0.05/L with matching coverage ≥80%. These thresholds are review rules, not an optimized predictive model.</p><div class="links"><a href="../docs/metrics.md">Metric definitions</a><a href="../docs/chart_walkthrough_zh.md">中文圖表講解</a><a href="../validation/quality_report.json">Quality results</a><a href="report_content.json">Structured report data</a></div></footer></main>
<script id="report-data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('report-data').textContent), rows=D.weekly;
const $=id=>document.getElementById(id), colors=['#147d85','#5578a2','#d99836','#9472a0','#bd514f'];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=1)=>v==null||!Number.isFinite(+v)?'Unknown':(+v).toLocaleString('en-US',{maximumFractionDigits:n,minimumFractionDigits:n});
const sum=(rs,k)=>rs.reduce((a,r)=>a+(Number.isFinite(+r[k])&&r[k]!=null?+r[k]:0),0);
const unique=(rs,k)=>[...new Set(rs.map(r=>r[k]))].sort();
function options(id,values,all){$(id).innerHTML=(all?'<option value="all">All</option>':'')+values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')}
options('tenant',unique(rows,'tenant_id'),true);options('vehicle',unique(rows,'vehicle_id'),true);
const weeks=unique(rows,'week');options('from',weeks,false);options('to',weeks,false);$('to').value=weeks.at(-1);
let current=[];
function selected(){return rows.filter(r=>r.view===$('view').value&&($('tenant').value==='all'||r.tenant_id===$('tenant').value)&&($('vehicle').value==='all'||r.vehicle_id===$('vehicle').value)&&r.week>=$('from').value&&r.week<=$('to').value&&($('quality').value==='all'||r.quality===$('quality').value))}
function groups(rs,k){let m={};rs.forEach(r=>(m[r[k]]??=[]).push(r));return Object.entries(m).sort(([a],[b])=>a.localeCompare(b))}
const layout={paper_bgcolor:'white',plot_bgcolor:'white',font:{family:'system-ui,sans-serif',color:'#163247',size:11},margin:{l:62,r:30,t:24,b:55},legend:{orientation:'h',y:1.15},hovermode:'closest',xaxis:{gridcolor:'#e4edf1'},yaxis:{gridcolor:'#e4edf1'},colorway:colors};
function plot(id,traces,extra={}){Plotly.react(id,traces,{...layout,...extra},{responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']})}
function filteredCases(cs){return cs.filter(r=>($('tenant').value==='all'||r.tenant_id===$('tenant').value)&&($('vehicle').value==='all'||r.vehicle_id===$('vehicle').value))}
function render(){const rs=current=selected();let fuel=sum(rs,'fuel_used_l'),km=sum(rs,'distance_travelled_km'),expected=sum(rs,'expected_observation_seconds'),valid=sum(rs,'valid_paired_seconds'),amount=sum(rs,'comparable_fuel_amount');
$('context').textContent=$('view').value==='retrospective'?'Retrospective view: official historical prices may have been retrieved after 2025. They are not evidence of what was known at the original reporting deadline.':'Historical reporting replay: only inputs available by the specified cutoff are eligible. Market references are synthetic as-of context unless historical availability is evidenced.';
const cards=[['Fleet MPG',fuel>0?fmt(km/fuel*2.3521458333333334):'Unknown','Same accepted distance / fuel intervals'],['Paired distance',fmt(km,0)+' km','Accepted intervals only'],['Fuel consumed',fmt(fuel,0)+' L','ECU paired consumption'],['Observation coverage',expected>0?fmt(valid/expected*100)+'%':'Unknown','Valid paired / expected seconds'],['Net purchased volume',fmt(sum(rs,'purchase_l'),0)+' L','Comparable transactions, including credits'],['Fuel purchases','$'+fmt(amount,0),'Transactions; not consumption cost']];
$('cards').innerHTML=cards.map(c=>`<div class="card"><small>${c[0]}</small><strong>${c[1]}</strong><small>${c[2]}</small></div>`).join('');
const wg=groups(rs,'week'),x=wg.map(([w])=>w),mpg=wg.map(([,g])=>sum(g,'fuel_used_l')>0?sum(g,'distance_travelled_km')/sum(g,'fuel_used_l')*2.3521458333333334:null),coverage=wg.map(([,g])=>sum(g,'expected_observation_seconds')>0?100*sum(g,'valid_paired_seconds')/sum(g,'expected_observation_seconds'):null);
plot('trend',[{x,y:mpg,name:'Fleet MPG',type:'scatter',mode:'lines+markers',line:{color:colors[0]}},{x,y:coverage,name:'Coverage %',type:'scatter',mode:'lines+markers',yaxis:'y2',line:{color:colors[2],dash:'dot'}}],{yaxis:{title:{text:'MPG (US gal)'},gridcolor:'#e4edf1'},yaxis2:{title:{text:'Coverage %'},overlaying:'y',side:'right',showgrid:false},margin:{l:60,r:60,t:30,b:50}});
plot('contextplot',groups(rs,'task_comparison_group').map(([t,g],i)=>({x:g.map(r=>r.average_load_kg==null?null:r.average_load_kg/1000),y:g.map(r=>r.l_per_100km),text:g.map(r=>`${r.vehicle_id} | ${r.week}<br>Coverage ${r.measurement_coverage==null?'Unknown':fmt(r.measurement_coverage*100)+'%'}`),name:t,type:'scatter',mode:'markers',marker:{size:g.map(r=>7+35*(r.pto_share||0)),opacity:.65,color:colors[i%colors.length]},hovertemplate:'%{text}<br>Load %{x:.1f} tonnes<br>%{y:.1f} L/100km<extra></extra>'})),{xaxis:{title:{text:'Time-weighted load (tonnes)'}},yaxis:{title:{text:'L / 100 paired km'}}});
const vehicles=unique(rs,'vehicle_id'),ws=unique(rs,'week'),lookup=new Map(rs.map(r=>[r.vehicle_id+'|'+r.week,r]));
plot('heat',[{x:ws,y:vehicles,z:vehicles.map(v=>ws.map(w=>lookup.get(v+'|'+w)?.mpg??null)),text:vehicles.map(v=>ws.map(w=>{let r=lookup.get(v+'|'+w);return r?`Coverage ${r.measurement_coverage==null?'Unknown':fmt(r.measurement_coverage*100)+'%'}<br>${esc(r.review_reason)}`:'No usable record'})),type:'heatmap',colorscale:'YlGnBu',hoverongaps:false,hovertemplate:'%{y} | %{x}<br>MPG %{z:.2f}<br>%{text}<extra></extra>',colorbar:{title:{text:'MPG'}}}],{height:Math.max(350,vehicles.length*19+110),margin:{l:100,r:60,t:15,b:65},yaxis:{autorange:'reversed'},xaxis:{type:'category',tickangle:-45}});
let selectedKeys=new Set(rs.map(r=>r.tenant_id+'|'+r.vehicle_id+'|'+r.week));let comps=D.comparisons.filter(r=>r.report_view===$('view').value&&selectedKeys.has(r.tenant_id+'|'+r.vehicle_id+'|'+r.week));let shown=comps.filter(r=>r.comparison_status==='descriptive_peer_comparison'&&r.relative_to_prior!=null&&r.relative_to_peer!=null);
plot('peer',groups(shown,'task_type').map(([task,g],i)=>({x:g.map(r=>r.relative_to_prior*100),y:g.map(r=>r.relative_to_peer*100),type:'scatter',mode:'markers',name:task,marker:{color:colors[i%colors.length],size:8,opacity:.65},text:g.map(r=>`${r.vehicle_id} | ${r.week}<br>${r.vehicle_class} | ${r.peer_count} other peers<br>${r.review_flag}`),hovertemplate:'%{text}<br>Prior difference %{x:.1f}%<br>Peer difference %{y:.1f}%<extra></extra>'})),{xaxis:{title:{text:'Intensity difference vs prior vehicle/task week (%)'},zeroline:true,zerolinecolor:'#163247'},yaxis:{title:{text:'Intensity above peer median (%)'},zeroline:true,zerolinecolor:'#163247'},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:20,y1:20,line:{color:'#bd514f',dash:'dash',width:1}}]});
let pcs=[['vehicle_id','Vehicle'],['week','Week'],['task_type','Task'],['measurement_coverage','Coverage'],['l_per_100km','Current L/100km'],['prior_l_per_100km','Prior L/100km'],['peer_median_l_per_100km','Peer median'],['peer_count','Other peers'],['comparison_status','Eligibility'],['review_flag','Review rule']];$('peer_detail').innerHTML='<table><thead><tr>'+pcs.map(([,s])=>`<th>${s}</th>`).join('')+'</tr></thead><tbody>'+comps.map(r=>'<tr>'+pcs.map(([k])=>`<td>${r[k]==null?'Unknown':k==='measurement_coverage'?fmt(r[k]*100)+'%':typeof r[k]==='number'?fmt(r[k]):esc(r[k])}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
let full=wg.filter(([,g])=>g.every(r=>r.full_week)), pairs=full.slice(1).map((v,i)=>[full[i],v]).filter(([[a],[b]])=>Date.parse(b)-Date.parse(a)===604800000);if(pairs.length){let [[pw,pg],[cw,cg]]=pairs.at(-1),p=sum(pg,'comparable_fuel_amount'),c=sum(cg,'comparable_fuel_amount'),pe=sum(cg,'purchase_price_effect'),qe=sum(cg,'purchase_quantity_effect');plot('bridge',[{type:'waterfall',orientation:'v',x:[pw,'Price','Quantity','Mix / unmatched',cw],y:[p,pe,qe,c-p-pe-qe,0],measure:['absolute','relative','relative','relative','total'],connector:{line:{color:'#9baab5'}},increasing:{marker:{color:colors[2]}},decreasing:{marker:{color:colors[0]}},totals:{marker:{color:'#163247'}},hovertemplate:'%{x}<br>$%{y:,.2f}<extra></extra>'}],{yaxis:{title:{text:'Comparable purchase USD'}}})}else plot('bridge',[],{annotations:[{text:'Select two adjacent full weeks',showarrow:false,x:.5,y:.5,xref:'paper',yref:'paper'}]});
plot('market',[{x,y:wg.map(([,g])=>sum(g,'benchmark_matched_quantity_l')>0?sum(g,'benchmark_amount_gap')/sum(g,'benchmark_matched_quantity_l'):null),type:'scatter',mode:'lines+markers',name:'Gap USD/L',line:{color:colors[0]}},{x,y:wg.map(([,g])=>sum(g,'benchmark_eligible_quantity_l')>0?100*sum(g,'benchmark_matched_quantity_l')/sum(g,'benchmark_eligible_quantity_l'):null),type:'scatter',mode:'lines',name:'Matched quantity %',yaxis:'y2',line:{color:colors[2],dash:'dot'}}],{yaxis:{title:{text:'Gap USD / matched L'}},yaxis2:{title:{text:'Matched %'},overlaying:'y',side:'right',showgrid:false},margin:{l:60,r:60,t:30,b:50}});
let lo=rs.length?Math.min(...rs.map(r=>Date.parse(r.report_week_start))):NaN,hi=rs.length?Math.max(...rs.map(r=>Date.parse(r.report_week_end))):NaN;
let bi=filteredCases(D.inventory).filter(r=>Date.parse(r.period_start_at)<hi&&Date.parse(r.period_end_at)>lo),bc=bi.filter(r=>r.ecu_minus_inventory_l!=null&&r.uncertainty_l!=null);
plot('inventory',[{x:bc.map(r=>r.balance_consumption_l),y:bc.map(r=>r.ecu_minus_inventory_l),type:'scatter',mode:'markers',marker:{color:colors[0],size:8},text:bc.map(r=>`${r.vehicle_id} | ${r.balance_id}<br>${r.reconciliation_status}`),name:'ECU minus tank',hovertemplate:'%{text}<br>Balance %{x:.1f} L<br>Residual %{y:.1f} L<extra></extra>'},{x:bc.map(r=>r.balance_consumption_l),y:bc.map(()=>0),type:'scatter',mode:'markers',marker:{size:3,color:'#9baab5'},error_y:{type:'data',array:bc.map(r=>r.uncertainty_l),visible:true,color:'#9baab5',thickness:1},name:'Inventory uncertainty'}],{xaxis:{title:{text:'Balance consumption L'}},yaxis:{title:{text:'ECU − tank balance L'}}});
let ar=filteredCases(D.reviews),ac=groups(ar,'adoption_status'),fe=filteredCases(D.followup),fc=groups(fe,'comparison_status');plot('actions',[{x:ac.map(([s])=>s),y:ac.map(([,g])=>g.length),type:'bar',marker:{color:colors[0]},name:'Adoption'},{x:fc.map(([s])=>s),y:fc.map(([,g])=>g.length),type:'bar',marker:{color:colors[2]},name:'Comparison eligibility'}],{xaxis:{tickangle:-25,tickfont:{size:9}},yaxis:{title:{text:'Review cases'}},margin:{l:50,r:20,t:35,b:120}});
let eligible=fe.filter(r=>r.comparison_status==='comparable_descriptive_only');plot('followup',eligible.map((r,i)=>({x:['Baseline','Task-standardized follow-up'],y:[r.baseline_l_per_100km,r.standardized_followup_l_per_100km],type:'scatter',mode:'lines+markers',name:r.vehicle_id+' · '+r.review_case_id,line:{color:colors[i%colors.length]},text:[`Paired ${fmt(r.baseline_valid_seconds/3600)} / expected ${fmt(r.baseline_expected_seconds/3600)} hours`,`Paired ${fmt(r.followup_valid_seconds/3600)} / expected ${fmt(r.followup_expected_seconds/3600)} hours<br>Unstandardized rate ${fmt(r.followup_l_per_100km,2)} L/100km`],hovertemplate:'%{x}<br>%{y:.2f} L/100km<br>%{text}<extra>%{fullData.name}</extra>'})),{yaxis:{title:{text:'L / 100 paired km'}},legend:{orientation:'v',x:1.02,y:1},margin:{l:60,r:250,t:20,b:50},annotations:eligible.length?[]:[{text:'No comparable cases for this selection',showarrow:false,x:.5,y:.5,xref:'paper',yref:'paper'}]});
let actioncols=[['review_case_id','Case'],['vehicle_id','Vehicle'],['adoption_status','Adoption'],['action_type','Action'],['comparison_status','Comparison state'],['active_review_seconds','Active review sec'],['baseline_review_seconds','Baseline review sec'],['investigation_seconds','Investigation sec'],['baseline_l_per_100km','Baseline L/100km'],['followup_l_per_100km','Follow-up L/100km'],['change_l_per_100km','Raw change'],['standardized_followup_l_per_100km','Standardized follow-up'],['standardized_change_l_per_100km','Standardized change']];$('action_detail').innerHTML='<table><thead><tr>'+actioncols.map(([,s])=>`<th>${s}</th>`).join('')+'</tr></thead><tbody>'+fe.map(r=>'<tr>'+actioncols.map(([k])=>`<td>${r[k]==null?'Unknown':typeof r[k]==='number'?fmt(r[k]):esc(r[k])}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
const ordered=[...rs].sort((a,b)=>(b.review_reason!=='No reporting flag')-(a.review_reason!=='No reporting flag')||a.vehicle_id.localeCompare(b.vehicle_id)||a.week.localeCompare(b.week));
const cols=[['vehicle_id','Vehicle'],['week','Week'],['task_comparison_group','Task group'],['mpg','MPG'],['measurement_coverage','Coverage'],['fuel_used_l','Consumed L'],['comparable_fuel_amount','Purchases USD'],['benchmark_amount_gap','Market gap USD'],['review_reason','Review reason'],['output_id','Output ID'],['as_of_time','Available-by cutoff']];
$('rowcount').textContent=`${rs.length.toLocaleString()} selected rows · ${unique(rs,'vehicle_id').length} vehicles · one report view only`;
$('detail').innerHTML='<table><thead><tr>'+cols.map(([,l])=>`<th>${l}</th>`).join('')+'</tr></thead><tbody>'+ordered.map(r=>'<tr>'+cols.map(([k])=>`<td>${k==='measurement_coverage'?(r[k]==null?'Unknown':fmt(r[k]*100)+'%'):typeof r[k]==='number'?fmt(r[k]):esc(r[k])}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
}
['view','tenant','vehicle','from','to','quality'].forEach(id=>$(id).addEventListener('change',()=>{if(id==='tenant'){let v=$('vehicle').value;options('vehicle',unique(rows.filter(r=>$('tenant').value==='all'||r.tenant_id===$('tenant').value),'vehicle_id'),true);if([...$('vehicle').options].some(o=>o.value===v))$('vehicle').value=v;}render()}));
$('reset').onclick=()=>{$('view').value='revised';$('tenant').value='all';options('vehicle',unique(rows,'vehicle_id'),true);$('from').value=weeks[0];$('to').value=weeks.at(-1);$('quality').value='all';render()};
$('download').onclick=()=>{if(!current.length)return;const keys=Object.keys(current[0]);const q=v=>'"'+String(v??'').replace(/"/g,'""')+'"';let content=[keys.map(q).join(','),...current.map(r=>keys.map(k=>q(r[k])).join(','))].join('\r\n');let a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+content],{type:'text/csv;charset=utf-8'}));a.download='DA-E01_selected_'+$('view').value+'.csv';a.click();URL.revokeObjectURL(a.href)};
render();
</script></body></html>'''
    output=template.replace("__PLOTLY__",get_plotlyjs()).replace("__DATA__",data).replace("__SOURCE__",html.escape(SOURCE_NOTE))
    path=root/"outputs/dashboard.html";path.write_text(output,encoding="utf-8")
    return path


def report(root: str | Path) -> dict:
    root=Path(root).resolve()
    (root/"outputs/figures").mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(root/"data/DA-E01.duckdb"),read_only=True)
    con.execute("SET TimeZone='UTC'")
    try:
        weekly=_weekly(con,root)
        balance=con.sql("SELECT * FROM analytics.inventory_reconciliation ORDER BY tenant_id,vehicle_id,period_start_at,balance_id").df()
        reviews=_read_table(con,"fuel_output_review").sort_values(["tenant_id","review_case_id"])
        followup=_read_table(con,"fuel_action_followup").sort_values(["tenant_id","action_followup_id"])
        evaluation=con.sql("SELECT * FROM analytics.followup_evaluation ORDER BY tenant_id,vehicle_id,review_case_id").df()
        comparisons=_comparison(con)
    finally:con.close()
    figures=_static_figures(root,weekly,balance,reviews,followup,evaluation,comparisons)
    dashboard=_dashboard(root,weekly,balance,reviews,evaluation,comparisons)
    chosen=weekly[weekly.view=="revised"]
    fleet=_aggregate(chosen,["view"]).iloc[0]
    timed=evaluation.dropna(subset=["active_review_seconds","baseline_review_seconds"])
    summary={"vehicle_count":int(chosen.vehicle_id.nunique()),"tenant_count":int(chosen.tenant_id.nunique()),
             "vehicle_week_rows":len(chosen),"report_week_count":int(chosen.week.nunique()),
             "paired_distance_km":float(fleet.distance_travelled_km),"fuel_used_l":float(fleet.fuel_used_l),
             "fleet_mpg":float(fleet.mpg),"paired_time_coverage":float(fleet.coverage),
             "comparable_purchase_amount_usd":float(fleet.comparable_fuel_amount),
             "low_coverage_rows":int((chosen.measurement_coverage<.95).sum()),
             "no_operating_exposure_rows":int(chosen.quality.eq("No operating exposure").sum()),
             "unknown_coverage_rows":int(chosen.quality.eq("Unknown").sum()),
             "intensity_review_rows":int(chosen.intensity_review.sum()),"price_review_rows":int(chosen.price_review.sum()),
             "no_eligible_peer_rows":int(((chosen.eligible_task_comparisons==0)&(chosen.expected_observation_seconds>0)).sum()),
             "review_case_count":len(reviews),"action_case_count":len(followup),"inventory_window_count":len(balance),
             "comparable_followup_cases":int((evaluation.comparison_status=="comparable_descriptive_only").sum()),
             "timed_review_cases":len(timed),"recorded_active_review_seconds":float(timed.active_review_seconds.sum()),
             "recorded_baseline_review_seconds":float(timed.baseline_review_seconds.sum()),
             "followup_statuses":evaluation.comparison_status.value_counts().to_dict()}
    weekly.drop(columns=["input_provenance_ids"],errors="ignore").to_csv(root/"outputs/report_weekly_detail.csv",index=False)
    chosen[chosen.review_reason!="No reporting flag"].drop(columns=["input_provenance_ids"],errors="ignore").to_csv(root/"outputs/review_candidates.csv",index=False)
    sections=[
        {"title":"資料範圍與分析口徑","text":[
            f"修訂版分析涵蓋 {summary['tenant_count']} 個合成租戶、{summary['vehicle_count']} 輛車、{summary['report_week_count']} 個報告週，共 {summary['vehicle_week_rows']:,} 筆車輛週資料。",
            f"可配對里程為 {summary['paired_distance_km']:,.1f} km，對應耗用 {summary['fuel_used_l']:,.1f} L；車隊 MPG 由兩者總量計算為 {summary['fleet_mpg']:.2f}。有效觀測時間覆蓋率為 {summary['paired_time_coverage']:.1%}。",
            "初版、修訂版與事後背景分開保存，不將多個版本重複加總。首尾部分週保留；合成營運數據的結果不能外推為真實車隊效果。"]},
        {"title":"效率與工況","text":[
            f"共有 {summary['low_coverage_rows']} 筆車輛週低於 95% 配對時間覆蓋，應先核對觀測缺口再比較效率。",
            f"另有 {summary['no_operating_exposure_rows']} 筆沒有預定營運時間，效率不適用；{summary['unknown_coverage_rows']} 筆覆蓋未知。無營運、未知與低覆蓋分開處理。",
            f"按租戶、車型、任務與週分組的同儕規則標出 {summary['intensity_review_rows']} 筆需進一步調查的車輛週。每一任務分開與同車前週及至少三輛同儕比較；旗標不是浪費或故障的已驗證標籤。"],"figures":[figures[i] for i in [0,1,2]]},
        {"title":"購油支出與價格背景","text":[
            f"修訂版可比燃油購買淨額合計為 US${summary['comparable_purchase_amount_usd']:,.2f}。購油支出與 ECU 耗用分開，不能用此金額直接宣稱當期耗用成本。",
            "價量分解按固定順序計算；無法歸入價格或數量效果的組合差異另列。公開市場價格只用在具有適用證據的比較，事後取得的歷史價格不放入當時資訊回放。"],"figures":[figures[3]]},
        {"title":"燃料平衡與調查優先順序","text":[
            f"共產生 {summary['inventory_window_count']} 個庫存觀察窗口。只有邊界、油箱範圍與燃料移動能核對時才形成可解釋平衡量。",
            "先處理低覆蓋與關聯問題，再調查高耗用強度或價格差異；保留未知狀態與原件證據，避免將量測問題解讀成營運損失。"],"figures":[figures[4],figures[5]]},
        {"title":"報告採用與後續觀察","text":[
            f"合成流程包含 {summary['review_case_count']} 筆報告審閱案例與 {summary['action_case_count']} 筆措施追蹤。實際收到報告、是否採用與後續窗口是否成熟各自記錄。",
            f"其中 {summary['timed_review_cases']} 筆具有可對照的工時紀錄，活躍審閱合計 {summary['recorded_active_review_seconds']/60:.1f} 分鐘，紀錄基準為 {summary['recorded_baseline_review_seconds']/60:.1f} 分鐘。活躍工時不含等待；這是合成欄位的演練，不能當作實測效率提升。",
            f"其中 {summary['comparable_followup_cases']} 筆通過成熟度、任務與至少 95% 覆蓋檢查，可作描述性前後比較。窗口結束本身不代表可比；真實客戶採用、真實節油及公司成效仍未觀測。"],"figures":[figures[6]]}
    ]
    for section in sections:
        for figure in section.get("figures",[]):
            section["text"].extend(figure.get("findings",[]))
    result={"project_id":"DA-E01","report_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),
            "default_view":"revised","source_note":SOURCE_NOTE,"summary":_safe(summary),"sections":sections,
            "figures":figures,"dashboard":"outputs/dashboard.html","detail_csv":"outputs/report_weekly_detail.csv",
            "review_candidates_csv":"outputs/review_candidates.csv",
            "limitations":["Synthetic operational scenarios do not establish real fleet effectiveness.",
                           "Retrospective public prices are not historical availability evidence.",
                           "Review flags are descriptive rules and require investigation.",
                           "Before/after action comparisons do not identify causal savings."]}
    (root/"outputs/report_content.json").write_text(json.dumps(_safe(result),ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    _write_walkthrough(root,result)
    _write_notebook(root)
    return result


def _write_walkthrough(root: Path, result: dict):
    s=result["summary"]
    lines=["# DA-E01 圖表講解與分析重點","", "資料性質：合成車隊營運資料；公開 EIA 價格只作符合口徑的事後背景。", "",
           "## 開場說明", "", f"這個專案先把購油、ECU 耗用與油箱存量分開，再在共同有效區間比較效率。本版涵蓋 {s['tenant_count']} 個合成租戶與 {s['vehicle_count']} 輛車，修訂版車隊效率為 {s['fleet_mpg']:.2f} MPG，配對時間覆蓋率為 {s['paired_time_coverage']:.1%}。這些數值只代表本次模擬資料。", ""]
    for i,f in enumerate(result["figures"],1):
        lines += [f"## {i}. {f['title']}","",f"![{f['title']}](../{f['path']})","",f["interpretation"],"",*f.get("findings",[]),"",f"計算與限制：{f['caption']}","", "口述時先指出問題與分母，再說明圖中的差異、資料可信度及下一個可行查核。不要將旗標描述成已驗證原因。",""]
    lines += ["## 互動操作","", "開啟 `outputs/dashboard.html`，切換單一報告版本，再篩選租戶、車輛、週與覆蓋狀態。下載選取明細後，利用 output_id 與原資料庫中的報告版本回查。庫存依窗口篩選；措施圖依租戶與車輛顯示全期案例，圖中有明示。", "",
              "## 面試說明重點","", "- 為什麼不能把購油量直接當耗用？油箱存量、移動與交易跨期會使兩者不同。", "- 為什麼車隊 MPG 不平均各車 MPG？比率平均會讓不同里程與耗油量得到錯誤權重。", "- 為什麼保留三種版本？初版與修訂版重現當時可知資訊，事後背景則明示新增的歷史資料。", "- 為什麼沒有宣稱節省？目前只有合成演練，前後變化也可能來自任務或資料覆蓋差異。",""]
    (root/"docs/chart_walkthrough_zh.md").write_text("\n".join(lines))
    en=["# Fleet fuel efficiency and price variance","", "DA-E01 separates ECU fuel use, fuel purchases and inventory movements, then builds traceable vehicle-week metrics and reporting review candidates.","",
        f"The revised dataset covers {s['tenant_count']} synthetic tenants and {s['vehicle_count']} vehicles. It contains {s['vehicle_week_rows']:,} vehicle-week rows, {s['paired_distance_km']:,.0f} paired kilometres and {s['fuel_used_l']:,.0f} litres of paired consumption. Fleet efficiency is {s['fleet_mpg']:.2f} MPG with {s['paired_time_coverage']:.1%} paired-time coverage.","",
        "The workflow includes versioned input snapshots, temporal entity relationships, counter segmentation, independent reconciliation, SQL/Python analytics and an offline interactive report. Review thresholds identify cases for investigation; they do not prove waste or maintenance faults.","",
        "Official EIA observations are retrospective background where available. All vehicle operations and action-follow-up records are synthetic, and no real customer adoption or realized savings are claimed.","",
        "Outputs: [interactive report](../outputs/dashboard.html), [metric definitions](metrics.md), [Chinese chart walkthrough](chart_walkthrough_zh.md), [structured report](../outputs/report_content.json).",""]
    (root/"docs/portfolio_summary_en.md").write_text("\n".join(en))


def _write_notebook(root:Path):
    import nbformat
    (root/"notebooks").mkdir(parents=True,exist_ok=True)
    nb=nbformat.v4.new_notebook()
    nb.cells=[
        nbformat.v4.new_markdown_cell("# DA-E01 fuel analysis walkthrough\n\nThis notebook reads the built analytical database. Run the documented build pipeline first. Fleet operations are synthetic; no realized savings are claimed."),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport duckdb\nroot = Path.cwd()\nif root.name == 'notebooks': root = root.parent\ncon = duckdb.connect(str(root / 'data/DA-E01.duckdb'), read_only=True)\ncon.execute(\"SET TimeZone='UTC'\")"),
        nbformat.v4.new_markdown_cell("## 1. Inspect report versions\n\nKeep initial, revised and retrospective results separate. Each output_id points to a cutoff and source snapshot."),
        nbformat.v4.new_code_cell("con.sql(\"SELECT tenant_id, output_id, report_week_start, as_of_time FROM normalized.fuel_report_run ORDER BY tenant_id, report_week_start LIMIT 12\").df()"),
        nbformat.v4.new_markdown_cell("## 2. Recalculate the fleet ratio\n\nUse total distance and total consumption from the same accepted intervals, not the arithmetic mean of vehicle MPG."),
        nbformat.v4.new_code_cell("con.sql(\"\"\"SELECT SUM(distance_travelled_km) paired_km, SUM(fuel_used_l) paired_l, SUM(distance_travelled_km)/NULLIF(SUM(fuel_used_l),0)*3.785411784/1.609344 fleet_mpg, SUM(valid_paired_seconds)/NULLIF(SUM(expected_observation_seconds),0) coverage FROM normalized.fuel_weekly_metric WHERE output_id LIKE '%-revised'\"\"\").df()"),
        nbformat.v4.new_markdown_cell("## 3. Inspect exclusions before interpreting anomalies\n\nRejected intervals remain visible. A missing or invalid interval is not zero fuel consumption."),
        nbformat.v4.new_code_cell("con.sql(\"SELECT accepted, excluded_interval_reason, COUNT(*) n FROM normalized.fuel_paired_interval GROUP BY ALL ORDER BY n DESC\").df()"),
        nbformat.v4.new_markdown_cell("## 4. Compare like tasks\n\n**Why:** mixed task weeks can hide operating differences. **Data:** task-specific accepted intervals, vehicle class and expected task time. **How:** compare each vehicle/task with its previous week and with other vehicles in the same tenant, class, task and week. **Interpretation:** at least three peers and 95% coverage are needed for the peer review rule. A difference still requires load, PTO and route investigation."),
        nbformat.v4.new_code_cell("con.sql(\"\"\"SELECT tenant_id,vehicle_id,vehicle_class,report_week_start,task_type,l_per_100km,prior_l_per_100km,peer_median_l_per_100km,peer_count,measurement_coverage,comparison_status,review_flag FROM analytics.efficiency_comparison WHERE report_view='revised' ORDER BY (review_flag='review_load_pto_route') DESC,vehicle_id,report_week_start LIMIT 25\"\"\").df()"),
        nbformat.v4.new_markdown_cell("## 5. Reconcile purchase spend without calling it fuel use\n\n**Why:** a purchase fills stock; it need not be consumed in that week. **Data:** net fuel-only transaction amounts and quantities, including eligible credits. **How:** inspect weekly quantities and price/quantity effects. **Interpretation:** unmatched cohort changes remain a residual; market gaps are comparisons, not realizable savings."),
        nbformat.v4.new_code_cell("con.sql(\"\"\"SELECT report_week_start, SUM(purchase_quantity_l) purchased_l, SUM(comparable_fuel_amount) purchase_usd, SUM(purchase_price_effect) price_effect_usd, SUM(purchase_quantity_effect) quantity_effect_usd FROM analytics.fleet_weekly WHERE report_view='revised' GROUP BY report_week_start ORDER BY report_week_start DESC LIMIT 8\"\"\").df()"),
        nbformat.v4.new_markdown_cell("## 6. Cross-check ECU use against tank balance\n\n**Why:** two measurement paths can disagree. **Data:** common tank-window boundaries, recorded refills/transfers/removals and accepted ECU intervals. **How:** inspect residual and stated uncertainty, together with evidence state. **Interpretation:** a residual outside uncertainty calls for coverage or movement checks; it does not prove theft or waste."),
        nbformat.v4.new_code_cell("con.sql(\"\"\"SELECT tenant_id,vehicle_id,period_start_at,period_end_at,balance_consumption_l,ecu_fuel_l,ecu_minus_inventory_l,uncertainty_l,reconciliation_status FROM analytics.inventory_reconciliation ORDER BY ABS(ecu_minus_inventory_l) DESC NULLS LAST LIMIT 15\"\"\").df()"),
        nbformat.v4.new_markdown_cell("## 7. Change a reporting threshold\n\nCompare the number of rows eligible for interpretation at 90% and 95% coverage. This changes review eligibility, not the underlying measurements."),
        nbformat.v4.new_code_cell("for threshold in [0.90, 0.95]:\n    result = con.execute(\"SELECT COUNT(*) FROM normalized.fuel_weekly_metric WHERE output_id LIKE '%-revised' AND measurement_coverage >= ?\", [threshold]).fetchall()[0][0]\n    print(threshold, result)"),
        nbformat.v4.new_markdown_cell("## 8. Follow the report into action records\n\n**Why:** producing a report is different from its adoption. **Data:** report receipt/review records, actions and independent observation windows. **How:** recompute baseline/follow-up fuel and distance from accepted intervals. **Interpretation:** maturity, exposure, coverage and task comparability gate the descriptive change. Follow-up task rates are also standardized using baseline task distance shares. A before/after comparison is not a causal estimate."),
        nbformat.v4.new_code_cell("con.sql(\"SELECT adoption_status, review_outcome, COUNT(*) cases FROM normalized.fuel_output_review GROUP BY ALL ORDER BY cases DESC\").df()"),
        nbformat.v4.new_code_cell("con.sql(\"\"\"SELECT review_case_id,vehicle_id,adoption_status,comparison_status,baseline_coverage,followup_coverage,baseline_l_per_100km,followup_l_per_100km,change_l_per_100km,standardized_followup_l_per_100km,standardized_change_l_per_100km FROM analytics.followup_evaluation ORDER BY review_case_id\"\"\").df()"),
        nbformat.v4.new_markdown_cell("## 9. Read the generated evidence\n\nThese figures use the same database values as the offline dashboard and written report. Open the dashboard to filter one report view at a time. The source data represent a synthetic portfolio exercise, with separately identified public price background."),
        nbformat.v4.new_code_cell("from IPython.display import Image, display\ndisplay(Image(filename=str(root / 'outputs/figures/06_review_priority.png')))\ndisplay(Image(filename=str(root / 'outputs/figures/07_action_followup.png')))"),
        nbformat.v4.new_code_cell("con.close()")]
    nb.metadata={"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python"}}
    nbformat.write(nb,root/"notebooks/01_fuel_analysis.ipynb")


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path.cwd());args=p.parse_args()
    print(json.dumps(report(args.root)["summary"],ensure_ascii=False,indent=2))
