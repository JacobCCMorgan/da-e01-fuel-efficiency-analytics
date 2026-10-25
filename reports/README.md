# Analysis reports

The Chinese report contains the seven analysis figures and the full interpretation guide. The English summary selects the key findings, comparison rules and follow-up evidence. Both use the same structured numerical source, `outputs/report_content.json`.

## Rebuild

From the project root, with the locked Python environment installed:

```bash
python scripts/build_documents.py
```

This creates both DOCX files from the structured results and existing figures. Generate analysis outputs first if they are absent. To export PDFs with LibreOffice installed:

```bash
python scripts/build_documents.py --pdf
```

Install the Noto Sans CJK TC regular and bold fonts for the Chinese document. PDF export also requires LibreOffice (`soffice`) on the system path. Font substitution can change pagination; render and inspect all pages before publishing regenerated reports.

The release PDFs were checked page by page: nine Chinese pages and three English pages, with readable Chinese text, unclipped figures and tables, and no blank pages. `document_validation.json` records checksums for this inspected version. A regenerated DOCX/PDF may have different file metadata even when its content is unchanged.

Operational records and follow-up cases are synthetic. Public EIA observations remain separately identified market context. These reports do not claim verified real-world savings.
