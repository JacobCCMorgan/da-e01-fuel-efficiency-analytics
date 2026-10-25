# 還原 DA-E01 完整封存檔

Google Drive 上傳連線的單檔上限為 100 MiB，因此大型 ZIP 以五個編號分段檔交付，每段不超過 90 MiB。原始 ZIP 內容與校驗碼不變，分段檔本身不能直接解壓縮。

請將同一組五個 `.part001` 至 `.part005`、對應的 `.parts.json` 及 `reassemble_archives.py` 下載至同一個本機資料夾，依上方指令執行。程式會依序檢查每段、還原 ZIP，並核對完整 ZIP 的 SHA256。出現成功訊息後即可解壓縮。

完整專案包已包含程式與資料；可選擇完整包，或選擇程式包加資料包。無須同時下載完整包與資料包。

```bash
python reassemble_archives.py DA-E01_v1_data.parts.json
python reassemble_archives.py DA-E01_v1_complete.parts.json
```

依下載的資料包選擇其中一行；完整專案包不需要另外下載資料包。系統需要時，將 `python` 改成 `python3`。
