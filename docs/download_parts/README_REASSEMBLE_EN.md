# Restore the DA-E01 archive

The Google Drive upload connection has a 100 MiB per-file limit. Each large ZIP is therefore delivered as five raw byte parts, each at most 90 MiB. The original release ZIP remains unchanged. These are transport parts; individual parts cannot be opened as ZIP files.

Download all five numbered parts, the matching `.parts.json` manifest and `reassemble_archives.py` into one local folder. Python 3 is the only requirement; no packages need to be installed.

For the data and database archive:

```bash
python reassemble_archives.py DA-E01_v1_data.parts.json
```

For the complete project archive:

```bash
python reassemble_archives.py DA-E01_v1_complete.parts.json
```

Use `python3` instead of `python` if required by your operating system. The script checks every part's size and SHA256, assembles the ZIP in the declared order, and checks its complete size and SHA256 against the original frozen archive. It refuses to overwrite a different existing file. Open or extract the reconstructed `.zip` only after the success message.

The complete archive already includes the data and source. Download either the complete archive or the source plus data archives; downloading both complete and data repeats the same data unnecessarily.

