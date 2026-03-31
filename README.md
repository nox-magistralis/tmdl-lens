# tmdl-lens

Automated documentation generator for Power BI projects.

Reads TMDL files from a folder of `.pbip` reports and generates a structured `README.md` for each one — covering data sources, tables, measures, relationships, M parameters, security roles, and calculation groups.

Runs as a standalone Windows desktop app with a live file watcher that regenerates documentation automatically on every save.

---

## What it documents

See a [real example output](sample/README.md) generated from the included sample report.

Each generated README includes:

- **Data Sources** - connector type and resolved source detail for every query, covering 30+ connectors including SQL, Dataflows, SharePoint, Excel, OData, Azure storage, Fabric, Databricks, Snowflake, Salesforce, and more. Unknown connectors are auto-detected and flagged for manual labelling.
- **Table Details** - table type, row count hint, and column list
- **Measures** - full DAX (optional), display folder, and format string
- **Relationships** - cardinality, cross-filter direction, and active/inactive state
- **M Parameters** - current value and which source expressions reference each parameter
- **Security Roles** - static and dynamic RLS rules per table, flagged by type
- **Calculation Groups** - calculation items with DAX and ordinal order
- **Model Statistics** - table, column, measure, and relationship counts

---

## Installation

### Option A - Run from source

Requires Python 3.12+.

```
git clone https://github.com/nox-magistralis/tmdl-lens.git
cd tmdl-lens
pip install -r requirements.txt
python main.py
```

### Option B - Standalone executable

Download the latest `tmdl-lens.exe` from the [Releases](https://github.com/nox-magistralis/tmdl-lens/releases) page. No Python or pip required — just run the `.exe` directly.

A `config.json` file will be created alongside the executable on first run to store your settings.

> **Note:** Windows may show a SmartScreen warning on first run. Click **More info** then **Run anyway**. This is expected for unsigned applications.

---

## Usage

1. Launch the app
2. Under **Configure**, set the **Reports folder** to the root of your `.pbip` projects
3. Set an **Output folder** if you want READMEs written somewhere other than next to each `.pbip`
4. Press **Run Now** to generate documentation for all reports
5. Enable **Watch for TMDL changes** to auto-regenerate on every save

If no output folder is set, each `README.md` is written next to its `.pbip` file. If a separate output folder is set, each report gets its own named subfolder inside it — for example `docs/SalesReport/README.md`, `docs/FinanceReport/README.md` — so multiple reports never collide.

Workspace metadata (owner, team, refresh schedule) is set under the **Metadata** tab and written to a `tmdl-lens.json` file inside the reports folder. Per-report overrides can be added directly in that file.

---

## Requirements

| Package | Version |
|---|---|
| customtkinter | >= 5.2.0 |
| watchdog | >= 4.0.0 |

Python 3.12 or later required when running from source.

---

## Project structure

```
tmdl-lens/
  main.py                   entry point
  requirements.txt
  src/
    app.py                  CustomTkinter UI
    tmdl_parser.py          TMDL file parser
    source_resolver.py      M expression source resolver
    readme_generator.py     README markdown generator
    watcher.py              file watcher (watchdog)
    config.py               UI config read/write (config.json)
    workspace_config.py     workspace metadata read/write (tmdl-lens.json)
  sample/                   sample .pbip project for testing
  tests/                    unit tests
```

---

## Author

**Marcin Mozol** — [github.com/nox-magistralis](https://github.com/nox-magistralis)

---

## License

MIT — see [LICENSE](LICENSE)
