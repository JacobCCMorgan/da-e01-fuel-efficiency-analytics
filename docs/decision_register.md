# Implementation decisions and deferred scope

This register reconciles the DA-E01 implementation with the accepted source and scope decisions. It was recorded during release review; the frozen baseline files remain unchanged. The structured record is [implementation_decisions.json](../contracts/implementation_decisions.json).

**Disposition:** 2 DA-E01 questions resolved for v1; 16 questions retained for later projects; 3 shared-definition decisions. The other 39 cataloged projects remain unexpanded. No later project starts automatically.

## Shared seed rule: WEATHER-002 / WEATHER-003

These references identify **S23-PKG-WEATHER-002** (DS-E01 synthetic weather) and **S23-PKG-WEATHER-003** (optional DS-M01 synthetic forecasts), not similarly numbered evidence records. Their old 8-byte instructions conflict with the accepted global 128-bit rule. The JSON retains the exact old text and frozen source identity.

| Package | Original instruction | Execution disposition |
|---|---|---|
| S23-PKG-WEATHER-002 | `SHA256("20261021\|weather_field\|v1")取前8bytes轉uint64；不得用語言內建hash` | First 16 SHA256 bytes, unsigned big-endian; weather generation deferred. |
| S23-PKG-WEATHER-003 | `SHA256("20261021\|eta_forecast\|v1")前8bytes uint64` | First 16 SHA256 bytes, unsigned big-endian; weather generation deferred. |

DA-E01 already uses UTF-8 tokens separated by U+001F and a 16-byte prefix. `trip` and `physics` use stable trip IDs. Generator version 1.0.0 and config freeze the current grammar; the version is recorded externally, not claimed to be an extra hashed token. A changed grammar, algorithm or version requires a new dataset version and replay comparison. This record does not alter generated data.

**Width-only vectors** keep the legacy pipe-separated bytes unchanged and isolate the 8-byte → 16-byte correction.

| Legacy key | Old uint64 | Corrected-width uint128 |
|---|---|---|
| `20261021\|weather_field\|v1` | 2399850739894360960 | 44269432413933785659689547793188947507 |
| `20261021\|eta_forecast\|v1` | 11110930881638544203 | 204960498394262258769924241784648519219 |

**Current encoder vectors** use the actual `sub_seed` function. Weather-labelled vectors test encoding only; they do not create weather data or forecasts.

| Tokens after master seed 20261021 | UTF-8 bytes (hex) | Actual uint128 |
|---|---|---|
| `trip`, `T01-V01-TR001` | `32303236313032311f747269701f5430312d5630312d5452303031` | 45315173385107991413193837980978084803 |
| `physics`, `T01-V01-TR001` | `32303236313032311f706879736963731f5430312d5630312d5452303031` | 56555512423673698005097336676557723775 |
| `weather_field`, `v1` | `32303236313032311f776561746865725f6669656c641f7631` | 6635490931900012547853576854177117584 |
| `eta_forecast`, `v1` | `32303236313032311f6574615f666f7265636173741f7631` | 297823811902032038899646802291833577546 |

All four vectors were checked against an independent SHA256 byte calculation. `tests/test_simulation.py` also checks the trip vector; the [clean-rebuild report](../validation/rebuild_report.json) verifies identical source bytes and logical tables under frozen config. Large integers are decimal strings in JSON to avoid JavaScript precision loss.

## Other accepted shared definitions

| Decision | Meaning | Scope and next action |
|---|---|---|
| DA-E01-M0-002 / S23-CHG-WEATHER-001 | `grid_id` keeps `S22-F-7EFB048C7F64`; future identity includes source/product/version. Synthetic locations are not real NWS grids. | DS-M01 implementation deferred; test qualified grid and as-of semantics upon activation. |
| DA-E01-M0-003 / S23-CP-SUP-001 | `generator_version` keeps `S22-F-6568412EC7DF`; it identifies the actual draft component. Retrieval-only uses NULL/not_applicable. | DS-M05 deferred; a local extractive/template draft is distinct from an executed language model. |

## All 18 baseline questions

Every row preserves the original question ID and project. Reusable DA-E01 evidence does not complete a later project. The structured record retains the original source/evidence references as well.

| Question ID | Project | Disposition | Next project or gate |
|---|---|---|---|
| S23-OQ-001 | DA-E01 | Resolved for DA-E01 v1 | DA-E01 v1 acceptance |
| S23-OQ-002 | DA-E01 | Resolved for DA-E01 v1 | DA-E01 v1 acceptance |
| S23-OQ-003 | DS-E01 | Deferred; project not started | DS-E01 |
| S23-OQ-004 | DS-E01 | Deferred; project not started | DS-E01 |
| S23-OQ-005 | DA-E02 | Deferred; project not started | DA-E02 |
| S23-OQ-006 | DA-E02 | Deferred; project not started | DA-E02 |
| S23-OQ-007 | DE-E01 | Deferred; project not started | DE-E01 |
| S23-OQ-008 | DE-E01 | Deferred; project not started | DE-E01 |
| S23-OQ-009 | DE-E03 | Deferred; project not started | DE-E03 |
| S23-OQ-010 | DE-E03 | Deferred; project not started | DE-E03 |
| S23-OQ-011 | DE-M02 | Deferred; project not started | DE-M02 |
| S23-OQ-012 | DE-M02 | Deferred; project not started | DE-M02 |
| S23-OQ-013 | DS-M01 | Deferred; project not started | DS-M01 |
| S23-OQ-014 | DS-M01 | Deferred; project not started | DS-M01 |
| S23-OQ-015 | DS-M01 | Deferred; project not started | DS-M01 |
| S23-OQ-016 | DS-M05 | Deferred; project not started | DS-M05 |
| S23-OQ-017 | DS-M05 | Deferred; project not started | DS-M05 |
| S23-OQ-018 | DS-M05 | Deferred; project not started | DS-M05 |

### S23-OQ-001 · DA-E01

公開價格/氣象快照能否符合期間、授權與重現要求？

Public EIA prices are frozen: 62 observations from 2024-12-02 to 2025-06-30, including 52 Jan–Jun observations across two series. Original files, receipts, rights notes and hashes are retained. Historical release times remain unknown, so public prices enter retrospective context only. Optional weather is not activated for DA-E01; no full-period weather coverage is claimed.

**Owner:** Data analyst / project maintainer. **Stage:** DA-E01 S2.4/S3 complete; v1 review pending.

**Evidence:** `data/public/source_manifest.json`; `docs/sources.md`; `src/fleet_fuel/public_normalization.py`; `tests/test_public_normalization.py`.

**Next action — DA-E01 v1 acceptance:** Accept retrospective-only price interpretation at v1 review. A later weather extension needs its own coverage, rights and version assessment; it is not a missing prerequisite.

### S23-OQ-002 · DA-E01

初版情境範圍與樣本規模是否需要擴增？

Keep the accepted Jan–Jun 2025 scope: 3 tenants, 30 vehicles, 36 devices, 45 drivers and 1,800 trips. The fixed 100-trip smoke subset, full run, boundary cases, independent controls and parameter change checks execute. No scale increase is required for v1; simulated scale is not evidence of real-world efficacy.

**Owner:** Data analyst / project maintainer. **Stage:** DA-E01 S2.4/S3 complete; v1 review pending.

**Evidence:** `config/project.json`; `data/generation_manifest.json`; `contracts/scenario_registry.json`; `validation/rebuild_report.json`.

**Next action — DA-E01 v1 acceptance:** Retain the fixed scope at v1 review; add later scenario or scale versions only for a specific coverage/performance question while preserving prior IDs.

### S23-OQ-003 · DS-E01

公開價格/氣象快照能否符合期間、授權與重現要求？

Retain the source policy. DA-E01 EIA acquisition is reusable context, but DS-E01 weather matching and full-period coverage are not implemented.

**Owner:** Data scientist / project maintainer. **Stage:** DS-E01 S2.4 source coverage; S3 feature evaluation.

**Evidence:** `data/public/source_manifest.json`; `docs/sources.md`.

**Next action — DS-E01:** Verify rights, station/month coverage, QC and as-of availability for DS-E01; otherwise use explicitly synthetic weather or disable that optional context.

### S23-OQ-004 · DS-E01

初版情境範圍與樣本規模是否需要擴增？

Preserve the common scale. Reusable DA-E01 simulation does not validate a DS-E01 daily target, normal baseline, model split or waste classifier.

**Owner:** Data scientist / project maintainer. **Stage:** DS-E01 S2.4 fixtures; S3 sensitivity.

**Evidence:** `config/project.json`; `validation/rebuild_report.json`.

**Next action — DS-E01:** Define target observability, load/PTO/normal cases, chronological splits and independent labels before deciding whether larger samples are needed.

### S23-OQ-005 · DA-E02

實際公開資料是否足以補充來源格式或部分事件範例？

Synthetic device, deployment and work-order data remain the sufficient DA-E02 route. No complete DA-E02 online-state or support dataset is claimed.

**Owner:** Data analyst / project maintainer. **Stage:** DA-E02 S2.4 dedicated data and source review.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DA-E02:** Build DA-E02-specific events and tickets; add official format examples only after checking rights, versions and applicability, separate from simulated identities.

### S23-OQ-006 · DA-E02

示範用回報策略與品質門檻是否適合展示？

Reporting policies and physical thresholds remain versioned design assumptions. A 60-second GNSS assumption is not an externally verified device standard; fuel-counter checks do not resolve DA-E02 online-state semantics.

**Owner:** Data analyst / project maintainer. **Stage:** DA-E02 S2.4 policy fixtures; S3 sensitivity.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DA-E02:** Define expected online intervals, device/engine states and sampling policies; retain uncertain physical limits as research settings and measure sensitivity.

### S23-OQ-007 · DE-E01

實際公開資料是否足以補充來源格式或部分事件範例？

The DA-E01 HTTP envelope and receipt log are reusable components only. DE-E01 multi-format/version normalization outputs remain unimplemented.

**Owner:** Data engineer / project maintainer. **Stage:** DE-E01 S2.4 dedicated format fixtures.

**Evidence:** `docs/api_contract.md`; `src/fleet_fuel/ingestion.py`.

**Next action — DE-E01:** Implement DE-E01 decoded JSONL v1/v2 mappings, parser failures and correction history. Add official examples only after verification; do not claim vehicle-protocol certification.

### S23-OQ-008 · DE-E01

示範用回報策略與品質門檻是否適合展示？

Structural, key, time and unit tests are reusable; DE-E01 reporting policies and physical limits remain subject to its own source contract.

**Owner:** Data engineer / project maintainer. **Stage:** DE-E01 S2.4 policy/config; S3 sensitivity.

**Evidence:** `tests/test_ingestion.py`; `tests/test_normalization.py`.

**Next action — DE-E01:** Freeze per-format policies and failure cases; describe uncertain physical thresholds as research settings, not vehicle standards.

### S23-OQ-009 · DE-E03

實際公開資料是否足以補充來源格式或部分事件範例？

DA-E01 receipt reconciliation is not the complete DE-E03 daily-quality project. Optional public examples remain subject to source verification.

**Owner:** Data engineer / project maintainer. **Stage:** DE-E03 S2.4 independent daily controls.

**Evidence:** `validation/ingestion_report.json`; `validation/quality_report.json`.

**Next action — DE-E03:** Build independent input/receipt/output daily control totals and quarantine balances for missing, late, repeated and corrected records.

### S23-OQ-010 · DE-E03

示範用回報策略與品質門檻是否適合展示？

Keep reporting assumptions explicit and unverified physical limits pending. DE-E03-specific threshold calibration has not occurred.

**Owner:** Data engineer / project maintainer. **Stage:** DE-E03 S2.4 config; S3 sensitivity.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DE-E03:** Define expected windows, completeness denominators and thresholds; evaluate policy sensitivity without presenting unverified limits as industry rules.

### S23-OQ-011 · DE-M02

實際公開資料是否足以補充來源格式或部分事件範例？

DA-E01 vehicle-device history supports fuel attribution, including ambiguity. Complete DE-M02 tenant/vehicle/device/driver history and operational data products remain deferred.

**Owner:** Data engineer / project maintainer. **Stage:** DE-M02 S2.4 dedicated history model.

**Evidence:** `contracts/da_e01_contract.json`; `tests/test_analysis.py#test_ambiguous_historical_assignment_is_excluded`.

**Next action — DE-M02:** Implement complete relationship history with independent swap, overlap and gap timelines when DE-M02 is explicitly activated; verify any optional public format.

### S23-OQ-012 · DE-M02

示範用回報策略與品質門檻是否適合展示？

Sampling assumptions do not define identity resolution. DA-E01 business/known-time checks are reusable, not completion of DE-M02.

**Owner:** Data engineer / project maintainer. **Stage:** DE-M02 S2.4 temporal keys and policies.

**Evidence:** `docs/metrics.md`; `tests/test_analysis.py#test_both_endpoints_require_valid_definition_period`.

**Next action — DE-M02:** Freeze unknown/overlap/gap policies and temporal keys against independent timelines; add observation policy only where DE-M02 requires it.

### S23-OQ-013 · DS-M01

候選公開資料是否有可再利用的歷史預報快照與當時可用證據？

Keep the no-forecast ETA baseline. Public forecasts remain disabled without historical issued/available/valid-time evidence. DA-E01 adds no forecast source.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M01 S2.4 forecast eligibility; S3 comparison.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DS-M01:** Implement no-forecast baseline first; activate synthetic or evidenced public forecast variants only with availability and leakage fixtures.

### S23-OQ-014 · DS-M01

路線背景資料及回應是否允許取得與 GitHub 再散布？

The shared 12 fictional facilities/routes exist for DA-E01. They are original simulation context, not commercial API responses; DS-M01 route-response modeling remains deferred.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M01 S2.4 route fixtures.

**Evidence:** `data/raw/operations/facilities.json`; `data/raw/operations/routes.json`; `src/fleet_fuel/simulation.py`.

**Next action — DS-M01:** Use the fictional route graph; review external routing terms before optional acquisition or redistribution and preserve true source labels.

### S23-OQ-015 · DS-M01

80% 覆蓋、30 分鐘提前量與通知容量是否適合示範敘事？

Retain 80% nominal interval coverage, 30-minute lead and 30-minute suppression as research settings. No ETA calibration or notification-capacity result is claimed.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M01 S3 calibration and held-out evaluation.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DS-M01:** Set finite notification capacity, tune on calibration data only, freeze before testing and report measured coverage/load with sensitivity.

### S23-OQ-016 · DS-M05

哪些官方公開內容可合法重製並具有可核對的版本有效資訊？

Knowledge-source reuse and historical validity remain DS-M05 work. DA-E01 has not obtained an ELD corpus; a current page does not establish its historical version.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M05 S2.4 corpus acquisition/versioning.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DS-M05:** Check each document and reuse condition; retain actual version evidence and supply clearly fictional product material for uncovered scenarios.

### S23-OQ-017 · DS-M05

首版是否加入生成模型與向量檢索？

Retain the accepted generator_version clarification. BM25, drafts, vector retrieval and optional models have not been implemented as DS-M05 outcomes here.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M05 S2.4 index/data; S3 draft/model evaluation.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DS-M05:** Implement BM25 plus local evidence-backed drafts and claim-level evaluation as the self-contained route; compare optional models on the same frozen set.

### S23-OQ-018 · DS-M05

是否有真正獨立的人類專家覆核與客服試用？

No external expert or real support trial is required to execute the demonstration, and neither is claimed. DA-E01 synthetic reviews do not resolve independent RAG evaluation.

**Owner:** Data scientist / project maintainer. **Stage:** DS-M05 S3 independent answer evaluation.

**Evidence:** Accepted source/scope decision only; no project-specific execution evidence claimed..

**Next action — DS-M05:** Create evidence-grounded answers, adversarial cases and disagreement records. Mark adoption/time trials synthetic unless actual independently documented trials occur.

## Frozen source identity

| Source | SHA256 |
|---|---|
| open_questions.json | `84a60abe058eb29485a4e508c00e19eeb7ba4b9ea23871750a4809cecba55df2` |
| s23_source_decisions.json | `5596e91e7d2db98c0dc1049d5de68cefac3cdfc5da7de0181419f74faf78262e` |
| S2_4_DA_E01_Execution_Instructions_v2_20261023_REVIEW.txt | `6f7190f193c16c6afb7a1cda4203c8e2beada9dc6aa6f273840bcb844f5e7917` |

The baseline files were not modified. DA-E01 preserves 26 canonical tables, 330 fields, 153 original requirements and O01/O02/O03. Retaining shared definitions does not authorize or complete the seven later first-batch projects; the remaining 39 Project IDs stay deferred in the business-topic catalog.

After DA-E01 v1 acceptance, the scheduled order is DE-M02 → DE-E01 → DE-E03 → DA-E02 → DS-E01 → DS-M01 → DS-M05, subject to explicit activation.
