# Connecting an analysis workbook to the records

Your analysis workbook keeps a **read-only, refreshable copy** of the records in one sheet. You never type into that sheet: you filter, sort, and build formulas, pivots and charts on top of it, and **Data > Refresh All** brings in the latest records while keeping your filter and sort.

Keep your analysis workbook **outside** the records folder (or anywhere you like). It is yours; the records repository never touches it.

You need Microsoft 365 Excel: Windows, or Mac version 16.69 or later.

## One-time setup

1. **Get the records path.** In the records folder, run `uv run safedata powerquery`. The first line it prints is the full path of `records.csv` on your computer, and the rest is the query code used in step 4.
2. **Add a `DataPath` cell.** In your workbook, put the path in a cell (on a `Settings` sheet, say), select that cell, type `DataPath` in the Name Box (left of the formula bar), and press Enter. Then use *Insert > Table* on that one cell, with no header row. If several people share the workbook, each person only changes this cell.
3. **Create the query.** *Data > Get Data > Other Sources > Blank Query* (on Mac: *Data > Get Data (Power Query) > Blank query*).
4. **Paste the code.** In the Power Query editor, open *Advanced Editor*, replace everything with the code printed in step 1, and click *Done*. Rename the query `Records`.
5. **Load it.** *Close & Load To... > Table > New worksheet* (or a worksheet you choose). That sheet now holds the records as an Excel table named `Records`.
6. **Keep filter and sort on refresh.** Click inside the table, then *Table Design > External Table Data > Properties* (Windows) or *Table > Refresh options* (Mac), and make sure **Preserve column sort/filter/layout** and **Preserve cell formatting** are ticked. Optional: *Refresh data when opening the file*.

If Excel shows a *Formula.Firewall* or privacy-level message: go to *Data > Get Data > Query Options > Privacy* (Windows) or *Preferences > Privacy* (Mac), and either set both sources to *Organizational* or choose *Ignore the Privacy Levels*.

## Daily use

1. Double-click **update** in the records folder's `launchers` folder to get the latest records.
2. In Excel: **Data > Refresh All**.

Your filters, sort order, formulas, pivots and charts stay as they were.

## Tips for a refresh-proof workbook

- **Point formulas at the table, not cell ranges.** `=AVERAGEIFS(Records[value], Records[site], "North")` keeps working as the number of rows changes, but `=AVERAGE(G2:G201)` doesn't.
- **Your own columns next to the table are fine.** Add a column at the right edge of the `Records` table with a formula like `=[@value]*2`. Excel fills it for new rows on every refresh.
- **Never type values into the records sheet.** A refresh overwrites them. To change the data, use **edit**/**submit**.
- **Pivots:** base them on the `Records` table, and they update with *Refresh All*.
- **If the column list changes** (the maintainer adds a column to the schema), run `safedata powerquery` again and paste the new code into the Advanced Editor.

## Without Power Query (Python users)

```python
import safedata
df = safedata.load("/path/to/records-folder")  # typed pandas DataFrame
```
