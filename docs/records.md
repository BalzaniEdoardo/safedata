# How the records are stored and checked

The records are stored in a folder that has two important files: `data/records.csv`, which holds the records, and `data/schema.yaml`, which describes the columns and the values each one accepts. The folder also contains a few configuration files used by the tools, which you do not need to look at. This page describes what the two important files contain.

## The records are a table, written as text

The records must form a table: each row is one record, and each column is one property of it. Take this table as an example:

| date | site | category | observer | value | verified | notes |
|---|---|---|---|---|---|---|
| 1996-02-09 | West | survey | Omar Haddad | 5.79 | false | |
| 1996-03-13 | North | incident | Yuki Sato | 25.76 | true | access road closed |
| 1996-04-18 | South | survey | Maria Rossi | 66.13 | true | |

!!! tip "The columns are yours to choose"

    You decide which columns the table has, what they are called, and what kind of data each one holds: a date, a number, a category from a fixed list, a yes/no value, free text. The schema, described [below](#the-schema-which-values-are-allowed), is where you write these choices down.

In the folder, the table is stored as a CSV file, `data/records.csv`: plain text, with one line per row and the values in a row separated by commas. The first line holds the column names. The example table becomes:

```
id,date,site,category,observer,value,verified,notes
1,1996-02-09,West,survey,Omar Haddad,5.79,false,
2,1996-03-13,North,incident,Yuki Sato,25.76,true,access road closed
3,1996-04-18,South,survey,Maria Rossi,66.13,true,
```

The first column, `id`, is not part of the example table: safedata requires it in every dataset, as explained below.

!!! note "Why a plain text file and not a spreadsheet"

    Plain text is what makes the history readable. Because each record is one line, a change to a record is a change to one line, and git can show exactly which records changed and how. A spreadsheet file (`.xlsx`) is a compressed bundle: git can keep its versions, but it cannot show what changed inside it, so a reviewer would only see that the file is different.

    A CSV file can also be opened by almost any program, now and in the future, without safedata.

### The id column: a number that identifies each record

safedata requires one extra column in every table, called `id` in the template: a whole number that is different for every record. It gives each record a fixed identity, which safedata uses to keep the file sorted and to apply changes made by different people to the right records. New records get their number automatically. In the schema, this column is called the **key**.

## The schema: which values are allowed

The schema, `data/schema.yaml`, is used to validate the entries when the records are edited. Think of it as a way to constrain the format and content of each column: what kind of value it holds, whether it can be empty, and which values are allowed.

The schema has three parts: `key` names the [id column](#the-id-column-a-number-that-identifies-each-record), `unique_entries` lists the columns that must not repeat together (described [below](#entries-that-must-not-repeat)), and `columns` describes each column. An excerpt from the example dataset, without its comments:

```yaml
key: id

unique_entries:
  - [date, site]

columns:
  - name: id
    type: int
    required: true
    unique: true
    description: Record number, assigned automatically for new records.

  - name: site
    type: choice
    required: true
    choices: [North, South, East, West]

  - name: value
    type: float
    min: 0
    description: Measured value, if any.
```

### Supported column settings

`name` and `type` are required for every column, and `choices` for every `choice` column.

| Setting | For types | Meaning |
|---|---|---|
| `name` | all | **required**; the column name, exactly as in the first line of `records.csv` |
| `type` | all | **required**; one of the types below |
| `required` | all | `true` or `false` (default): whether the value can be empty |
| `unique` | all | `true` or `false` (default): whether two records can have the same value |
| `choices` | `choice` | **required** for `choice`; the allowed values, each listed once; the editor shows them as a dropdown |
| `min`, `max` | `int`, `float`, `date` | lowest and highest allowed value, both included |
| `description` | all | text shown when hovering over the column title in the editor |

The key column is always treated as `required` and `unique`, whether or not the schema says so.

The `type` setting accepts these types:

| Type | Values | Written in the file as |
|---|---|---|
| `int` | whole numbers | `42` |
| `float` | numbers | `3.5` |
| `date` | dates | `2024-03-15` |
| `bool` | yes/no | `true` or `false` |
| `choice` | one of `choices` | the choice, spelled as in the schema |
| `string` | any text on one line | the text |

### Entries that must not repeat

The id is different in every record by construction, so it cannot tell when the same entry has been recorded twice: for example, when two people add the same observation at the same time, and each copy gets its own number.

`unique_entries` closes this gap. It lists groups of columns whose values, together, identify an entry, so no two records may have the same combination. In the example dataset, the group `[date, site]` allows at most one record per site and day:

```yaml
unique_entries:
  - [date, site]
```

A record that repeats the values of a group is refused when the records are saved in the editor, when a change is committed, and when two people's changes are combined (see [When several people change the records at the same time](git.md#when-several-people-change-the-records-at-the-same-time)).

- A group can have any number of columns, and the list can have several groups, each on its own line.
- A record with an empty value in any column of a group is not checked against that group.
- The setting is required. To allow duplicates, write `unique_entries: []`.

#### Finding entries that are only similar

The check above catches entries whose values are identical. The same entry can also be recorded twice with slightly different text, for example `Trastevere` and `Trastevre`, or `Rome` and `rome`. To look for these, run in the dataset folder:

```sh
safedata audit-duplicates
```

For each group in `unique_entries`, it compares the text columns by similarity, ignoring upper and lower case and extra spaces, and requires the other columns of the group, such as dates and numbers, to be equal. With the group `[country, city, neighborhood, year]`, for example:

```
2 possible duplicate(s) among 5 records (similarity threshold 85%):
  - records 2 and 5: country, city, neighborhood, year (Italy, Rome, Monti, 2024 / Italy, rome, Monti, 2024), 100% similar
  - records 1 and 3: country, city, neighborhood, year (Italy, Rome, Trastevere, 2024 / Italy, Rome, Trastevre, 2024), 98% similar
These are only similar, not identical: check each pair, and correct or delete a record with `safedata edit` where it is the same entry.
```

A record for Trastevere in 2025 would not be listed, because the year differs. Similar records can be genuinely different, so this is a report for you to review: it changes nothing and blocks nothing. `--threshold` sets how similar the text must be, from 0 to 1 (default 0.85).

!!! note "When the columns change, update the schema"

    Every time a column is added, removed or renamed in `records.csv`, the schema needs to be updated too, so that the two files keep describing the same table.
