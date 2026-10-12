# Analysing the records in Excel

An analysis workbook holds a copy of the records as an Excel table, loaded with Power Query, Excel's tool for importing data. The workbook only reads the records: refreshing it reloads `records.csv`, and filters, sorting, formulas, pivot tables and charts built on the table stay as they are. Nothing done in the workbook can change the records, which is what keeps analysis separate from editing (see [Keeping a table of records safe](index.md)).

These steps were tested with Microsoft 365 Excel on macOS. The Windows menus are taken from Microsoft's documentation and have not been tested yet.

## Setting up a workbook

This is done once per workbook. The workbook can be saved anywhere, including outside the dataset folder.

**1. Generate the query.** In a terminal, in the dataset folder, run:

```sh
safedata powerquery > query.txt
```

This writes `query.txt`, which contains the Power Query code that loads your copy of `records.csv` with the column types from the schema: dates as dates, numbers as numbers, yes/no values as TRUE/FALSE. The code contains the full path of the records file on your computer.

**2. Create the query in Excel.** Create an empty query and paste the generated code into it:

=== "macOS"

    1. On the **Data** tab of the ribbon, inside the Excel window, click **Get Data (Power Query)**. The *Data* menu in the menu bar at the top of the screen has only older import features, which do not work here.
    2. Choose **Blank query**. The Power Query editor opens.
    3. Open **Home > Advanced Editor**, delete its content, and paste the content of `query.txt`. Click **Done**. The preview shows the records, with the column types from the schema.
    4. Click **Close & Load**. Excel adds a sheet with the records as a table.

=== "Windows"

    1. On the **Data** tab, choose **Get Data > From Other Sources > Blank Query**. The Power Query editor opens.
    2. Open **Home > Advanced Editor**, delete its content, and paste the content of `query.txt`. Click **Done**. The preview shows the records, with the column types from the schema.
    3. Click **Close & Load**. Excel adds a sheet with the records as a table.

**3. Name the table.** Click a cell of the table. A **Table** tab appears in the ribbon (*Table Design* on Windows); its *Table Name* box shows the name Excel chose. Give it a short name, for example `Records`, which formulas will use.

## Getting the latest records

1. Get the latest version of the records into the dataset folder: `git pull`, or the pull button of your git program.
2. In Excel, on the **Data** tab, click **Refresh** (on Windows, **Refresh All**).

The table reloads with the current records. Filters, sorting, formulas and pivot tables built on it are kept.

The query reads `records.csv` as it is on disk. Edits saved with `safedata edit` but not yet committed are included, so to analyse only committed records, refresh when your git program shows no changes to `data/records.csv`.

## Writing formulas that keep working

- **Refer to table columns, not cell ranges.** `=AVERAGEIFS(Records[value], Records[site], "North")` includes new records after a refresh, while `=AVERAGE(G2:G201)` does not. Column names go inside the brackets without quotes; text values, such as `"North"`, need quotes.
- **Mind the order of arguments.** `AVERAGEIFS` takes the column to average first: `AVERAGEIFS(Records[value], Records[site], "North")`. `AVERAGEIF`, without the S, takes it last: `AVERAGEIF(Records[site], "North", Records[value])`.
- **Count records with** `=ROWS(Records)`, which grows when records are added.
- **Base pivot tables on the table.** Refreshing updates them together with the table.
- **Do not type values into the table.** The next refresh overwrites them. Change records with [`safedata edit`](editing.md).

## When the columns change

The query names every column and its type. When a column is added, renamed or removed, or its type changes, generate the query again with `safedata powerquery > query.txt`, open the query in Excel (*Data > Queries & Connections*, right-click it, *Edit*), and replace its code in the Advanced Editor.

Do the same if the dataset folder moves, since the query contains its path.

## Analysing the records in Python

The `safedata` package loads the records as a pandas table with the column types from the schema. It must be installed in the Python environment you analyse with, since the installer only provides the `safedata` command:

```sh
pip install git+https://github.com/BalzaniEdoardo/safedata
```

```python
import safedata

df = safedata.load("/path/to/records")  # the dataset folder, or any folder inside it
```
