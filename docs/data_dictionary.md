# DA-E01 data dictionary

This dictionary is exported from the versioned contract. The CSV preserves every field attribute, including Chinese labels, null conditions, units, time availability and original requirement IDs.

The 26 canonical tables contain 330 fields and support 153 original field requirements. Operational helper tables and raw HTTP receipts are separate from this contract.

## Data layers

| Table | Grain | Layer | Source plan | Key |
|---|---|---|---|---|
| core_tenant | 每個模擬租戶 | master | synthetic | tenant_id |
| core_vehicle | 每租戶每個物理車輛 | master | synthetic | tenant_id, vehicle_id |
| core_device | 每租戶每個物理裝置 | master | synthetic | tenant_id, device_id |
| core_vehicle_device_assignment | 每租戶每段業務關係的每個系統可知版本 | relationship | synthetic | tenant_id, assignment_id |
| provenance_record | 每個canonical資料列版本；可共同指向同一來源紀錄 | provenance | synthetic | provenance_id |
| fuel_vehicle_context | 租戶及車輛的一個情境版本 | source | synthetic | tenant_id, vehicle_context_id |
| fuel_task_assignment | 車輛參與任務的一個有效期間及版本 | source | synthetic | tenant_id, task_assignment_id |
| fuel_signal_definition | 來源 ECU 配置及訊號種類的一個解碼版本 | source | synthetic | tenant_id, signal_definition_id |
| fuel_counter_observation | 來源傳輸紀錄中的一組可部分缺失讀值；燃料與里程各自有量測時間 | source | synthetic | tenant_id, counter_observation_id |
| fuel_counter_change | 指定車輛 ECU 訊號的一次重置回捲或未知跳變 | source | synthetic | tenant_id, counter_change_id |
| fuel_purchase_line | 一筆交易明細的一個版本；純金額調整仍獨立明細 | source | synthetic | tenant_id, purchase_line_id, line_version |
| fuel_card_assignment | 一張代碼化油卡與車輛的一段有效關係 | source | synthetic | tenant_id, card_assignment_id |
| fuel_station | 一個購油站點版本 | source | synthetic | tenant_id, station_version_id |
| fuel_market_price | 價格系列及觀測日期的一個發布版本 | source | mixed | tenant_id, market_price_version_id |
| fuel_region_mapping | 國家州別與不重疊市場地區的一個映射版本 | source | synthetic | tenant_id, region_mapping_id |
| fuel_tank_scope | 車輛油箱或雙油箱群的一個範圍版本 | source | synthetic | tenant_id, tank_scope_version_id |
| fuel_inventory_measurement | 同一油箱範圍的一次實際量測及版本 | source | synthetic | tenant_id, inventory_measurement_id |
| fuel_movement | 同一憑證的一次燃料移動 | source | synthetic | tenant_id, fuel_movement_id |
| fuel_inventory_balance | 同油箱範圍及兩個量測邊界的一次平衡計算 | derived | derived | tenant_id, balance_id |
| fuel_statement_control | 帳單版本及分類燃料類型幣別單位的控制總數 | validation | synthetic | tenant_id, statement_control_id |
| fuel_reference_case | 一個覆核案例與核對指標的一個答案版本 | validation | synthetic | tenant_id, reference_case_id, reference_metric |
| fuel_output_review | 專案發布成果中的一個車輛週或車輛日調查案例 | source | synthetic | tenant_id, review_case_id |
| fuel_action_followup | 一項措施在指定比較與追蹤窗口的一個觀察版本 | source | synthetic | tenant_id, action_followup_id |
| fuel_report_run | 一次週報執行與輸入版本快照 | configuration | synthetic | tenant_id, output_id |
| fuel_paired_interval | 同車燃油段與距離段交集內可歸屬的區間 | derived | derived | tenant_id, paired_interval_id |
| fuel_weekly_metric | 報告執行及車輛與任務比較組的一列週指標 | derived | derived | tenant_id, weekly_metric_id |

## core_tenant

租戶主檔；以每個模擬租戶支援DA-E01, DA-E02, DE-E01, DE-E03, DE-M02, DS-E01, DS-M01, DS-M05的追溯用途

**History:** 不可變的初始實體登錄，主鍵一列。此處屬性為初始值；後續屬性更正與歷史變化存各領域版本/證據表，不覆寫本列。租戶時區與幣別為第一版固定情境設定。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 初始生成一次；新增實體時追加

**References:** []

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-45D1EDD42E5B | tenant_id | 租戶識別 | VARCHAR | 無 | 不可為 NULL | 所有業務實體的隔離範圍；每個模擬租戶使用獨立 ID 命名空間 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-1A2B977841E1 | tenant_name | 租戶顯示名 | VARCHAR | 無 | 不可為 NULL | 明確虛構的展示名稱，不使用真實客戶名稱 符合定義與型別 |
| S22-F-453FB0E50CE7 | report_timezone | 報表時區 | VARCHAR | 無 | 不可為 NULL | 依 IANA tzdb 解釋營運日與週；保留版本 America/Los_Angeles 等 IANA 識別 |
| S22-F-4D7362DF0993 | base_currency | 報表幣別 | VARCHAR | 無 | 不可為 NULL | 第一版 USD；交易原幣別另外保存 ISO 4217 三字碼 |

## core_vehicle

車輛穩定主檔；以每租戶每個物理車輛支援DA-E01, DA-E02, DE-E01, DE-E03, DE-M02, DS-E01, DS-M01的追溯用途

**History:** 不可變的初始實體登錄，主鍵一列。此處屬性為初始值；後續屬性更正與歷史變化存各領域版本/證據表，不覆寫本列。租戶時區與幣別為第一版固定情境設定。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 初始生成一次；新增實體時追加

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "同一租戶；所需版本在使用時點已可知"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-95C87E536E83 | tenant_id | 租戶識別 | VARCHAR | 無 | 不可為 NULL | 所有業務實體的隔離範圍；每個模擬租戶使用獨立 ID 命名空間 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-8562703BF1D4 | vehicle_id | 車輛識別 | VARCHAR | 無 | 不可為 NULL | 物理車輛穩定鍵；換裝置不換車輛鍵 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-A88624F76AB8 | vin_raw | 來源 VIN | VARCHAR | 無 | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 來源 VIN 原值或明示為合成的測試 VIN；不能從模擬 VIN 假稱真車規格 符合定義與型別 |
| S22-F-ED6084644583 | vin | 標準化 VIN | VARCHAR | 無 | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 從 vin_raw 去首尾空白並轉大寫；保留原值與檢查結果 符合定義與型別 |
| S22-F-4C52A1423130 | vehicle_class | 車輛分類 | VARCHAR | 無 | 不可為 NULL | 示範重型/中型商用車分類；具體規格版本由領域情境表保存 heavy_truck / medium_truck / bus / unknown |
| S22-F-FB42B6B92049 | fuel_type | 燃料種類 | VARCHAR | 無 | 不可為 NULL | 第一版柴油案例；其他燃料不可直接沿用柴油換算 diesel / gasoline / electric / other / unknown |

## core_device

裝置穩定主檔；以每租戶每個物理裝置支援DA-E01, DA-E02, DE-E01, DE-E03, DE-M02, DS-E01, DS-M01的追溯用途

**History:** 不可變的初始實體登錄，主鍵一列。此處屬性為初始值；後續屬性更正與歷史變化存各領域版本/證據表，不覆寫本列。租戶時區與幣別為第一版固定情境設定。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 初始生成一次；新增實體時追加

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "同一租戶；所需版本在使用時點已可知"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-310CAED2B271 | tenant_id | 租戶識別 | VARCHAR | 無 | 不可為 NULL | 所有業務實體的隔離範圍；每個模擬租戶使用獨立 ID 命名空間 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-82C828361885 | device_id | 裝置識別 | VARCHAR | 無 | 不可為 NULL | 裝置物理鍵，移機不換鍵 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-71B855147978 | device_model | 裝置型號 | VARCHAR | 無 | 不可為 NULL | 示範型號代碼；不暗示真實硬體支援全部訊號 符合定義與型別 |

## core_vehicle_device_assignment

車輛裝置歷史關聯；以每租戶每段業務關係的每個系統可知版本支援DA-E01, DA-E02, DE-E01, DE-E03, DE-M02, DS-E01, DS-M01的追溯用途

**History:** 穩定主鍵不重用；業務有效期間與系統可知期間分開，採 [from,to) 半開區間

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 變更時新增版本；日快照可重建

**References:** [{"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "同一租戶；所需版本在使用時點已可知"}, {"columns": ["tenant_id", "device_id"], "ref_table": "core_device", "ref_columns": ["tenant_id", "device_id"], "condition": "同一租戶；所需版本在使用時點已可知"}, {"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "同一租戶；所需版本在使用時點已可知"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-77515B00705E | tenant_id | 租戶識別 | VARCHAR | 無 | 不可為 NULL | 所有業務實體的隔離範圍；每個模擬租戶使用獨立 ID 命名空間 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-AEE74B32050F | assignment_id | 關聯版本識別 | VARCHAR | 無 | 不可為 NULL | 每次關係修訂的不可變 ID 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-6AE835C52A3A | vehicle_id | 車輛識別 | VARCHAR | 無 | 不可為 NULL | 被關聯的車輛 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-AA7DDE13DF5C | device_id | 裝置識別 | VARCHAR | 無 | 不可為 NULL | 關聯實體的穩定鍵 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-954C16C9FE56 | valid_from | 業務生效時間 | TIMESTAMPTZ | UTC | 不可為 NULL | 實際關係開始時點 ISO 8601；from < to；保留原始 offset |
| S22-F-0F0C4C0B3A18 | valid_to | 業務失效時間 | TIMESTAMPTZ | UTC | NULL 只在相應 *_state 為 open 或 unknown 時允許；open 可作無限終點，unknown 不可作無限延伸 | 實際關係結束，右端不包含；NULL 僅表示開放終點 ISO 8601；from < to；保留原始 offset |
| S22-F-7C5FC615F989 | known_from | 可知開始時間 | TIMESTAMPTZ | UTC | 不可為 NULL | 此版本首次被系統知道的時點 ISO 8601；from < to；保留原始 offset |
| S22-F-F83C688D7460 | known_to | 可知結束時間 | TIMESTAMPTZ | UTC | NULL 只在相應 *_state 為 open 或 unknown 時允許；open 可作無限終點，unknown 不可作無限延伸 | 此版本被後續版本取代時點；NULL 表示現行可知版本 ISO 8601；from < to；保留原始 offset |
| S22-F-F86FE75B2233 | valid_to_state | 業務終點狀態 | VARCHAR | 無 | 不可為 NULL | 已知終點、開放終點及未知終點明確區別 known / open / unknown |
| S22-F-124F9677EB46 | known_to_state | 系統終點狀態 | VARCHAR | 無 | 不可為 NULL | 已知取代時間、現行版本及未知狀態明確區別 known / open / unknown |
| S22-F-EF7FE451C01F | resolution_status | 關聯解析狀態 | VARCHAR | 無 | 不可為 NULL | 明確、未知、衝突及待裁定分開 resolved / unknown / ambiguous / withdrawn |
| S22-F-511BAD2D91D1 | provenance_id | 來源追溯識別 | VARCHAR | 無 | 不可為 NULL | 指向本紀錄及版本的來源、取得與合成脈絡 非空穩定識別；不得依顯示名稱或列順序臨時重編 |

## provenance_record

紀錄版本與來源追溯；以每個canonical資料列版本；可共同指向同一來源紀錄支援DA-E01, DA-E02, DE-E01, DE-E03, DE-M02, DS-E01, DS-M01, DS-M05的追溯用途

**History:** 穩定主鍵不重用；業務有效期間與系統可知期間分開，採 [from,to) 半開區間

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 變更時新增版本；日快照可重建

**References:** [{"columns": ["source_dataset_id"], "ref_table": "source_dataset", "ref_columns": ["source_dataset_id"], "condition": "同一租戶；所需版本在使用時點已可知"}, {"columns": ["synthetic_scenario_id"], "ref_table": "synthetic_scenario", "ref_columns": ["synthetic_scenario_id"], "condition": "同一租戶；所需版本在使用時點已可知"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "同一租戶；所需版本在使用時點已可知"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-8A1C6E23714C | provenance_id | 追溯識別 | VARCHAR | 無 | 不可為 NULL | 每個來源記錄版本的全域唯一鍵 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-A348705C222D | source_system_id | 來源系統識別 | VARCHAR | 無 | 不可為 NULL | 原件所屬系統；同值 source_record_id 跨系統不可合併 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-960E7EDEE887 | source_record_id | 來源紀錄識別 | VARCHAR | 無 | 不可為 NULL | 原生 ID；無原生鍵時以原件雜湊與列位建立並註明生成方式 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-DC583E4FC62B | record_version | 來源修訂版本 | VARCHAR | 無 | 不可為 NULL | 來源或接收快照版本，保留撤回與更正歷史 符合定義與型別 |
| S22-F-1C4FD208A523 | record_state | 記錄有效狀態 | VARCHAR | 無 | 不可為 NULL | 來源版本生命週期 active / corrected / withdrawn / unknown |
| S22-F-23BECD962138 | event_time | 事件時間 | TIMESTAMPTZ | UTC | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 此追溯記錄對應事件時間；事件專用時間仍存領域表 符合定義與型別 |
| S22-F-0375996504DC | available_time | 首次可用時間 | TIMESTAMPTZ | UTC | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 此版本首次能被分析流程使用的時間，不可倒填取得日前的未知歷史 符合定義與型別 |
| S22-F-917735F0663F | retrieved_at | 實際取得時間 | TIMESTAMPTZ | UTC | 不可為 NULL | 下載或合成執行完成取得本批資料的時間 符合定義與型別 |
| S22-F-D492410C2B94 | extract_as_of | 匯出截止 | TIMESTAMPTZ | UTC | 不可為 NULL | 本次快照涵蓋截止，不代表之前事件全部到齊 符合定義與型別 |
| S22-F-8CE2A78B4755 | raw_record_reference | 原件定位 | VARCHAR | 無 | 不可為 NULL | 可定位 immutable 檔案相對路徑、雜湊與列號，或已保存 API 回應；不可含密鑰 符合定義與型別 |
| S22-F-580569DA4EE8 | origin_type | 來源性質 | VARCHAR | 無 | 不可為 NULL | 公開、合成、混合與衍生各自明示 public / synthetic / mixed / derived |
| S22-F-A4C0DA6F0ED9 | source_dataset_id | 資料集版本識別 | VARCHAR | 無 | 不可為 NULL | 指向取得或生成的不可變資料集版本 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-B53BA541B1C7 | synthetic_scenario_id | 合成情境識別 | VARCHAR | 無 | 純公開紀錄不適用可NULL；synthetic/mixed必填 | 純公開記錄為 NULL；合成與混合記錄必須可追溯生成情境 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-E782A9AFF2BC | value_states | 逐欄值狀態 | JSON | 無 | 不可為 NULL | 物件鍵為完整 table.column，值含 state 與 reason；缺失狀態不可代表觀察到零 {"table.column":{"state":"observed / missing / invalid / unknown / not_applicable / not_mature","reason":"text"}} |
| S22-F-7E83460332F3 | source_timezone | 來源時區 | VARCHAR | 無 | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 原件 IANA 時區；未知用NULL並在value_states標unknown，不能猜測 符合定義與型別 |
| S22-F-C39B69B88FCE | source_utc_offset_minutes | 來源 UTC 偏移 | INTEGER | minutes | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 原件時間所帶 UTC offset；DST重複時刻須有偏移或fold證據 -840..840 |
| S22-F-ADFA883A94CB | tenant_id | 業務租戶 | VARCHAR | 無 | 僅全域公開背景/共用設定可為NULL；業務資料必填並與引用資料列租戶一致 | 業務紀錄必填且需與引用此追溯的資料列租戶相同；公共背景來源可為NULL 非空穩定識別；不得依顯示名稱或列順序臨時重編 |
| S22-F-479764B18D5E | field_origins | 逐欄來源組成 | JSON | 無 | 不可為 NULL | 混合與衍生紀錄逐欄列出來源性質、資料集、原件或生成/計算依據；禁止混合欄位失去來源 {"table.column":{"origin_type":"public / synthetic / derived","source_dataset_ids":["id"],"reference":"raw ref or generator version"}} |
| S22-F-C80C90F679ED | availability_basis | 可用時間依據 | VARCHAR | 無 | 不可為 NULL | 區分真實首次可用、情境模擬可用與未知，不把2026取得時間倒填為2025歷史事實 observed / simulated / unknown |
| S22-F-645CE99A40BB | availability_evidence | 可用時間證據 | VARCHAR | 無 | 來源未提供或尚未知時允許 NULL，必須在 value_states 記錄狀態；主鍵不可空 | 真實日誌/發布紀錄引用，或情境規則版本；未知時NULL 符合定義與型別 |
| S22-F-5BF366AC7A44 | canonical_table | 目標資料表 | VARCHAR | 無 | 不可為 NULL | 這筆追溯對應的canonical資料表名稱 符合定義與型別 |
| S22-F-1EFA88095B78 | canonical_record_key | 目標紀錄鍵 | JSON | 無 | 不可為 NULL | 具名物件包含目標表完整主鍵與版本；來源一列拆成多列時各列獨立追溯 {"tenant_id":"id if scoped","primary_key_column":"value","version":"value if versioned"} |
| S22-F-920FBF12B84B | parent_provenance_ids | 上游追溯 | JSON | 無 | 不可為 NULL | 合併或衍生列引用所有上游追溯ID；純原始列空陣列 ["provenance_id",...] |

## fuel_vehicle_context

燃油研究車輛有效情境；以租戶及車輛的一個情境版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 車輛加入、離隊、來源代碼或營運時區變更時留版本；非固定採樣

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-C2DEC72D1337 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-56E2DDE70E01 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-D5FA58F0F1D3 | vehicle_context_id | 車輛研究情境版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-3519C7AE7023 | vehicle_source_id | 來源車號或車輛代碼 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 原系統車號／代碼，與穩定車輛 ID 作有效期間對照；保留改號歷史。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-E068EAEE050E | vehicle_active_from | 納入觀察開始時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 車輛進入本案授權且應受觀察範圍的時點。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-4D9C5A171C21 | vehicle_active_to | 納入觀察結束時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 離隊、授權停止或研究截止時點；裝置離線本身不自動代表離隊。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-3558678F4AAC | operating_timezone | 營運報表時區 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該車隊週報使用的 IANA 時區名稱；跨州行駛仍按核准報表時區歸週。 標準儲存語意：report_timezone → operating_timezone；統一單位或同義欄位；原值與原單位保存於原件/來源欄 有效IANA時區；初版America/Los_Angeles |
| S22-F-EF99F9841FCB | day_boundary_local | 營運日界時刻 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 一日開始的當地時刻，跨日行程依區間分配。 標準儲存語意：直接保留語意 HH:MM:SS；初版00:00:00 |
| S22-F-BB675177312C | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |

## fuel_task_assignment

車輛任務指派與實際作業；以車輛參與任務的一個有效期間及版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 派工、改派、實際開始與結束事件更新；每個有效區間一列

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-52BA9786C3B9 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-4B72A78A61A4 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-A5ED409C047D | task_assignment_id | 車輛任務指派版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-D05B4E31CF63 | task_id | 任務識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每次可辨識運輸任務或車隊定義工作段的 ID；可追到原始派工。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-C8BA8812D83F | task_type | 任務類型 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 任務的受控分類，例如幹線或區域配送；實際類別由車隊核對，未知及混合另列。 標準儲存語意：直接保留語意 regional_delivery / linehaul / mixed / unknown |
| S22-F-80B4B60A7AB4 | task_assignment_from | 車輛任務指派開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本車實際參與該任務的開始；中途換車需拆指派。每列含車輛 ID。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-4A5009A6C5CB | task_assignment_to | 車輛任務指派結束 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本車結束該任務的時點；不能只用訂單建立日或整週標籤代替。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-47138AD008B2 | task_start_at | 任務起點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際任務開始時間，日末可用但需原證據。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-2FED65F5C049 | task_end_at | 任務終點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際結束或觀察中狀態；未完不假定當日結束。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-7471FA0122C6 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |

## fuel_signal_definition

燃油與里程訊號解讀版本；以來源 ECU 配置及訊號種類的一個解碼版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 ECU配置、解碼規格或韌體版本變更時；每訊號種類獨立版本

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-0795B3AFF069 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-935200EC4FA2 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-2A906457D4F9 | signal_definition_id | 訊號解碼配置識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-181603333C15 | source_ecu_id | 來源ECU識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 提供讀值的 ECU 來源代碼／地址；不同 ECU 同名量不可直接拼接。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-20A000F153E1 | signal_definition_version | 訊號解碼定義版本 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該訊號的尺度、單位、無效碼、計數器行為所依據的解碼版本。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-7BE4FA8999EB | signal_kind | 訊號種類 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 只允許本核心表的累積燃料耗用或累積車輛里程；用來連各自單位、有效碼與連續段。 標準儲存語意：直接保留語意 fuel_total / odometer / engine_runtime / speed / engine_running / pto |
| S22-F-527085307CF5 | signal_unit | 訊號原始單位 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 逐訊號記 L、US gal、mile 或 km；不能從欄名或數值大小猜。 標準儲存語意：直接保留語意 L / US_gal / km / mile / hour / second / km/h / mph / boolean |
| S22-F-CABA424626BD | signal_resolution | 訊號解析度 | DECIMAL(20,6) | 數值＋原單位 | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每單位最小刻度；連同原始值或解碼尺度決定差分與對帳容差。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-A86A4F371032 | counter_modulus | 計數器回捲模數 | DECIMAL(20,6) | 數值／不適用／未知 | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 溢位回捲週期；若來源不會回捲，提供規格證據；未知不得按猜測補差分。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-E6550D177EE5 | firmware_version | 韌體版本 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 量測當時的韌體版本，更新生效時間須可對照。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-6A78F153472E | ecu_configuration | ECU 配置識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可定位實際 ECU／引擎配置的 OEM 料號或配置代碼，不以泛稱卡車取代。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-BD2FD907BA2A | signal_protocol | 訊號協定 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際 J1939、OBD-II、J1708／J1587 或廠商私有路徑；逐訊號記錄。 標準儲存語意：直接保留語意 J1939 / J1708_J1587 / OBD_II / vendor_private / synthetic |
| S22-F-DB848A3DB56A | source_signal_locator | 原訊號定位 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 廠商原欄名及可核對的 PGN／SPN／PID 等定位；未取得證據時明示尚未提供。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-3E6B11A037DE | valid_from | 配置有效起點 | TIMESTAMPTZ | UTC | 不可空 | 解碼與韌體配置開始有效時間 非空穩定識別 |
| S22-F-125A9CB8DE12 | valid_to | 配置有效終點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 開放有效期NULL須標open_ended，不同於未知 非空穩定識別 |

## fuel_counter_observation

燃料與里程獨立時間讀值；以來源傳輸紀錄中的一組可部分缺失讀值；燃料與里程各自有量測時間支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 設計為引擎運轉時60秒及啟停/重置留點；燃料與里程分別保留實際時間，非宣稱硬體現成支援

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "device_id"], "ref_table": "core_device", "ref_columns": ["tenant_id", "device_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "signal_definition_id"], "ref_table": "fuel_signal_definition", "ref_columns": ["tenant_id", "signal_definition_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}, {"columns": ["tenant_id", "distance_definition_id"], "ref_table": "fuel_signal_definition", "ref_columns": ["tenant_id", "signal_definition_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-3A06200B8CC7 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-B408EE659867 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-A2ED9391A06C | counter_observation_id | 計數器觀測版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-FECCE4C2DEE5 | fuel_total_l | 累積燃料耗用讀值 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | ECU 回報的累積燃料耗用量；需確認是引擎耗用估計、來源 ECU 與計數器邊界。不是油箱液位。 標準儲存語意：fuel_total → fuel_total_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-01A897631F7A | odometer_km | 累積行駛里程 | DECIMAL(20,6) | km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 車輛／引擎累積里程讀值，與燃油取同車、可配對區間。既有樣本原名 Engine Mile 不能直接當已驗證有效值。 標準儲存語意：odometer → odometer_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-7BC325D1EC6C | signal_validity | 訊號有效碼 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 有效、未提供、錯誤、不可用等原始碼與其解釋；0 只有已核對有效時才是零。 標準儲存語意：直接保留語意 valid / not_available / error / unknown |
| S22-F-7A48B2357F11 | fuel_measured_at | 燃料量測時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 燃料計數器自身時間，與日界及里程配對。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-70D9EEF8B668 | fuel_raw_unit | 燃料原單位 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 累計耗用單位與尺度，gal/L分開。 標準儲存語意：直接保留語意 L / US_gal |
| S22-F-B707071600F3 | fuel_validity | 燃料有效狀態 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 有效、不可用、錯碼與真零。 標準儲存語意：直接保留語意 valid / not_available / error / unknown |
| S22-F-668A08BFCBBD | distance_measured_at | 里程量測時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 里程自身量測時間，不假設同步。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-C026A5FDFA42 | distance_raw_unit | 里程原單位 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 來源mi/km及尺度。 標準儲存語意：直接保留語意 km / mile |
| S22-F-C24E346CE09F | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-A0D760FE695A | device_id | 裝置識別 | VARCHAR | none | 不可空 | 事件來源裝置 非空穩定識別 |
| S22-F-43C0EB7E70FF | signal_definition_id | 訊號解碼鍵 | VARCHAR | none | 不可空 | 選量測時有效且可知的訊號配置 非空穩定識別 |
| S22-F-FE0B1E994698 | fuel_total_raw | 原始燃油讀值 | DECIMAL(20,6) | source_unit | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 未換單位原數值 非空穩定識別 |
| S22-F-B2C473C69185 | odometer_raw | 原始里程讀值 | DECIMAL(20,6) | source_unit | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 未換單位原數值 非空穩定識別 |
| S22-F-47D0186B4A4D | distance_validity | 里程有效狀態 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 獨立於燃油有效狀態 valid / not_available / error / unknown |
| S22-F-9FBD24A0676A | distance_definition_id | 里程解碼鍵 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 燃油與里程可來自不同訊號定義，不用同一單位推定 非空穩定識別 |

## fuel_counter_change

計數器不連續證據；以指定車輛 ECU 訊號的一次重置回捲或未知跳變支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每次有證據重置、回捲、更換或推導未知跳變時；可晚到更正

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "device_id"], "ref_table": "core_device", "ref_columns": ["tenant_id", "device_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "signal_definition_id"], "ref_table": "fuel_signal_definition", "ref_columns": ["tenant_id", "signal_definition_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-110BB3D92EF4 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-8A7DE94C209D | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-23E34CB5F84C | counter_change_id | 計數器變更證據識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-E0F8A01F9C50 | counter_change_at | 重置或更換時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 有事件日誌則取得實際時點；只有跳變時保留不連續區間，不猜精確重置時間。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-F3B0D8B08438 | counter_change_type | 重置或更換類型 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 重置、已證實回捲、ECU 更換、裝置更換或推導的未知跳變；推導狀態與來源事件分開。 標準儲存語意：直接保留語意 reset / confirmed_rollover / ecu_replacement / device_replacement / unknown_discontinuity |
| S22-F-8385E63FD867 | counter_change_evidence | 計數器變更證據 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 事件原件、維修單或規格定位；只有負差分不能證明是哪種變更。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-8DF74CE9B014 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-6720597E77B8 | device_id | 裝置識別 | VARCHAR | none | 不可空 | 事件來源裝置 非空穩定識別 |
| S22-F-3DEE10A6B2BD | signal_definition_id | 訊號解碼鍵 | VARCHAR | none | 不可空 | 選量測時有效且可知的訊號配置 非空穩定識別 |
| S22-F-4EB562B7C268 | signal_kind | 變更訊號種類 | VARCHAR | none | 不可空 | 只影響此訊號的連續段，不連帶推定另一計數器 fuel_total / odometer |

## fuel_purchase_line

購油交易明細與調整；以一筆交易明細的一個版本；純金額調整仍獨立明細支援DA-E01的追溯用途

**History:** purchase_line_id保留來源業務鍵，line_version保存來源更正版本；兩者加tenant_id構成主鍵；不覆寫舊版。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每筆購油明細、退款及更正事件；入帳時間與購油時間分開

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-F75E05D07020 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-3258A872FD80 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-F0141BADE7D0 | purchase_line_id | 交易明細識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-AC601496F56D | line_version | 交易明細版本 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-0B43EFFB6430 | purchase_id | 購油交易識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 供應商的交易識別；同筆可含多商品或更正行。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-BC4EEAF29FE7 | purchase_time | 購油發生時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際購油發生時間，帶時區；用於營運週及市場背景配對。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-8C6EE4CC61CB | posted_at | 入帳時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 交易或更正進入供應商／財務帳的時點；不代替購油時間或銀行付款日。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-E572B5957577 | purchase_quantity_l | 購油數量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該燃油行實際購買量。金額折讓不能自動改成負數油量；退貨量需有來源證據。 標準儲存語意：purchase_quantity → purchase_quantity_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-E7604306B3A9 | purchase_quantity_unit | 交易數量單位 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | US gal 或 L 等實際單位；保留原單位再換算。 標準儲存語意：直接保留語意 L / US_gal |
| S22-F-A3780141E1F2 | purchase_amount | 購油明細行金額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 此明細行依原字典的最終應付或結算金額。若來源只有整筆交易總額，另存表頭，不複製到每行；未拆分前不能算燃油專屬單價。無付款證據時稱交易支出。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-FEF0A2540807 | purchase_fuel_type | 購油燃料類型 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 柴油、汽油或其他商品原始分類；DEF 與其他非燃油商品分開。 標準儲存語意：直接保留語意 diesel / gasoline / DEF / nonfuel / unknown |
| S22-F-76155AEF4C85 | currency | 交易幣別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本版核心比較提議限定 USD；其他幣別單列，未核准匯率政策前不混算。 標準儲存語意：直接保留語意 USD / 其他ISO4217代碼；不同幣別不加總 |
| S22-F-1575E3EC7AB9 | fuel_subtotal | 燃油稅前原額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 燃油商品在稅、折扣及額外費用之前的金額；來源如已淨額需提供口徑。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-22826925AA65 | fuel_tax_amount | 燃油稅額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可歸屬本燃油行的稅額；與 EIA 含稅價比較需確定同口徑。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-DE7B192F7D4E | fuel_discount_amount | 燃油折扣或折讓 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可歸屬本燃油交易的折扣／折讓，保存適用原交易；不要和油量相抵。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-6E6BF85893F8 | extra_fee_amount | 額外費用金額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 刷卡、服務等非燃油價格費用；另列，不暗中算進可比燃油單價。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-30C8C5EF6F5E | nonfuel_amount | 非燃油商品金額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | DEF、用品等非燃油項目；若逐行已排除，仍保留排除證據。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-9FFD92C7F5AF | transaction_status | 交易狀態 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 有效、待處理、取消、退刷或更正等供應商原狀態。 標準儲存語意：直接保留語意 posted / pending / cancelled / reversed / corrected |
| S22-F-D33A6A7C09F6 | adjustment_type | 調整類型 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 原購油、數量退回、純金額退款、折扣補登或更正；決定數量與金額處理。 標準儲存語意：直接保留語意 purchase / quantity_return / amount_refund / discount_adjustment / correction |
| S22-F-F55D6974B191 | original_purchase_line_id | 被更正的原明細 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 指向原交易與明細行的引用；不能只靠相同金額配對退刷。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-383272BDAC6B | fuel_card_id | 油卡代碼 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 經遮罩或代碼化的卡片 ID；不需完整支付卡號。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-1BA7BC6BB0DB | station_id | 加油站識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 交易發生的站點 ID 或可核對的商家定位。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-70B8A6E53D40 | statement_id | 原帳單識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 將交易、費用與更正連到獨立月結／週結對帳單。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-408B9DCE4586 | source_amount_basis | 金額口徑 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 稅前原額、含稅未折扣、含稅折後燃油淨額或整筆交易總額；用來防止重複加稅扣折扣。 標準儲存語意：直接保留語意 pretax_gross / tax_inclusive_gross / tax_inclusive_net_fuel / transaction_total |
| S22-F-87008D0D9634 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-20360226A256 | quantity_raw | 交易原數量 | DECIMAL(20,6) | source_unit | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 以purchase_quantity_unit解讀，轉換後為purchase_quantity_l 非空穩定識別 |
| S22-F-158EC8998CEC | record_state | 明細版本狀態 | VARCHAR | none | 不可空 | 與provenance版本一致 active / corrected / withdrawn / unknown |

## fuel_card_assignment

油卡車輛有效關聯；以一張代碼化油卡與車輛的一段有效關係支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 油卡指派、改派、停用或關聯更正時

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-75FA0497DADF | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-107E1FE61B0B | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-91022EF02DF9 | card_assignment_id | 油卡關聯版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-BE35413699F9 | card_vehicle_from | 油卡車輛關聯開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 卡片實際指派到該車輛的開始時間；每列帶車輛 ID。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-862283A730F5 | card_vehicle_to | 油卡車輛關聯結束 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 卡片改派或停用時間；一張卡多車共用時須逐交易核對，不強行連車。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-EFE75595F95E | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-BE2F7FD3E487 | fuel_card_id | 油卡代碼 | VARCHAR | none | 不可空 | 不保存完整支付卡號 非空穩定識別 |
| S22-F-8993A564C12D | known_from | 關聯首次可知時間 | TIMESTAMPTZ | UTC | 不可空 | 歷史回放不得提前套用後知關聯 非空穩定識別 |
| S22-F-7D1BB07021DF | known_to | 關聯被替代時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 系統時間的左含右不含終點 非空穩定識別 |

## fuel_station

購油站點；以一個購油站點版本支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 新增站點或站點國家州別資訊更正時

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-C3184805DB24 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-13DB8ACAD7CE | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-46DB3493DF76 | station_version_id | 購油站點版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-04DB5233025E | station_country | 加油站國家 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際購油國家；美國以外不套用美國 EIA 地區價。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-82DA0C9DCC7D | station_state | 加油站州別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際購油州別；配對 EIA 地區不用車隊總部地址。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-739A3448581C | station_id | 加油站識別 | VARCHAR | none | 不可空 | 原站點鍵與版本 非空穩定識別 |

## fuel_market_price

地區柴油公開參考價格；以價格系列及觀測日期的一個發布版本支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 官方週價格候選或合成週價格；發布修訂另版，S2.3才核對實際週期

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-F325898E1258 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-FF377BAC1A1A | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-542F7B387115 | market_price_version_id | 市場價格版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-0DA3330B8B2E | market_week_price | EIA地區週參考價 | DECIMAL(20,6) | USD/US_gal | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 官方地區道路用柴油週參考價；本版比較口徑為含稅 USD／US gal。與商業折扣價的差距只作背景。 標準儲存語意：直接保留語意 >0；不與USD/L直接相減 |
| S22-F-6042D818BDF0 | market_region | 市場價格地區 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際採用的 EIA 地區代碼與名稱；按加油站州別匹配，保留未匹配狀態。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-DAB6825A7302 | eia_series_id | EIA 系列識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 定位選定柴油價格系列；例如 California 歷史系列 EMD_EPD2D_PTE_SCA_DPG，其他地區代碼須逐一核對。[E4] 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-CBCC399C6083 | price_observation_date | 價格觀測日期 | DATE | date | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該週官方價格代表的觀測日期；不是下載日期或客戶加油日期。 標準儲存語意：直接保留語意 YYYY-MM-DD；operating_day按營運時區與日界求值 |
| S22-F-071123391877 | price_published_at | 發布可得時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 此價格版本實際已公開的時間或可支持的日期精度；若歷史證據不足標未知，不捏造精確時分。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-6FAEEE408DD0 | price_retrieved_at | 實際擷取時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 分析流程取得該版本的時間；可證明本流程何時看見資料。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-C9651EBCAF2F | price_snapshot_ref | 價格原件與網址 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 保存的原檔／回應及官方 URL，保留選定價格的行位。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-DB4DE683E0BA | price_method_version | 價格方法版本 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 沿用的來源方法或版本日期；跨方法變更時標示不可直接比較的區間。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-130311C48F1D | origin_label | 價格性質 | VARCHAR | none | 不可空 | 真實公開系列與虛構背景系列清楚區分 public / synthetic |
| S22-F-0B389AE17619 | publication_precision | 發布時間精度 | VARCHAR | none | 不可空 | 只有日期證據時保留date，不造出時分 timestamp / date / unknown |

## fuel_region_mapping

購油州別與價格地區對照；以國家州別與不重疊市場地區的一個映射版本支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 市場地區定義或映射版本改變時

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-0C248D4372FF | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-1403CD65EAB9 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-87A8C7BDD855 | region_mapping_id | 價格地區映射識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-B56636B5F212 | region_mapping_version | 州別地區映射版本 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 州別如何映至選定 PADD 或 California 的核准對照；不得混合重疊地區重複加權。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-7E65B84810EA | country_code | 國家 | VARCHAR | none | 不可空 | 原購油地國家 ISO3166-1 alpha2 |
| S22-F-E32055B0084C | state_code | 州別 | VARCHAR | none | 不可空 | 按購油站點匹配，不用總部地址 非空穩定識別 |
| S22-F-59657DE37983 | market_region | 價格地區 | VARCHAR | none | 不可空 | 選定不重疊地區 非空穩定識別 |
| S22-F-467033C56D44 | valid_from | 映射有效起點 | DATE | date | 不可空 | 地區映射版本起點 非空穩定識別 |
| S22-F-573A689DFCE6 | valid_to | 映射有效終點 | DATE | date | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 左含右不含終點 非空穩定識別 |

## fuel_tank_scope

油箱盤點範圍與容量；以車輛油箱或雙油箱群的一個範圍版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 油箱容量、組合、車輛歸屬或校準適用範圍變更時

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-F00C4E035ECE | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-18322638F69A | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-BEEEC58F55B9 | tank_scope_version_id | 油箱範圍版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-6FB319F4EFF7 | inventory_tank_scope_id | 油箱範圍識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 同一個單油箱／雙油箱群的範圍代碼；期初末及移動必須一致。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-D2ABDB8A1AFD | tank_capacity_l | 油箱容量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 與盤點油箱範圍一致、可核對的有效容量。 標準儲存語意：tank_capacity → tank_capacity_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-05126C6920AD | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |

## fuel_inventory_measurement

獨立庫存量測；以同一油箱範圍的一次實際量測及版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 設計為每週期初/期末邊界與例外抽查盤點；每次量測留一列

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-EBE3754F8411 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-925008D4B76A | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-C2FAAFCEF725 | inventory_measurement_id | 庫存量測版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-2FB2AE92472D | inventory_measurement_method | 庫存量測方法 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 量尺、校準感測器或其他實際方法；保留容量／校準／原件引用。未校準油表不可當精確量。 標準儲存語意：直接保留語意 calibrated_sensor / dipstick / manual_volume / unknown |
| S22-F-6811E4F8D159 | inventory_uncertainty | 量測不確定度 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每次量測可支持的誤差範圍及依據；未知時不能聲稱精確燃油耗用。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-EFEF9AAE7DC0 | raw_level_percent | 原始油位百分比 | DECIMAL(20,6) | percent | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每次盤點當時的原始百分比；分別連到期初與期末盤點 ID。 標準儲存語意：直接保留語意 0 <= value <= 100 |
| S22-F-2F8F5EF06FF1 | calibration_curve_ref | 油位校準證據 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 支持百分比轉體積的校準曲線／方法及有效版本；未校準不可假設線性。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-A2BEBDF3EA20 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-D9E4348342F5 | inventory_tank_scope_id | 油箱範圍 | VARCHAR | none | 不可空 | 和容量校準適用範圍一致 非空穩定識別 |
| S22-F-B7AD5340D865 | measured_at | 盤點時點 | TIMESTAMPTZ | UTC | 不可空 | 實際量測時間 非空穩定識別 |
| S22-F-85CEE39441C0 | quantity_l | 獨立庫存體積 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 原量測換L；未校準百分比不換體積 0至可核對容量；超界隔離 |
| S22-F-FB52B005CCDC | raw_quantity | 庫存原始量 | DECIMAL(20,6) | source_unit | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 保留來源量或百分比 非空穩定識別 |
| S22-F-991C3F79FAAE | raw_quantity_unit | 庫存原始單位 | VARCHAR | none | 不可空 | L/USgal/percent明示 L / US_gal / percent |
| S22-F-0CF401367397 | measurement_role | 盤點角色 | VARCHAR | none | 不可空 | 同一量測可被兩個期間引用，角色在期間表以opening/closing鍵指定 period_boundary / spot_check |

## fuel_movement

燃料進出移動；以同一憑證的一次燃料移動支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每次實際加注、轉入、轉供、維修放油等事件；非交易入帳節奏

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-2D2BD45AE7AE | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-B3A9588B6FF1 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-7115F21F5DB7 | fuel_movement_id | 燃料移動版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-29C399C5AF3F | fuel_movement_at | 燃料移動時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際燃料進出該油箱的時點；不能直接以交易入帳時間代替。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-3CD16ADCAB3E | fuel_movement_type | 燃料移動類型 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 購油加注、其他轉入、轉供、維修放油、可核對其他用途等。 標準儲存語意：直接保留語意 refuel / transfer_in / transfer_out / maintenance_drain / other_verified |
| S22-F-8B57282DC791 | fuel_movement_quantity_l | 燃料移動數量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每次移動的實測或可核對數量，附 L／US gal 與憑證；未知移出不填 0。 標準儲存語意：fuel_movement_quantity → fuel_movement_quantity_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-CB4790D2FD5E | fuel_movement_reference | 燃料移動對應憑證 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 對應購油明細、供油單或轉移證據，並保留進出油箱代碼。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-E29B5BD0485C | movement_source_scope | 移動來源油箱或站點 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際提供該燃料的油箱／加油站／供油點代碼；與移動類型一致。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-001C0487F3D2 | movement_destination_scope | 移動目的油箱或用途 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際接收油箱或非目標用途代碼，據此判斷是否進出本盤點範圍。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-B295D875B7CB | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |

## fuel_inventory_balance

盤點期間燃料平衡；以同油箱範圍及兩個量測邊界的一次平衡計算支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每對可核對期初/期末盤點完成時計算；輸入更正新增計算版本

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "opening_measurement_id"], "ref_table": "fuel_inventory_measurement", "ref_columns": ["tenant_id", "inventory_measurement_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}, {"columns": ["tenant_id", "closing_measurement_id"], "ref_table": "fuel_inventory_measurement", "ref_columns": ["tenant_id", "inventory_measurement_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-1B3A70ADFA8C | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-C6D5239AF585 | balance_id | 盤點平衡計算識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-B0DF03BB97F1 | opening_volume_l | 期初燃料庫存量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 期初實際可核對燃料量；液位百分比只有配合容量與校準才能轉成體積。 標準儲存語意：fuel_inventory_start → opening_volume_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；從opening_measurement_id對應獨立quantity_l投影，保留來源不覆寫 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-853D56BB292E | closing_volume_l | 期末燃料庫存量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 相同油箱範圍的期末實際燃料量。 標準儲存語意：fuel_inventory_end → closing_volume_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；從closing_measurement_id對應獨立quantity_l投影，保留來源不覆寫 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-8B1AB71C1EB4 | period_start_at | 期初庫存量測時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 期初盤點實際時間，與同期間距離讀值對齊。 標準儲存語意：inventory_start_at → period_start_at；統一單位或同義欄位；原值與原單位保存於原件/來源欄 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-5B3DB1C56ADC | period_end_at | 期末庫存量測時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 期末盤點實際時間，不能以報表結束日代填。 標準儲存語意：inventory_end_at → period_end_at；統一單位或同義欄位；原值與原單位保存於原件/來源欄 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-3F329D651FF5 | inventory_quality_state | 庫存平衡品質 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 邊界一致、量測誤差已知、移動完整、未知損失等核對狀態。 標準儲存語意：直接保留語意 balanced_verified / uncertainty_known / incomplete_movements / unknown_loss / boundary_mismatch |
| S22-F-6D73EB55A378 | refuel_volume_l | 期間加注燃料量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 盤點期間、同油箱範圍內可核對的實際加注量加總；交易須證明加到此油箱。 標準儲存語意：inventory_fuel_added → refuel_volume_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；同期間同油箱實際refuel移動L加總；交易須有加到此油箱的證據 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-5AA928079A13 | transfer_in_l | 期間轉入燃料量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 盤點期間其他燃料轉入量總和；確認沒有轉入才記 0。 標準儲存語意：inventory_fuel_transfer_in → transfer_in_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；同期間transfer_in移動L加總；無事件與已確認沒有移動分開 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-A6A89111BA41 | removed_l | 期間非引擎移出燃料量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 轉供、放油與可核對其他用途的期間總和；未知流失不填 0。 標準儲存語意：inventory_fuel_removed → removed_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；同期間已核對transfer_out/maintenance_drain等移動L加總 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-A823A015DCBD | balance_consumption_l | 庫存平衡推估耗用 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 期初＋加注＋其他轉入－期末－已核對非目標移出；未核對其他用途或漏失時，只稱油箱平衡量。 標準儲存語意：inventory_balance_consumption → balance_consumption_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；opening_volume_l + refuel_volume_l + transfer_in_l - closing_volume_l - removed_l；未知移動傳播NULL，未核對其他用途則只稱平衡量 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-5695B1AA8806 | net_transfer_l | 燃料淨轉入 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 其他油箱轉入減轉出，有證據才填。 標準儲存語意：net_fuel_transfer → net_transfer_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；transfer_in_l-removed_l；明示是否含非燃油用途，未知傳播 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-E1FF1184ACEE | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-23FAF1A4A34A | opening_measurement_id | 期初或期末量測鍵 | VARCHAR | none | 不可空 | 引用獨立量測，不重寫人工讀值 非空穩定識別 |
| S22-F-70200921C735 | closing_measurement_id | 期初或期末量測鍵 | VARCHAR | none | 不可空 | 引用獨立量測，不重寫人工讀值 非空穩定識別 |
| S22-F-4C3BE05635FC | inventory_tank_scope_id | 油箱範圍 | VARCHAR | none | 不可空 | 期間兩端與全部移動必須同範圍 非空穩定識別 |
| S22-F-94F3C6B6440A | as_of_time | 平衡資料截止 | TIMESTAMPTZ | UTC | 不可空 | 此版本可用來源的截止時間 非空穩定識別 |
| S22-F-97749B544FC4 | uncertainty_l | 平衡不確定度 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 盤點與移動誤差合成方法另存版本；未知不填0 非空穩定識別 |

## fuel_statement_control

獨立帳單控制總數；以帳單版本及分類燃料類型幣別單位的控制總數支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每份獨立週結/月結帳單及更正版本；按分類保存控制數

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-BF360757C9DC | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-789303D013FD | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-1886FE873003 | statement_control_id | 帳單控制總數識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-783E3AC8FDFB | statement_period_start | 帳單期間起點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 獨立帳單的計費起點；保留原時區／日期規則。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-A7A9AB1F6407 | statement_period_end | 帳單期間終點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 與起點共同界定帳單總額，不能直接拿整月帳單比單週。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-134911187269 | statement_control_amount | 帳單控制金額 | DECIMAL(20,6) | currency欄指定原幣；初版USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 獨立帳單的燃油／稅費／非燃油／調整分類總額及分類代碼；按原帳單可提供層級保存。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-2105E8E6BEE5 | statement_control_quantity | 帳單控制燃油量 | DECIMAL(20,6) | quantity_unit欄指定，原值保留；對帳時明確換算 | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 帳單若提供，保存燃料種類與數量單位；沒有時標未知，改以原交易憑證抽查量。 標準儲存語意：直接保留語意 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-5D18AB148523 | statement_id | 原始帳單識別 | VARCHAR | none | 不可空 | 控制總數分組鍵；需與交易對帳口徑一致 非空穩定識別 |
| S22-F-AE17AEBC910D | category_code | 帳單控制分類 | VARCHAR | none | 不可空 | 控制總數分組鍵；需與交易對帳口徑一致 非空穩定識別 |
| S22-F-AB83A8FD36ED | currency | 交易幣別 | VARCHAR | none | 不可空 | 控制總數分組鍵；需與交易對帳口徑一致 非空穩定識別 |
| S22-F-FC528EA5EED9 | fuel_type | 燃料種類 | VARCHAR | none | 不可空 | 控制總數分組鍵；需與交易對帳口徑一致 非空穩定識別 |
| S22-F-87783CB8A1B9 | quantity_unit | 控制數量單位 | VARCHAR | none | 不可空 | 控制總數分組鍵；需與交易對帳口徑一致 非空穩定識別 |

## fuel_reference_case

燃油獨立預期答案；以一個覆核案例與核對指標的一個答案版本支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 驗證案例建立或獨立答案覆核、更正時；執行測試不覆寫答案

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-B7901198A144 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-C7F00AA0111B | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-84178F94DA71 | reference_case_id | 獨立核對案例識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-DACDF730981A | reference_metric | 核對指標代碼 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-73DA895EC734 | expected_value | 獨立預期答案 | JSON | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 由原件手算的數值與單位，或預期處理狀態；同案不同指標分列。 標準儲存語意：直接保留語意 物件 {numeric_value:number / null,unit:string,state_value:string / null,tolerance:number,evidence_ref:string}；數值答案及狀態答案二擇一 |
| S22-F-F005B341A4F9 | reference_reviewer_role | 覆核角色 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 獨立核對者的角色代碼。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-EAF532CDB00B | reference_reviewed_at | 覆核完成時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該案例實際核對完成的時間。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-F234969319E3 | reference_evidence_ref | 獨立核對證據 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 原件與手算附件定位，不能引用待驗證輸出當正確答案。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-DA9B34036642 | reference_review_status | 核對結論 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 通過、未通過、爭議、尚未覆核。 標準儲存語意：直接保留語意 passed / failed / disputed / not_reviewed |
| S22-F-B6DBD5664E8A | scenario_id | 驗證情境 | VARCHAR | none | 不可空 | 手算或生成真值的獨立案例鍵 非空穩定識別 |

## fuel_output_review

報告接收與案例採用；以專案發布成果中的一個車輛週或車輛日調查案例支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 報告接收、開啟、案例採用及覆核狀態改變時

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-F0D7E1612239 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-CE6E7793438F | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-E974F72E3E6E | review_case_id | 報告調查案例識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-BC29A9B0672C | output_received_at | 接收或開啟時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 管理者實際收到或開啟指定報告的時間；寄出時間不能代替。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-59B5ADCC42C2 | adoption_status | 採用或覆寫狀態 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 採用、部分採用、拒絕、尚未審閱；不能把開啟自動當採納。 標準儲存語意：直接保留語意 accepted / partly_accepted / rejected / not_reviewed |
| S22-F-9E95C6E14A70 | review_reason | 調查或拒絕原因 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 確認資料問題、價格變化、任務差異、需維修、原因未知等，附自由補充與證據。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-A4AFAA7C2247 | review_outcome | 覆核或追蹤狀態 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 已確認、否定、爭議、未回報、未結案、結果未成熟或失訪；確認無問題另有證據。 標準儲存語意：直接保留語意 confirmed / negated / disputed / not_reported / open / not_mature / lost_followup |
| S22-F-54A449D9EDB9 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-01E7EF3E6289 | project_id | 專案識別 | VARCHAR | none | 不可空 | DA-E01或DS-E01，避免跨案同ID混淆 DA-E01 / DS-E01 |
| S22-F-2320A3D2AAF0 | output_id | 發布成果識別 | VARCHAR | none | 不可空 | 連回本專案報告/診斷輸出；跨表條件式引用 非空穩定識別 |
| S22-F-379B62769972 | evidence_origin | 追蹤證據性質 | VARCHAR | none | 不可空 | 此作品初版僅提供合成演練，真實採用另行記錄 synthetic_scenario / real_observation |

## fuel_action_followup

燃油措施與後續觀察；以一項措施在指定比較與追蹤窗口的一個觀察版本支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 措施執行、比較窗口確認、追蹤觀察更新及結案時；尚未發布可只有合成演練

**References:** [{"columns": ["provenance_id"], "ref_table": "provenance_record", "ref_columns": ["provenance_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "review_case_id"], "ref_table": "fuel_output_review", "ref_columns": ["tenant_id", "review_case_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-61F64275E5E5 | provenance_id | 來源追溯鍵 | VARCHAR | none | 不可空 | 連到原件或合成生成情境、版本、可知時點及逐欄缺值狀態 非空文字；未知以明確狀態表示 |
| S22-F-42FF66AA3D64 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-EC34C503968A | action_followup_id | 措施追蹤版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-B7380F458146 | action_id | 行動識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 每一個實際措施的 ID；未處理留明確狀態。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-C9022945CAD0 | action_type | 後續處置 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際檢查、維修、調度調整、與司機確認或不處理；補具體內容，不能只記建議。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-0F2C367AB079 | action_time | 處置時間 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 措施實際開始執行時間；用來界定前後觀察。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-76F949D20DA8 | active_review_seconds | 實際調查工時 | BIGINT | seconds | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 該案例實際查表、核對與溝通分鐘；排除單純等待，記錄計時方式。 標準儲存語意：active_review_minutes → active_review_seconds；統一單位或同義欄位；原值與原單位保存於原件/來源欄；minutes × 60 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-A82250A34F89 | baseline_review_seconds | 原流程對照工時 | BIGINT | seconds | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 同類任務採原流程的實測分鐘，附對照案例與計時方式；不憑回憶估計。 標準儲存語意：baseline_review_minutes → baseline_review_seconds；統一單位或同義欄位；原值與原單位保存於原件/來源欄；minutes × 60 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-745D05E64278 | baseline_window_start | 處置前觀察開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 同車同任務處置前比較窗口的開始。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-A2DC5318BAB9 | baseline_window_end | 處置前觀察結束 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 處置前比較窗口截止；不可延伸至措施之後。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-EB8EA4C05FD1 | followup_start | 處置後觀察開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 措施後真正開始計算可比較結果的時間。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-9DF14E502974 | outcome_observation_end | 結果觀察終點 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 目前實際已觀察到的截止時間；和預定追蹤截止分開，未滿期間不當完整。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-25B9A6201DDD | observed_fuel_l | 後續實際耗用量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 從後續同口徑 B 或 E 包重算的耗用，並附同期間距離與任務；不請人手填無來源的節油數。 標準儲存語意：observed_business_result → observed_fuel_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；後續同口徑量測/盤點重新計算的耗用L；僅合成演練，不寫成已實現節油 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-BF2435D7CD38 | action_evidence | 處置與結果證據 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 維修單、調查紀錄、計時附件或結果量測快照，連回行動與比較案例。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-DB4FBC123261 | planned_followup_end | 預定追蹤截止 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 事前規劃的結果觀察截止；與 F029 實際已觀察終點比較，結果尚未成熟另列。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-2B32A4D2FB71 | followup_distance_km | 後續有效里程 | DECIMAL(20,6) | km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 與後續耗用同區間里程，從量測算。 標準儲存語意：followup_distance → followup_distance_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-E88FA37B6561 | followup_task_mix | 後續任務構成 | JSON | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 任務/載重/PTO比例，辨認情境變化。 標準儲存語意：直接保留語意 陣列 [{task_type:string,distance_share:number,duration_share:number,payload_band:string,pto_share:number}]；各適用比例分母明示 |
| S22-F-9084D84E18FC | investigation_seconds | 調查工時 | BIGINT | seconds | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 實際查核投入，不含等待。 標準儲存語意：investigation_minutes → investigation_seconds；統一單位或同義欄位；原值與原單位保存於原件/來源欄；minutes × 60 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-D865AEE6E462 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-E13C827B3713 | project_id | 專案識別 | VARCHAR | none | 不可空 | DA-E01或DS-E01，避免跨案同ID混淆 DA-E01 / DS-E01 |
| S22-F-CC34BAF0BD99 | output_id | 發布成果識別 | VARCHAR | none | 不可空 | 連回本專案報告/診斷輸出；跨表條件式引用 非空穩定識別 |
| S22-F-A0A73191B974 | evidence_origin | 追蹤證據性質 | VARCHAR | none | 不可空 | 此作品初版僅提供合成演練，真實採用另行記錄 synthetic_scenario / real_observation |
| S22-F-89745D3773CE | review_case_id | 調查案例鍵 | VARCHAR | none | 不可空 | 措施來自哪一報告案例 非空穩定識別 |

## fuel_report_run

燃油週報執行設定；以一次週報執行與輸入版本快照支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每週報告執行及每次補傳更正重跑；初版週界後48小時，7日後另版修訂

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-F7F4D1F26DAB | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-9D2E27FF6768 | output_id | 發布成果識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-B07A1ADE4194 | metric_version | 指標定義版本 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 週界、篩選、單位、退刷、配對區間、權重與重跑規則的核准版本。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-F2A697ACACFB | metric_owner | 指標定義責任人角色 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 核准指標口徑的業務角色，包含需同步的車輛週報與車隊彙總表。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-07680351333D | report_week_start | 報告週開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 核准時區的週一 00:00，或核准的替代週界。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-D6DDB7661FBF | report_week_end | 報告週結束 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 下一週同週界，採左含右不含區間。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-D8D64B9C6AAE | as_of_time | 報告資料截止 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本次納入已取得版本的截止時間；事後更正另版。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-B5848E94B4E5 | input_snapshot | 輸入快照與篩選 | JSON | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 此次採用的各來源版本清單及車輛／燃料／期間篩選，足以原樣重跑。 標準儲存語意：直接保留語意 物件 {source_versions:[{dataset_id,version,sha256}],filters:{vehicle_ids,fuel_types,start,end},code_version}；禁止密鑰 |

## fuel_paired_interval

有效燃油里程配對區間；以同車燃油段與距離段交集內可歸屬的區間支援DA-E01, DS-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 原始量測/有效關聯/計數器邊界更新後建立共同有效區間；按as_of重算版本

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "fuel_start_observation_id"], "ref_table": "fuel_counter_observation", "ref_columns": ["tenant_id", "counter_observation_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}, {"columns": ["tenant_id", "fuel_end_observation_id"], "ref_table": "fuel_counter_observation", "ref_columns": ["tenant_id", "counter_observation_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}, {"columns": ["tenant_id", "distance_start_observation_id"], "ref_table": "fuel_counter_observation", "ref_columns": ["tenant_id", "counter_observation_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}, {"columns": ["tenant_id", "distance_end_observation_id"], "ref_table": "fuel_counter_observation", "ref_columns": ["tenant_id", "counter_observation_id"], "condition": "非空時參照有效；跨租戶引用禁止；參照業務識別時須以對應provenance版本/as_of選出唯一版本，不能任取歷史列"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-0BAA53173D48 | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-8D57F9E2262B | paired_interval_id | 燃油里程配對區間識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-30E75548EDD6 | fuel_segment_id | 燃油計數器連續段 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 按燃油計數器自己的重置／回捲／更換證據切段。 標準儲存語意：直接保留語意；來源ECU、解碼版本及已確認計數器邊界切燃油段 來源受控代碼或具版本的文字；未知單列 |
| S22-F-808A4D6EAF9D | distance_segment_id | 里程計數器連續段 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 按里程計數器自己的不連續證據切段；與燃油段可不同。 標準儲存語意：直接保留語意；里程依自身不連續證據切段，不能直接複製燃油段 來源受控代碼或具版本的文字；未知單列 |
| S22-F-23D65C23361C | paired_interval_start | 配對區間開始 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 燃油與里程共同有效、可對齊區間的開始。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-9FAF48A03C8B | paired_interval_end | 配對區間結束 | TIMESTAMPTZ | UTC | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 共同有效區間的結束，須能判斷是否跨週或任務邊界。 標準儲存語意：直接保留語意 ISO8601帶時區，保留原時區/offset；未知精度不補假時分 |
| S22-F-268AF93FB248 | paired_fuel_l | 配對區間燃油量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本共同有效區間的燃油差分與換算值。 標準儲存語意：paired_fuel_gal → paired_fuel_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；相同連續段末累積燃料減初值，換為L；不跨未知重置；必須落在共同有效區間 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-6568843330D3 | paired_distance_km | 配對區間里程 | DECIMAL(20,6) | km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 與燃油完全同區間的里程差分與換算值。 標準儲存語意：paired_distance_mile → paired_distance_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km；相同距離段末值減初值；原mile乘1.609344換km；與燃料同一區間 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-91E88A55392C | excluded_interval_reason | 排除或未歸週原因 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 無效讀值、未知重置、不同時間範圍、跨週無法分配、車輛關聯不明等。 標準儲存語意：直接保留語意 來源受控代碼或具版本的文字；未知單列 |
| S22-F-888673AD94A3 | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-547772348641 | as_of_time | 資料截止 | TIMESTAMPTZ | UTC | 不可空 | 只使用此時點前已可得版本；重算另版 非空穩定識別 |
| S22-F-FA45064E1D65 | calculation_version | 計算版本 | VARCHAR | none | 不可空 | 單位、邊界、有效性與聚合方法版本 非空穩定識別 |
| S22-F-034D1F461B65 | input_provenance_ids | 輸入原件鍵 | JSON | none | 不可空 | 可回到每一筆輸入版本 array<string provenance_id> |
| S22-F-FD81A8D09F67 | fuel_start_observation_id | 燃油初值讀值鍵 | VARCHAR | none | 不可空 | 引用開始讀值 非空穩定識別 |
| S22-F-B9198DB1C8CA | fuel_end_observation_id | 燃油末值讀值鍵 | VARCHAR | none | 不可空 | 引用結束讀值 非空穩定識別 |
| S22-F-E0F66289D2E3 | distance_start_observation_id | 里程初值讀值鍵 | VARCHAR | none | 不可空 | 引用開始讀值 非空穩定識別 |
| S22-F-BA9F5FEC10A4 | distance_end_observation_id | 里程末值讀值鍵 | VARCHAR | none | 不可空 | 引用結束讀值 非空穩定識別 |
| S22-F-2FC67DA3973D | accepted | 區間是否採用 | BOOLEAN | none | 不可空 | 排除原因與布林一致 true / false |

## fuel_weekly_metric

車輛週燃油與購油分析；以報告執行及車輛與任務比較組的一列週指標支援DA-E01的追溯用途

**History:** 技術列ID識別一個不可變版本，按來源業務鍵及版本穩定生成；更正產生新列ID與provenance_id。原業務鍵及版本保留於provenance，as_of選版；有效期左含右不含。

**Time and frequency:** 2025-01-01至2025-06-30模擬窗口；所需邊界/標籤成熟追蹤另依個案規格。公開RAG文件採實際擷取版本，不回填2025。 每次報告執行按車輛週與任務比較組聚合

**References:** [{"columns": ["tenant_id"], "ref_table": "core_tenant", "ref_columns": ["tenant_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "vehicle_id"], "ref_table": "core_vehicle", "ref_columns": ["tenant_id", "vehicle_id"], "condition": "非空時參照有效；跨租戶引用禁止"}, {"columns": ["tenant_id", "output_id"], "ref_table": "fuel_report_run", "ref_columns": ["tenant_id", "output_id"], "condition": "非空時參照有效；跨租戶引用禁止"}]

| Stable field ID | English name | 中文 | Type | Unit | Nullable | Meaning and valid values |
|---|---|---|---|---|---|---|
| S22-F-85FA27E6387E | tenant_id | 租戶識別 | VARCHAR | none | 不可空 | 資料所屬租戶 非空文字；未知以明確狀態表示 |
| S22-F-94BB6000B0A9 | weekly_metric_id | 車輛週指標版本識別 | VARCHAR | none | 不可空 | 穩定識別；重跑同一來源版本得到同鍵 非空文字；未知以明確狀態表示 |
| S22-F-A9BBA1B0244D | fuel_used_l | 週耗用燃料量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 報告期間內同一批合格配對區間的耗用總和；庫存法只能使用其實際觀察期間，方法另標。 標準儲存語意：fuel_used → fuel_used_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；SUM(同週同車合格paired_fuel_l)；跨週無法切分者另列，不平均分配 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-7FB317D035E4 | distance_travelled_km | 週行駛距離 | DECIMAL(20,6) | km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 與耗用使用完全相同有效區間的距離總和；不可取另一份更完整里程混當分子。 標準儲存語意：distance_travelled → distance_travelled_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km；SUM(與燃料完全同集合的paired_distance_km) 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-512C9499EF11 | measurement_coverage | 有效量測覆蓋率 | DECIMAL(20,6) | ratio | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可對齊且可歸屬目標週的有效配對時間／車輛應觀察時間；另列無法歸週量。封包缺少不直接等於總量遺失。 標準儲存語意：直接保留語意；共同有效配對秒數/按有效部署及營運規則的應觀察秒數；不以封包率代替 0 <= value <= 1 |
| S22-F-4915EFCBB217 | consumption_method | 耗用取得方法 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 本次採 ECU 差分或庫存平衡；若供應商僅給既有彙總，須先取得同等時間、單位、算法與驗證證據。 標準儲存語意：直接保留語意 ecu_difference / inventory_balance / verified_supplier_aggregate |
| S22-F-E5AABC06D752 | mpg | 加權燃油效率 | DECIMAL(20,6) | mile/US_gal | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 相同有效區間里程總和／耗用總和；車隊層亦採總量相除。 標準儲存語意：直接保留語意；(distance_travelled_km/1.609344)/(fuel_used_l/3.785411784)；分母<=0或缺失回傳NULL和狀態；車隊亦總量相除 >0或NULL；零距離可為0但燃油必須>0 |
| S22-F-0ED44C29162A | comparable_fuel_amount | 可比燃油交易淨額 | DECIMAL(20,6) | USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 依金額口徑分支：未稅原額加燃油稅、扣可歸屬折扣退款各一次；已核對含稅淨額直接採用。費用與非燃油排除，組成只用對帳不重複調整。 標準儲存語意：直接保留語意；依source_amount_basis分支；未稅燃油原額+稅-折扣各一次，含稅淨額直接採；排除費用與非燃油 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-87AD4EAEA47B | weighted_purchase_price_usd_per_l | 購油加權單價 | DECIMAL(20,6) | USD/L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可比燃油交易淨額／對應淨購油量；純金額調整需分開或回到原交易，不能造出退款油量。 標準儲存語意：weighted_purchase_price → weighted_purchase_price_usd_per_l；統一單位或同義欄位；原值與原單位保存於原件/來源欄；US gal × 3.785411784 = L，L原值不再換算；展示原USD/USgal時用USD/L ×3.785411784；可比燃油USD淨額/同集合淨購油L；純金額調整指回原交易，不造負油量 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-85B1B72958AA | purchase_spend_usd_per_km | 購油支出每英里 | DECIMAL(20,6) | USD/km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 指定營運週的購油交易支出／weekly_valid_distance；不以可能僅部分配對區間的 F013 代替完整週距離，不當作當週耗用成本。 標準儲存語意：purchase_spend_per_mile → purchase_spend_usd_per_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km；展示原USD/mile時用USD/km ×1.609344；原S2.1 USD/mile改為USD/km標準儲存；可比交易支出/完整週有效距離，不稱當週耗用成本 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-B289BD6A9719 | benchmark_amount | 市場參考金額 | DECIMAL(20,6) | USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 合格配對交易的油量乘各自 EIA 價後加總。 標準儲存語意：直接保留語意；SUM(合格交易purchase_quantity_l/3.785411784*對應market_week_price USD/USgal) 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-50E9FFB80B31 | benchmark_amount_gap | 相對市場金額差 | DECIMAL(20,6) | USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 同一配對交易集的可比燃油淨額減市場參考金額。 標準儲存語意：直接保留語意；同市場配對集合燃油淨額減benchmark_amount；只描述市場背景差額 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-3812C03068A3 | benchmark_match_coverage | 市場配對覆蓋率 | DECIMAL(20,6) | ratio | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 可比且成功配對的購油量／納入市場比較的總購油量。 標準儲存語意：直接保留語意；成功配對購油L/納入比較總購油L；未配對單列 0 <= value <= 1 |
| S22-F-6B595AA7F851 | purchase_price_effect | 購油價格效果 | DECIMAL(20,6) | USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 以前期量為權重的兩期價格差；公式見計算章。 標準儲存語意：直接保留語意；(P_current-P_previous)*Q_previous；P用USD/L，Q用L；同一產品/群組/口徑 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-874B17E2AC14 | purchase_quantity_effect | 購油數量效果 | DECIMAL(20,6) | USD | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 以本期價格乘兩期購油量差；公式見計算章。 標準儲存語意：直接保留語意；P_current*(Q_current-Q_previous)；與價格效果相加等於兩期購油額差；條件不一致另列組成影響 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-1EB0E1FABDB9 | weekly_valid_distance_km | 完整週有效距離 | DECIMAL(20,6) | km | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 由 F010 里程連續段重建整個報告週，含未與燃油配對但里程可靠的區間；缺週界或未知重置則不標完整。 標準儲存語意：weekly_valid_distance → weekly_valid_distance_km；統一單位或同義欄位；原值與原單位保存於原件/來源欄；mile × 1.609344 = km；里程自身連續段跨完整週差分加總，與燃油配對距離分開；缺邊界不標完整 有限數值，範圍依業務檢查；負值僅允許退款、淨轉移、殘差及差額等明示欄位 |
| S22-F-D40F8A07C8FF | vehicle_id | 車輛識別 | VARCHAR | none | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 歸屬車輛；未知歸屬保留例外，不強行填車 非空穩定識別 |
| S22-F-8D143B3D8F2F | as_of_time | 資料截止 | TIMESTAMPTZ | UTC | 不可空 | 只使用此時點前已可得版本；重算另版 非空穩定識別 |
| S22-F-F986AD45EB75 | calculation_version | 計算版本 | VARCHAR | none | 不可空 | 單位、邊界、有效性與聚合方法版本 非空穩定識別 |
| S22-F-E2184AF3BCFE | input_provenance_ids | 輸入原件鍵 | JSON | none | 不可空 | 可回到每一筆輸入版本 array<string provenance_id> |
| S22-F-C7ADA8EBBCDA | output_id | 報告執行鍵 | VARCHAR | none | 不可空 | 連到週界、截止與輸入快照 非空穩定識別 |
| S22-F-83B2A665741F | task_comparison_group | 任務比較組 | VARCHAR | none | 不可空 | 同任務或mixed/unknown不得暗中混組 非空穩定識別 |
| S22-F-7AFD6E89DA76 | valid_paired_seconds | 共同有效配對秒數 | DECIMAL(20,6) | seconds | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 比例指標的實際分子或分母，和對應圖表保持一致 >=0 |
| S22-F-E442E3D1E4FE | expected_observation_seconds | 應觀察秒數 | DECIMAL(20,6) | seconds | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 比例指標的實際分子或分母，和對應圖表保持一致 >=0 |
| S22-F-EED9D32B006F | benchmark_matched_quantity_l | 市場成功配對購油量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 比例指標的實際分子或分母，和對應圖表保持一致 >=0 |
| S22-F-4EBE99096F9D | benchmark_eligible_quantity_l | 市場比較合格購油量 | DECIMAL(20,6) | L | 未知、未取得、不適用或未成熟時可空；provenance_record.value_states 逐欄保留原因 | 比例指標的實際分子或分母，和對應圖表保持一致 >=0 |
