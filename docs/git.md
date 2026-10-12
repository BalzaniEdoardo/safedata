# Recording and reviewing changes with git

Saving in the editor changes `records.csv`, but it does not record the change in the history. That step is done with git, the version control system that keeps the history of the dataset. This page explains the few git operations the workflow uses, the programs that make them easier, and what happens when several people change the records at the same time.

## The words git uses

| Word | Meaning |
|---|---|
| **repository** | the dataset folder together with its complete history |
| **add** (or **stage**) | choosing which changed files go into the next commit; graphical programs call it *Stage* |
| **commit** | one recorded change: what changed, who made it, when, and a message describing it; also the act of recording it |
| **push** | sending your commits to the shared copy of the repository (for example on GitHub), so others can get them |
| **pull** | getting the commits others have pushed, and combining them with yours |
| **merge** | combining two sets of changes made at the same time; a pull does this when needed |
| **tag** | a name given to one version, for example the one used in a report |

## The everyday cycle

1. **Get the latest version** before you start, so you edit the current records: `git pull`.
2. **Edit and save** with `safedata edit`.
3. **Look for possible duplicates** with `safedata audit-duplicates`, which lists records that look like the same entry written slightly differently (see [Finding entries that are only similar](records.md#finding-entries-that-are-only-similar)). Correct or delete a record with `safedata edit` where needed.
4. **Review what changed.** Your git program shows the records you changed, one line per record; check that they are the changes you meant.
5. **Add** `data/records.csv`, then **commit** it with a message that says what you changed and why.
6. **Push**, so your colleagues get it.

On the command line, steps 3 to 6 are:

```sh
safedata audit-duplicates
git diff --word-diff data/records.csv
git add data/records.csv
git commit -m "Correct site of record 12: North, not South (field sheet 2024-03-15)"
git push
```

Committing is a separate, deliberate step on purpose. Before a change enters the history, a person looks at exactly what changed and writes down why. Months later, the message is often the only explanation of why a value is what it is, so it is worth writing it for a colleague who was not there.

## Programs for working with git

All of the above can be done with buttons instead of commands. Any program that works with git works with the dataset, because the dataset is an ordinary git repository.

- **git gui** shows the changed files and lines, lets you choose what to commit, write the message, and push. Start it with `git gui` in the dataset folder.
- **gitk** shows the history: every commit with its author, date, message and changes. Start it with `gitk` in the dataset folder, or `gitk data/records.csv` for the history of the records only.
- Both come with Git for Windows. On macOS and Linux they are sometimes packaged separately, for example `brew install git-gui` on macOS with Homebrew.
- **Visual Studio Code** has git built in: the *Source Control* view shows what changed and commits it, and the *Timeline* view of a file shows its history.
- Many other programs are listed at [git-scm.com/downloads/guis](https://git-scm.com/downloads/guis).

## Reading the history

The history is easiest to read in a graphical program, such as those listed [above](#programs-for-working-with-git):

- In **gitk**, started with `gitk data/records.csv` in the dataset folder, the top panel lists the commits that changed the records, newest first, with author and date. Clicking a commit shows its message and the lines it changed. To compare two commits, click the first one, then right-click the second and choose *Diff this -> selected*. When there are changes not yet committed, they appear at the top of the list as *Local uncommitted changes*, and can be compared with any commit in the same way.
- In **Visual Studio Code**, open `records.csv` and use the *Timeline* view, which lists the commits that changed it; clicking one shows its changes side by side.

On the command line, the same information is available with:

```sh
git log -p --word-diff data/records.csv      # every change, with the changed cells marked
git log -L '/^42,/,+1:data/records.csv'      # the history of record 42 only
git blame data/records.csv                   # the last commit that changed each record
```

With `--word-diff`, git marks each changed cell inside the line, so a corrected value shows as `[-1.5-]{+42+}`: the old value between `[-` and `-]`, the new one between `{+` and `+}`. safedata sets this up, so git treats each cell of the CSV as one word.

## How safedata sets up git to enforce a clean history

Git keeps the history of any text file, but it is unaware of the table's schema, which determines which entries are valid, and of the standard form in which the table is written. When installed, safedata instructs git to run the schema checks and write the file in standard form at each commit, as described in [What makes editing with safedata safe](editing.md#what-makes-editing-with-safedata-safe). It also instructs git to merge changes record by record, as described in the next section.

## When several people change the records at the same time

If you and a colleague both edited the records since your last pull, `git pull` merges the two sets of changes. safedata matches records by their `id`, so:

- changes to different records are combined;
- changes to different values of the same record are combined;
- new records added by both of you are all kept, and if both got the same number, one is renumbered with the next free number;
- if both of you changed **the same value** differently, git cannot know which is right. It stops and reports a **conflict**, so that someone decides;
- if the combined records **break the schema**, git also stops before recording the merge. This happens when each set of changes is valid on its own but not together: for example, when both of you added the same entry, each with its own number, so that it repeats one of the schema's [unique entries](records.md#entries-that-must-not-repeat).

### Resolving a conflict

When there is a conflict, the pull prints which records are affected and what to do, for example:

```
safedata: record 12 in data/records.csv changed differently on both sides.
Each is marked with git conflict markers (<<<<<<< ======= >>>>>>>), one record per block.
To resolve, in the dataset folder /Users/maria/Documents/records:
  1. keep one version of each record: in your git tool's conflict view, in a text editor
     (keep one line per block and delete the marker lines), or with `safedata edit`;
  2. review the result and stage it:  git add data/records.csv
  3. finish the merge:                 git commit
To cancel the merge instead:  git merge --abort
```

In `records.csv`, each conflicting record then appears twice, your version and the incoming one:

```
<<<<<<< local
12,2024-03-15,North,survey,Maria Rossi,7,true,
=======
12,2024-03-15,North,survey,Maria Rossi,8,true,
>>>>>>> incoming
```

Choose one version of each record in any of these ways:

- in your git program's conflict view;
- in a text editor, keeping one of the two lines and deleting the three marker lines;
- with `safedata edit`, which detects the conflict and shows both versions of each record side by side, with the differing values highlighted. Choosing a version and writing the file is all it does.

Then review the result, and finish the merge with `git add data/records.csv` and `git commit`. A file that still contains conflict markers cannot be committed.

### Fixing combined records that break the schema

When the combined records break the schema, the pull lists the problems, for example:

```
safedata: new record 3 was renumbered because that number was already taken
safedata: the changes to data/records.csv were combined, but together they break the schema:
  - Line 5 (record 4): date, site (2024-03-15, North) is the same as on line 4 (record 3); together, these columns must differ between records
To resolve, in the dataset folder /Users/maria/Documents/records:
  1. fix the records listed above with `safedata edit` (for two records that repeat
     each other, correct one or delete it);
  2. review the result and stage it:  git add data/records.csv
  3. finish the merge:                 git commit
To cancel the merge instead:  git merge --abort
```

Here both people recorded an observation at the North site on 15 March 2024, and the incoming one was renumbered to 4. The file contains all the combined records, without conflict markers. Open it with `safedata edit`, correct or delete one of the two records, save, and finish the merge with `git add data/records.csv` and `git commit`.

## Marking a final version

When a version of the records is final, for example the one used for a report or a publication, give it a name with a tag, and push the tag so that your colleagues get it too.

In **gitk**, right-click the commit and choose *Create tag*, then enter the name and, if offered, a message. To push it, use *Remote > Push* in **git gui** with *Include tags* ticked. On the command line:

```sh
git tag -a 2024-annual-report -m "Records used for the 2024 annual report"
git push origin 2024-annual-report
```

The tagged version can be retrieved exactly at any later time, whatever changed after it, so an analysis can always be repeated on the same records:

```sh
git show 2024-annual-report:data/records.csv > records-2024-annual-report.csv
```

## Protecting the shared copy

In a copy set up with `safedata install`, no change can be committed without being checked. Two routes remain around this check, both outside a set-up copy:

- skipping the check deliberately, with `git commit --no-verify`;
- editing `records.csv` directly on GitHub's website, which never passes through anyone's copy.

If the repository with the records is hosted on GitHub, a faulty edit that arrives by either route is detected by an automated validation, which runs on every change pushed to GitHub and marks a failing change as such. It is also possible to enforce the check, so that a failing change cannot enter the main version at all: in the repository's settings on GitHub, protect the main branch (*Settings > Branches > Branch protection rules*) and require the validation to pass (*Require status checks to pass*).

## Finding the change that introduced a problem

If an invalid record is found in the history, git can find the commit that introduced it. Give `git bisect` a version known to be bad (often the current one) and one known to be good, and let it run `safedata validate` on the versions in between:

```sh
git bisect start HEAD 2024-annual-report
git bisect run safedata validate
git bisect reset
```

Git tests versions by halving the range each time, so even a long history needs only a few steps. It reports the first commit where the check fails, with its author, date and message. `git bisect reset` returns the folder to where it was.
