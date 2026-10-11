# Editing records with safedata edit

Records are added, corrected and deleted with the editor: a page in your web browser that shows the records as a table, checks every change against the schema, and writes the records file when you save. This page describes how to use it, and why records are changed this way rather than by editing the file.

## Opening the editor

Open a terminal, go to the dataset folder and start the editor. Replace the folder in the `cd` line with the place where your copy of the dataset is.

=== "macOS"

    Open *Terminal*, from Applications > Utilities or by searching for it with Spotlight (Cmd+Space), then run:

    ```sh
    cd ~/Documents/records
    safedata edit
    ```

=== "Windows"

    Open *PowerShell* from the Start menu, then run:

    ```powershell
    cd $HOME\Documents\records
    safedata edit
    ```

=== "Linux"

    Open your terminal application, then run:

    ```sh
    cd ~/Documents/records
    safedata edit
    ```

A tab opens in your browser with the records. Keep the terminal window open while you edit: the editor runs there. When you are done, close the terminal window or press Ctrl+C in it.

The page shows, under its title, the folder it is editing, so it is always clear which copy of the records you are changing.

## Making changes

- **To change a value,** type over it. Columns with a fixed list of values show a dropdown, and dates show a date picker.
- **To add a record,** click *Add record*. The new row appears at the top of the table, and it gets its `id` number when you save.
- **To delete a record,** click *Delete* on its row. The row is marked, and nothing is removed until you save; *Undo delete* takes the mark away.
- **To find records,** type in the filter box, which matches any column, or click a column title to sort by it. Filtering and sorting only change what the page shows, not the file.

Every edited cell is highlighted, and the line above the table counts the records changed, added and deleted since the last save. *Only edited rows* shows just those records, and *Discard edits* throws all unsaved edits away.

A value that breaks a rule of the schema is outlined in red, and a list above the table says what is wrong, for example:

> Record 12, date: 1980-01-01 is earlier than the earliest allowed date, 1990-03-26

Clicking a line in the list jumps to the cell. The edits cannot be saved until every problem is fixed.

## Saving

*Save to data/records.csv* checks all the edits against the schema once more and writes the records file. This is all it does: the change is not yet recorded in the history. Recording it, with a description of what you changed and why, is done with git, as described in [Recording and reviewing changes with git](git.md).

After saving, the page lists the records that differ from the last version recorded in the history, under *Saved but not yet committed*. The list is a reminder of what is waiting to be recorded.

If the records file changed after the page was opened, for example because you got your colleagues' latest changes in the meantime, your edits are applied to the current file, record by record. Edits to values that nobody else changed are saved normally. If one of your edits changes a value that was changed in the meantime, nothing is saved, and the page lists the values that clash, so that neither change is lost without you noticing. In that case, note your edits, reload the page to see the current records, and make the edits again where they are still needed; reloading discards all unsaved edits.

## What makes editing with safedata safe

`records.csv` is a text file, and nothing stops anyone from opening it in a text editor or a spreadsheet program and accidentally introducing invalid or badly formatted entries. safedata sets up safeguards that make sure every edit is correct before it is recorded in the change history. The first two act while you edit with safedata; the third also applies to edits made with any other program.

1. **The editor enforces the schema.** Each value is checked against the schema as soon as it is entered: dates must be real dates in the allowed range, numbers must be numbers, categories must be in the list. A value that does not conform is flagged as a mistake and explained, at the moment you still know what you meant to write, and *Save* stays disabled until every problem is fixed. Entries that repeat another record (see [Entries that must not repeat](records.md#entries-that-must-not-repeat)) are found when you save: the save is refused, and both records are named.

2. **Saved records are always written in a standard form.** The same records always produce exactly the same file:

    - rows sorted by `id`;
    - dates written as `YYYY-MM-DD`, for example `2024-03-15`;
    - yes/no values written as `true` or `false`;
    - numbers written in their shortest form, so `2.50` becomes `2.5`;
    - choices spelled as in the schema, so `north` becomes `North`;
    - UTF-8 text, with one kind of line ending.

    Without a standard form, the history fills with changes that are not changes. For example, if one person's program writes a value as `1.5` and another person's as `1.50`, the history records the value as changed, although it is the same number. Changes like this clutter the history and make it hard to tell meaningful edits to the content apart from changes in format.

3. **Git runs the same checks when a change is recorded.** `safedata install` sets up git so that, every time a change to the records is recorded in the history (in git's terms, *committed*), the file is checked against the schema and rewritten in standard form. A change with invalid values is refused, with the problems listed, and a change in another format is standardized on the way in. So even when `records.csv` is edited by hand, no invalid value and no format difference enters the history.

!!! warning "The third safeguard works only in a copy where safedata is set up"

    The git check runs only in copies of the dataset where safedata has been installed for the records with `safedata install`, because its settings are stored in each copy separately. In a copy that is not set up, a file edited by hand is recorded in the history without being checked or standardized. This is why every copy must be set up before anyone edits the records: see [Setting up](setup.md), in particular the sections on installing safedata for the records and on checking the installation.

    If the dataset is shared through GitHub, the check that runs there flags such a change when it arrives. And because every change is kept in the history with its author and date, the change that introduced a problem can always be found and corrected.
