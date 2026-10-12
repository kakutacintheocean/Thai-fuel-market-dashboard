# Power BI: 1-page "Thai Fuel Market" dashboard

A rendered preview of this layout (built from the real cleaned data, styled in
Thaioil's brand colors) is `dashboard_preview.html` in this folder. Use it as
the visual target. This guide reproduces it in actual Power BI Desktop.

**Glossary:** MoM (Month-over-Month) compares this month to the previous
month. YoY (Year-over-Year) compares this month to the same month one year
earlier. Both show up throughout the KPI cards, the growth chart, and the
bottom table.

## 1. Get Data

Run the pipeline first so the clean table exists:

```bash
python scripts/clean_fuel_data.py
```

In Power BI Desktop: **Get Data > Text/CSV** then select
`data/processed/fact_fuel_monthly.csv`.
(Alternative: **Get Data > ODBC** with the SQLite ODBC driver pointed at
`data/processed/fuel_market.db`, table `fact_fuel_monthly`. Only do this if
the SQLite ODBC driver is already installed; CSV needs nothing extra.)

In Power Query, set column types explicitly (Power BI sometimes guesses
`record_date` as text because of the `YYYY-MM-DD` format from pandas):
- `record_date` > **Date**
- `year`, `month` > **Whole Number**
- `quantity_million_litres` > **Decimal Number**
- `product`, `metric_type`, `source_file` > **Text**

Close & Apply.

## 2. Build a Calendar table (needed for YoY/MoM DAX)

`fact_fuel_monthly` only has months that exist in the source data, which
breaks `SAMEPERIODLASTYEAR`/`DATEADD`. Add a proper date dimension:

**Modeling > New Table:**

```DAX
Calendar =
CALENDAR(DATE(1986,1,1), MAX(fact_fuel_monthly[record_date]))
```

Then **Mark as Date Table** (Table tools > Mark as Date Table > pick the
`Date` column). Create a relationship `Calendar[Date]` (1) to
`fact_fuel_monthly[record_date]` (*).

## 3. Add the measures

Open `measures.dax` in this folder and paste each measure into
**Modeling > New Measure** one at a time (Power BI doesn't support pasting
multiple DAX measures at once). This gives you `Total Consumption (M Litres)`,
`Consumption YoY %`, `Consumption MoM %`, `Export Share of Consumption %`, and
the KPI-card label measures.

## 4. Color system

Two separate palettes, used for two different jobs, matching the HTML preview:

**Thaioil brand pair** (sampled from the official logo SVG) drives the UI
chrome: header bar, active nav pill, KPI accent numbers, buttons, badges.
| Role | Hex |
|---|---|
| Brand blue (primary, "growing/positive") | `#00518A` |
| Brand magenta (accent, highlights/CTA) | `#E01383` |
| Status red ("shrinking/negative", reserved, never reused as a series color) | `#E34948` |

**Validated categorical ramp** drives the 6-product line-chart legend (chosen
for colorblind-safe adjacent contrast, independent of the brand pair since
two brand hues can't carry six distinct series identities):
| Product | Hex |
|---|---|
| Diesel | `#2A78D6` |
| Gasoline | `#EB6834` |
| Jet Fuel | `#1BAF7A` |
| LPG | `#EDA100` |
| Fuel Oil | `#E87BA4` |
| Kerosene | `#008300` |

## 5. Page layout (16:9, one page, no scrolling)

```
+---------------------------------------------------------------------+
| Thaioil-blue header bar: title + nav pills + date-range slicer      |
| "ความต้องการน้ำมันสำเร็จรูปไทยกำลังเปลี่ยนไปทางไหน"                   |
+--------------+--------------+--------------+------------------------+
| KPI: Total   | KPI: Fastest | KPI: Fastest | KPI: Export share %   |
| Consumption  | Shrinking    | Growing      |                        |
| + YoY        | Product +YoY | Product +YoY |                        |
+--------------+--------------+--------------+------------------------+
| Line chart: monthly consumption by product  | Donut: share of       |
| X = record_date (Calendar[Date])             | products shrinking    |
| Y = Total Consumption (M Litres)             | YoY (brand magenta    |
| Legend = product, filter metric_type =       | ring)                  |
| "Consumption"                                 +------------------------+
|                                               | Ranked list: product  |
|                                               | rows with growing /   |
|                                               | shrinking pill tags   |
+-----------------------------------------------+------------------------+
| Insight banner (brand gradient): names the shrinking products        |
+---------------------------------------------------------------------+
```

### KPI cards
Use **Card** visuals bound to the `KPI *` text measures in `measures.dax`, or
a **Card (new)** visual with:
- Field: `Total Consumption (M Litres)` / `Consumption YoY %`
- Conditional formatting on the YoY value font color: negative value uses
  `#E34948` (status red), positive value uses `#00518A` (brand blue).

### Line chart (consumption trend)
- Visual: **Line chart**
- X axis: `Calendar[Date]`, continuous
- Y axis: `Total Consumption (M Litres)`
- Legend: `fact_fuel_monthly[product]`
- Filter pane: `metric_type` is `Consumption`
- Data colors: the validated categorical ramp in section 4, assigned in that
  fixed order so it stays colorblind-safe.

### Donut: share of products shrinking YoY
- Visual: **Donut chart**
- Legend: `Is Shrinking` (from `measures.dax`)
- Values: count of products
- Data colors: "Shrinking" slice `#E34948`, "Growing" slice `#00518A`
- Center label: percentage of products currently shrinking

### Ranked product list
- Visual: **Table** or a matrix styled as rows, one per product
- Columns: product name, `Latest Month YoY % (by Product)` as a pill badge
  (conditional background `#E34948`/`10%` opacity for shrinking,
  `#00518A`/`10%` opacity for growing, text in the solid color)

### Insight banner
- A text box or Card visual with a brand-gradient background
  (`#00518A` to `#E01383`, 135 degrees) stating the business read in one
  sentence, e.g. "LPG, Jet Fuel, Diesel and Kerosene are shrinking
  year-over-year for 3+ consecutive months."

## 6. Slicer

Add a single **date range slicer** bound to `Calendar[Date]`, top-right of
the title bar, defaulted to the last 36 months so the page opens already
answering "what changed recently" instead of showing 40 years of noise.

## 7. Export as the single-page deliverable

**File > Export > Export to PDF** (one page, since this is a one-page report
with no extra pages added). This is the artifact to attach to the portfolio
alongside the `.pbix` file itself.
