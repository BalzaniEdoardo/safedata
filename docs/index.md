# Keeping a table of records safe

This documentation describes a workflow for maintaining a table of records, and safedata is the tool that makes one part of it work. The workflow makes it possible to edit the records consistently, keep track of every change together with a comment explaining it, and release final versions of the records, in a way that is safe and transparent to everyone involved.

It is meant for tables where preventing accidental edits or deletions is critical: observations, samples, inventory or measurements that several people add to and correct over months or years, and that others analyse. The tables it is designed for fit in a spreadsheet, from a few hundred to some tens of thousands of rows.

This page explains the reasoning behind the workflow. The other pages describe each step in practice.

## Records kept in the workbook that analyses them

A common setup is a single Excel file: one sheet holds the records, and the other sheets hold the pivot tables, charts and formulas that analyse them. To analyse, people sort and filter the records sheet. To add or correct records, they type or paste into the same sheet.

In that setup the records can change without anyone intending it:

- Sorting a selection of columns instead of the whole table reorders some values and not others, so values move to the wrong records.
- Pasting into a filtered sheet can write into rows that the filter hides.
- A value deleted or overwritten by accident looks like any other value.
- Copies of the file are made for safety or for a colleague (`records_final_v3.xlsx`), and it becomes unclear which one holds the correct records.

When a number looks wrong months later, the file cannot say who changed it, when, or what it was before.

## How the workflow separates the records from their analysis

The workflow keeps the records apart from everything that reads or changes them:

- **The records** are a plain text file, `data/records.csv`, with one line per record, kept in a folder whose history is managed by git (described below). Next to it, `data/schema.yaml` lists the columns, the type of each, and the values that are allowed.
- **Changes to the records** are made with `safedata edit`, which opens the records as a table in the browser. It checks every value against the schema while you type, and saving writes the file. It is the only part that changes `records.csv`.
- **The history** is kept by git, the most widely used version control system: a program that keeps every version of a set of files. Each time someone records a change, git stores what changed, who changed it, when, and a short description written by that person. Any earlier version of the records can be looked at or brought back, and a final version, for example the one used in a report, can be given a name so that it can always be retrieved exactly. How to do this in this workflow is explained in [Recording and reviewing changes with git](git.md).
- **The analysis** happens in Excel workbooks that load `records.csv` as a read-only table and reload it when asked. Sorting, filtering and formulas in a workbook never touch the records file.

## What this workflow guards against

- **Changes made while analysing.** A workbook only reads the records, so sorting, filtering or pasting in it cannot alter them.
- **Invalid values.** A date in the wrong format, a site that is not in the list, or an empty required value is refused when it is typed, and checked again before every change is recorded in the history.
- **Changes that nobody reviewed.** Before a change enters the history, git shows exactly which records changed and how: one changed line per changed record.
- **Lost history.** Every version is kept. Who changed a value, when, and what it was before can be looked up, and a mistaken change can be undone.
- **Two people editing at the same time.** When their changes are combined, changes to different records, or to different values of one record, are merged automatically. When both changed the same value, git stops and shows both versions, so neither is lost without someone deciding.

## The safedata philosophy: a small tool for each goal

Each goal of the workflow is handled by a tool that does that job and nothing else:

- **Editing the records:** safedata, which checks every change against the schema and writes the records file.
- **Version control:** git, which keeps the history and shares changes between people.
- **Analysis:** Excel, or any other program that reads a CSV file, which reads the records and never writes them.

Where an established tool already does a job well, the workflow uses it, and safedata covers only what is missing. This keeps safedata small, and each part can be understood, checked or replaced on its own.

## Contents

1. [Setting up a computer and a copy of the dataset](setup.md)
2. [How the records are stored and checked](records.md): the key, the sorted file, the schema.
3. [Editing records with safedata edit](editing.md)
4. [Recording and reviewing changes with git](git.md)
5. [Analysing the records in Excel](excel.md)
