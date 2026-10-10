# Connecting an analysis workbook to the records

An analysis workbook holds a read-only copy of the records in one sheet, loaded with Power Query. Filters, sort order, formulas, pivots and charts go on or next to that sheet. **Data > Refresh All** reloads the records and re-applies the filter and sort order.

The analysis workbook can be saved anywhere, including outside the records folder. Neither git nor the records editor opens or changes it.

Requirements: Microsoft 365 Excel on Windows, or on Mac version 16.69 or later.

## One-time setup

1. **Find the path of the records file.** In the records folder, run `uv run safedata powerquery`. The first line of the output is the full path of `records.csv` on this computer. The rest is the query code used in step 4.
2. **Store the path in a cell named `DataPath`.** Type the path into a cell, for example on a sheet called `Settings`. Select the cell, type `DataPath` in the Name Box (left of the formula bar), and press Enter. Then select the same cell and use *Insert > Table*, without a header row. When several people share one workbook, each person changes only this cell.
3. **Create an empty query.** *Data > Get Data > Other Sources > Blank Query*. On Mac: *Data > Get Data (Power Query) > Blank query*.
4. **Paste the query code.** In the Power Query editor, open *Advanced Editor*, replace its content with the code from step 1, and click *Done*. Rename the query to `Records`.
5. **Load the query into a sheet.** *Close & Load To... > Table > New worksheet*, or choose an existing sheet. The sheet now contains an Excel table named `Records`.
6. **Keep filter and sort order on refresh.** Click inside the table. On Windows, open *Table Design > External Table Data > Properties*; on Mac, *Table > Refresh options*. Tick **Preserve column sort/filter/layout** and **Preserve cell formatting**. Optionally tick *Refresh data when opening the file*.

If Excel reports a *Formula.Firewall* or privacy-level error, open *Data > Get Data > Query Options > Privacy* (Windows) or *Preferences > Privacy* (Mac). Either set both data sources to *Organizational*, or choose *Ignore the Privacy Levels*.

## Loading the latest records

1. Get the latest commits into the records folder (`git pull`, or the pull/sync button of your git client).
2. In Excel, click **Data > Refresh All**.

Filters, sort order, formulas, pivots and charts are unchanged after the refresh.

The query reads the `records.csv` file in your copy of the repository as it is on disk. Edits saved in the records editor but not yet committed are included, and so is any checked-out branch. To analyse only committed records, refresh when `git status` shows no changes to `data/records.csv`.

## Formulas and pivots that keep working when rows are added

- **Refer to table columns, not cell ranges.** `=AVERAGEIFS(Records[value], Records[site], "North")` includes new rows after a refresh. `=AVERAGE(G2:G201)` does not.
- **Add calculated columns inside the table.** A formula column added at the right edge of the `Records` table, such as `=[@value]*2`, is filled in for new rows on each refresh.
- **Do not type values into the `Records` sheet.** The next refresh overwrites them. Change records in the records editor.
- **Base pivot tables on the `Records` table.** *Refresh All* updates them together with the table.
- **After a schema change, replace the query code.** When the maintainer adds or renames a column, run `safedata powerquery` again and paste the new code into the Advanced Editor.

## Loading the records in Python

```python
import safedata
df = safedata.load("/path/to/records-folder")  # pandas DataFrame with typed columns
```
