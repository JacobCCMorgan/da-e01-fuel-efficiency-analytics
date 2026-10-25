# Fleet fuel efficiency and price variance

DA-E01 separates ECU fuel use, fuel purchases and inventory movements, then builds traceable vehicle-week metrics and reporting review candidates.

The revised dataset covers 3 synthetic tenants and 30 vehicles. It contains 810 vehicle-week rows, 219,386 paired kilometres and 62,853 litres of paired consumption. Fleet efficiency is 8.21 MPG with 99.9% paired-time coverage.

The workflow includes versioned input snapshots, temporal entity relationships, counter segmentation, independent reconciliation, SQL/Python analytics and an offline interactive report. Review thresholds identify cases for investigation; they do not prove waste or maintenance faults.

Official EIA observations are retrospective background where available. All vehicle operations and action-follow-up records are synthetic, and no real customer adoption or realized savings are claimed.

Outputs: [interactive report](../outputs/dashboard.html), [metric definitions](metrics.md), [Chinese chart walkthrough](chart_walkthrough_zh.md), [structured report](../outputs/report_content.json).
