# tmdl-lens

Automated documentation generator for Power BI projects.

Reads TMDL files from a folder of `.pbip` reports and generates structured HTML or Markdown documentation for each one - covering data sources, tables, measures, relationships, M parameters, security roles, and calculation groups.

Runs as a standalone Windows desktop app or as a headless command-line tool. Output can be HTML (opens in any browser) or Markdown (README.md for GitHub). A live file watcher regenerates documentation automatically on every save.

---

## What it documents

See a [real example output](sample/README.md) generated from the included sample report.

Each generated README includes:

- **Data Sources** - connector type and resolved source detail for every query. 30+ Power Query connector functions have dedicated labels (SQL, Dataflows, SharePoint, Excel, OData, Azure Blob/Table/Data Lake storage, Databricks, Snowflake, Salesforce, Oracle, PostgreSQL, SAP HANA, and more); any connector without a dedicated label is still auto-detected from the query and shown with its namespace and function for manual labelling.
- **Table Details** - table type, source detail, and column list
- **Measures** - full DAX (optional), display folder, and format string
- **Relationships** - cardinality, cross-filter direction, and active/inactive state
- **M Parameters** - current value and which source expressions reference each parameter
- **Security Roles** - static and dynamic RLS rules per table, flagged by type
- **Calculation Groups** - calculation items with DAX and ordinal order
- **Model Statistics** - table, column, measure, and relationship counts

---

## Installation

### Option A - Command line (PyPI)

Requires Python 3.12+.

```
pip install tmdl-lens
tmdl-lens --reports-folder C:\path\to\reports --format md
```

The base package installs the dependency-free `tmdl-lens` command and nothing else. For the desktop GUI, install the GUI extras and launch it as a module:

```
pip install "tmdl-lens[gui]"
python -m tmdl_lens.app
```

### Option B - Standalone executable

Download the latest `tmdl-lens.exe` from the [Releases](https://github.com/nox-magistralis/tmdl-lens/releases) page. No Python or pip required - just run the `.exe` directly.

A `config.json` file will be created alongside the executable on first run to store your settings.

> **Note:** Windows may show a SmartScreen warning on first run. Click **More info** then **Run anyway**. This is expected for unsigned applications.

### Option C - Run from source

Requires Python 3.12+.

```
git clone https://github.com/nox-magistralis/tmdl-lens.git
cd tmdl-lens
pip install -r requirements.txt
python main.py
```

---

## Usage

1. Launch the app
2. Under **Configure**, set the **Reports folder** to the root of your `.pbip` projects
3. Set an **Output folder** if you want READMEs written somewhere other than next to each `.pbip`
4. Press **Run Now** to generate documentation for all reports
5. Enable **Watch for TMDL changes** to auto-regenerate on every save

If no output folder is set, each `README.md` is written next to its `.pbip` file. If a separate output folder is set, each report gets its own named subfolder inside it - for example `docs/SalesReport/README.md`, `docs/FinanceReport/README.md` - so multiple reports never collide.

Optional documentation metadata (owner, team, refresh schedule) is set in the **Configure** tab and stored in `config.json` next to the app. Values left blank are omitted from the generated output.

By default the app skips reports whose TMDL files and documentation settings have not changed since the last run - each report is hashed, and only reports that actually moved are regenerated. Turn this off with **Skip reports with no TMDL changes** in **Configure**.

On startup the app validates the config and logs a warning for a missing or empty reports folder, a missing output folder, a watch debounce outside 1-300, or an output format other than `html` or `md`.

### Command line

The `tmdl-lens` command runs the same documentation pipeline without the GUI:

```
tmdl-lens --reports-folder C:\path\to\reports
tmdl-lens -r C:\path\to\reports -o docs --format html --overwrite
```

Run `tmdl-lens --help` for the full list of options. Exit codes: `0` when everything succeeds, `1` when a report fails or the reports folder does not exist, and `2` when `--reports-folder` is missing. Settings can be read from a `config.json` with `--config` (CLI flags override file values) - this is also what makes `--skip-unchanged` persist its content hashes between runs.

---

## Requirements

The command-line core has no third-party dependencies (pure Python standard library). The desktop GUI adds two packages:

| Package | Version | Used for |
|---|---|---|
| customtkinter | >= 5.2.0 | GUI |
| watchdog | >= 4.0.0 | file watcher |

Python 3.12 or later required when running from source.

---

## Development

```
pip install -r requirements-dev.txt
python -m pytest
```

`requirements-dev.txt` adds dev-only dependencies (pytest, pyinstaller) on top of the base `requirements.txt`. The test suite runs against the bundled sample report and covers the TMDL parser, source resolution, config validation, and README/HTML generation.

---

## Project structure

```
tmdl-lens/
  main.py                   entry point (desktop GUI)
  pyproject.toml            package metadata and CLI entry point (PyPI)
  requirements.txt          GUI dependencies (source installs)
  requirements-dev.txt      dev-only dependencies (pytest, build, twine, pyinstaller)
  pytest.ini
  tmdl_lens/
    app.py                  CustomTkinter UI
    cli.py                  command-line interface
    pipeline.py             documentation generation pipeline
    tmdl_parser.py          TMDL file parser
    source_resolver.py      M expression source resolver
    readme_generator.py     README markdown generator
    watcher.py              file watcher (watchdog)
    config.py               app settings + documentation metadata (config.json)
    version.py              single source of the app version
  sample/                   sample .pbip project for testing
  tests/                    pytest suite
```

---

## Author

**Marcin Mozol** - [github.com/nox-magistralis](https://github.com/nox-magistralis)

---

## License

MIT - see [LICENSE](LICENSE)
