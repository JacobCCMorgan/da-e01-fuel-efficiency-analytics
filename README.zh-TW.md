# 車隊燃油效率與價格差異分析

**DA-E01 · 燃油與能源營運 · Python、SQL、DuckDB、PostgreSQL、HTTP 資料匯入**

[English](README.md) · [互動報告](outputs/dashboard.html) · [分析 Notebook](notebooks/01_fuel_analysis.ipynb) · [圖表中文講解](docs/chart_walkthrough_zh.md) · [執行手冊](docs/runbook.md) · [交付包與驗證](docs/delivery.md) · [業務主題作品索引](https://github.com/JacobCCMorgan/data-portfolio)

加油量、ECU 耗用量與油箱存量代表不同事情。本專案整合車端累積計數器、加油交易、油箱異動、歷史裝置關聯與區域市場價格，建立可追溯的每週分析，並將需要查核的結果接到審閱、措施與後續觀察紀錄。

**資料範圍：**2025 年 1–6 月、3 個虛構租戶、30 輛車、36 個裝置、45 位司機及 1,800 趟計畫行程。車隊營運與措施資料為合成資料；EIA 價格是實際取得的公開觀測，保留來源標籤。缺少歷史可取得時間證據時，公開價格只用於回溯比較。

## 已驗證的結果與控制

完整合成情境的修訂版結果為 **8.210096 MPG**，採用相同配對窗口的 **62,852.700212 公升**與 **219,385.511611 公里**，配對時間覆蓋率為 **99.94914%**。這些是可重現的情境結果，不是真實商業車隊的營運成效；本流程的重點是把耗用、購油、庫存、可取得時間與後續措施證據分開並可追溯。

[隔離環境重建驗證](validation/rebuild_report.json)顯示 **26 張 canonical 資料表的邏輯內容一致**，**28 個生成來源檔逐位元一致**；只改變 seed 時，分析結果會隨之改變，品質規則仍通過。[最終原始碼 CI](https://github.com/JacobCCMorgan/da-e01-fuel-efficiency-analytics/actions/runs/40229112753) 在 commit `e0992b650a1686bd19dd50b5950b923be97ab6e0` 通過 **103 項測試、零跳過**，並透過 PostgreSQL **16.15**／HTTP／DuckDB 重建全部 **1,800 趟行程**。交付資料庫來自較早通過完整驗證的 run `40227233022`、commit `55b6831eaa7f44849aad39537288654ba04cb701`；[完整比對](validation/ci_full_canonical_comparison_40227233022.json)確認其 26 張表內 **330 個 canonical 欄位的值**與本機參考版本一致。[採用紀錄](validation/database_adoption.json)保存該資料庫的精確雜湊，並將本機接收紀錄與報告執行證據分開標示。


[最終原始碼的完整資料庫比對](validation/ci_final_canonical_comparison_40229112753.json)也已通過：交付資料庫與最終 CI 產生的資料庫，26 張表的全部 330 個 canonical 欄位值一致。

## 這個專案回答什麼

![燃油效率與量測覆蓋率](outputs/figures/01_efficiency_coverage.png)

| 問題 | 分析方式與可核對資料 |
| --- | --- |
| 同樣工況下，燃油效率是否改變？ | 配對燃油／里程窗口、可用量測覆蓋率、同車同任務前期值與合格同儕 |
| 購油支出為何改變？ | 稅費折扣口徑、退款、價格與數量拆解、獨立標示的市場參考價 |
| 油箱的物理收支是否支持耗用結果？ | 同油箱期初期末量測、加油與其他異動、不確定範圍及 ECU 對帳 |
| 報告是否被採用，後續是否能比較？ | 採用狀態、成熟觀察期、覆蓋門檻與按基準任務組合標準化的描述性比較 |

下載 [互動 HTML 報告](outputs/dashboard.html) 後可離線開啟，切換單一報告版本並篩選租戶、車輛、週與資料品質；也可匯出選取明細。GitHub 的檔案預覽不會執行互動頁面。Notebook 展示 SQL 查詢與結果，[中文圖表講解](docs/chart_walkthrough_zh.md) 說明每張圖應如何解讀。

## 從專案原始碼重建

已測試環境使用 Python 3.12。在 repository 根目錄執行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m fleet_fuel.cli run --profile full --operational snapshot
python -m pytest -q
```

完整流程會生成一致的虛構營運情境，啟動本機 HTTP 事件服務，透過分頁取得事件，完成驗證、資料庫建置、SQL 分析、報告與匯出。已凍結的 EIA 來源可供離線重跑；安裝依賴後，預設執行不需使用者提供資料、API 金鑰或 PostgreSQL 服務。

較短的工程檢查可使用：

```bash
python -m fleet_fuel.cli run --profile smoke --operational snapshot --skip-report
```

`smoke` 只觀測固定的 100 趟行程，但保留完整財務與庫存控制資料；低覆蓋是設計的一部分，不能用它重現完整分析指標。切換 profile 會重建目標目錄內的生成資料與成果；如要保留完整版，先使用另一份 checkout 或工作副本。

[執行手冊](docs/runbook.md) 另提供分階段指令、PostgreSQL 模式、來源更新、Notebook 執行與失敗復原。測試紀錄、品質報告與 manifest 才是實際執行證據；設定完成的 CI 不等於已成功執行。

## 端到端流程包含什麼

- 有分頁、快照游標、重複投遞、重試、斷點與拒收紀錄的本機 ELD 事件服務。
- 可原子寫入、拒絕既有鍵值被改寫、提供變更游標與一致快照擷取的 PostgreSQL 來源介接；另有獨立可跑的凍結快照模式。
- 26 張資料表、330 個欄位的版本化定義，包含租戶隔離、歷史有效期間、缺值狀態與來源追溯。
- 計數器分段、單位轉換、相同時間分母、歷史可取得時間與獨立對帳。
- DuckDB、Parquet、CSV、JSONL、七張分析圖、離線互動報告與可執行 Notebook。
- 手算案例、異常注入與整合測試；驗證答案不當成分析輸入。

EIA 使用的是官方 HTTPS **檔案下載**，沒有宣稱呼叫 EIA API。本機事件服務承載合成情境，不是實際 ELD 廠商端點。完整 PostgreSQL 流程已在遠端完成驗證，交付資料庫直接採用該建置成果；本機快照路徑仍可獨立重建，canonical 結果一致。詳見[環境執行狀態](docs/runbook.md#execution-status)。

## 三種報告版本不能混加

| 版本 | 截止時間 | 市場價格用途 |
| --- | --- | --- |
| 初版 `initial` | 週結束後 48 小時 | 使用當時已知的模擬價格 |
| 修訂版 `revised` | 週結束後 7 天 | 同樣遵守歷史可取得時間，可納入後到的營運修正 |
| 回溯版 `retrospective` | 已保留來源的最新可取得時間 | 可納入 2026 年取得的 EIA 歷史觀測 |

週界線使用 `America/Los_Angeles`，資料庫保存 UTC 時間；夏令時間週不假設一定是 168 小時。先套用資料可取得時間，再選擇當時最新版本。EIA 的觀測日期不等於已驗證的歷史發布時間。

## 檔案導覽

| 位置 | 內容 |
| --- | --- |
| `src/fleet_fuel/`、`sql/` | 可執行的生成、介接、清理、分析、驗證及報告程式 |
| `contracts/`、`config/` | 欄位定義、schema、資料範圍與情境參數 |
| `data/public/` | 公開來源原檔、取得紀錄、雜湊與價格快照 |
| `data/raw/`、`data/staged/` | 生成的來源資料與接收後事件 |
| `data/DA-E01.duckdb` | 可重建的分析資料庫 |
| `data/normalized/`、`data/derived/` | Parquet 與衍生資料 |
| `outputs/` | 互動報告、圖表、CSV 與結構化報告內容 |
| `validation/` | 獨立預期答案、品質檢查與需求追蹤 |
| `docs/`、`notebooks/`、`tests/` | 說明文件、逐步分析與測試 |

大型可重建的原始資料與資料庫可能透過 Git 原始碼以外的交付包提供；保留的生成程式、來源快照與建置入口可重建它們。實際交付內容以該版本的交付清單為準，不由目錄說明推定上傳完成。

## 如何解讀成果

車隊 MPG 使用合格燃油與里程總量的比值。同儕比較先限制租戶、車型、任務、週與覆蓋；市場差額不代表可實現的節省；庫存差異可能來自覆蓋、校正或未知異動。措施前後即使標準化任務組合，仍只能提供描述性比較，不能宣稱因果節省或真實客戶採用。

此作品驗證指定情境中的工程與分析行為，不代表已驗證真實車隊成效、正式訊號校正或取得廠商認證的 J1939／OBD 解碼能力。詳細規則請參考[指標定義](docs/metrics.md)、[合成資料設計](docs/simulation.md)、[來源紀錄](docs/sources.md)及[架構決定](docs/architecture.md)。

程式碼採 [MIT](LICENSE)；原創虛構 sample data 採 [CC0 1.0](data/LICENSE.md)。EIA 外部資料保留原來源及適用條件。
