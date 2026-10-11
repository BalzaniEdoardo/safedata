# Setting up a computer and a copy of the dataset

Setting up takes three steps: installing the safedata tool, once per computer; getting a copy of the dataset; and installing safedata for that copy. A last, optional step checks that everything is in place.

## What you need

Only [git](https://git-scm.com). Everything else is installed by the safedata installer, and no administrator rights are needed.

On a new Mac, open *Terminal* and run `git --version` once. If git is missing, macOS offers to install it with Apple's Command Line Tools; accept, and wait for the installation to finish.

## Installing the safedata tool

This is done once per computer. Open a terminal and run the line for your system:

=== "macOS"

    In *Terminal*:

    ```sh
    curl -LsSf https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.sh | sh
    ```

=== "Windows"

    In *PowerShell*:

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.ps1 | iex"
    ```

=== "Linux"

    In a terminal:

    ```sh
    curl -LsSf https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.sh | sh
    ```

The installer installs [uv](https://docs.astral.sh/uv/), a tool that manages Python programs, if it is not already there, and then installs safedata with it. Everything goes into your home folder. When it finishes, open a new terminal, so that the `safedata` command is found.

Running the installer again later updates safedata to the latest version.

## Getting a copy of the dataset

The records live in a git repository, usually on GitHub. Each person works on their own copy of it, which git calls a **clone**.

- **To join an existing dataset,** ask for the address of its repository.
- **To start a new dataset,** create a repository from the template at [github.com/BalzaniEdoardo/template-records](https://github.com/BalzaniEdoardo/template-records) with GitHub's *Use this template* button. Then describe your columns in `data/schema.yaml` and replace the example records, as described in [How the records are stored and checked](records.md).

To make the copy, run the following in a terminal, with the address of the repository, or use the *Clone* function of your git program. The last word is the name of the folder that will hold the copy:

```sh
git clone https://github.com/your-team/your-records.git records
```

## Installing safedata for the records

This is done once per copy. In the dataset folder, run:

```sh
cd records
safedata install
```

This sets up the git safeguards described in [What makes editing with safedata safe](editing.md#what-makes-editing-with-safedata-safe): before a change is committed, the records are checked against the schema and written in standard form, and when two people's changes are combined, they are combined record by record.

These settings are stored inside the copy, in its hidden `.git` folder, and git does not pass them on when the repository is cloned. That is why every copy needs this step, including a second copy on the same computer. `safedata edit` also runs it when it starts, and running it again is harmless.

## Checking the installation

The dataset folder contains a script that checks whether the safedata tool is installed on this computer and whether this copy is set up. It changes nothing: it only reports what is missing and how to fix it. In the dataset folder, run:

=== "macOS"

    ```sh
    ./check-setup.sh
    ```

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy Bypass -File .\check-setup.ps1
    ```

    The `-ExecutionPolicy Bypass` part allows this one script to run: by default, Windows does not run scripts downloaded with a repository.

=== "Linux"

    ```sh
    ./check-setup.sh
    ```

When everything is in place, it prints:

```
This clone (/Users/maria/Documents/records) is set up: the git add-ons are configured for data/records.csv.
```

Otherwise it says what is missing. For example, in a copy where `safedata install` was never run:

```
This clone (/Users/maria/Documents/records) is not fully set up:
  - the git setting filter.safedata.clean is not set in this clone
  - the git setting merge.safedata.driver is not set in this clone
  - the git setting diff.safedata.wordRegex is not set in this clone
  - there is no pre-commit hook, so commits are not checked
Run `safedata install` in this folder to set up the git add-ons.
```

And on a computer where the tool itself is not installed, it says so and gives the installation command from [Installing the safedata tool](#installing-the-safedata-tool).
