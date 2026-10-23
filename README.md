# NSE Market Data Downloader

A beginner-oriented Python command-line project for acquiring four NSE India
market-data datasets, validating tabular results, and saving dated CSV files.

> **Important access limitation:** automated NSE access is disabled in
> `config.json`. The NSE page URLs below identify the requested datasets, but
> this project has not verified an explicitly permitted automated retrieval
> method or the actual data schema for those pages. Do not enable automated
> access until you have confirmed an authorized method and its response format
> and expected columns. This project does not bypass anti-bot controls,
> authentication, CAPTCHAs, rate limits, or other access controls.

No live NSE requests were made while building or testing this project. The
automated tests use mocked HTTP responses and local example data; passing tests
do **not** prove that live NSE retrieval works.

## What it does

- Defines the four requested NSE market-data page locations.
- Offers a command-line selection for all datasets or one individual dataset.
- Separates configuration, acquisition, validation, CSV storage, logging, and
  command-line execution into different modules.
- Uses an explicit request timeout and a bounded retry policy for transient
  failures.
- Rejects denied or rate-limited responses without retrying them.
- Accepts only non-empty JSON or CSV HTTP responses at the acquisition boundary;
  the current CLI only parses explicitly declared CSV. It does not treat HTML
  pages as data or guess the structure of a JSON response.
- Validates expected columns and non-empty data, and removes exact duplicate
  rows before saving.
- Uses deterministic dated filenames and refuses to overwrite a same-day file.
- Writes timestamped structured logs to disk and readable messages to the
  console.
- Continues attempting other selected datasets after one fails.

## Requested datasets

The following identifiers and page URLs are configured in
[`datasets.py`](src/nse_market_data_downloader/datasets.py):

| Identifier | NSE page |
| --- | --- |
| `top-gainers-losers` | <https://www.nseindia.com/market-data/top-gainers-losers> |
| `upper-band-hitters` | <https://www.nseindia.com/market-data/upper-band-hitters> |
| `volume-gainers-spurts` | <https://www.nseindia.com/market-data/volume-gainers-spurts> |
| `52-week-high-equity-market` | <https://www.nseindia.com/market-data/52-week-high-equity-market> |

These URLs are web pages, not a verified data API contract.

## Project layout

```text
nse-market-data-downloader/
|-- config.json
|-- main.py
|-- pytest.ini
|-- requirements.txt
|-- README.md
|-- SETUP.md
|-- src/
|   `-- nse_market_data_downloader/
|       |-- acquisition.py
|       |-- cli.py
|       |-- config.py
|       |-- datasets.py
|       |-- logging_config.py
|       |-- storage.py
|       `-- validation.py
`-- tests/
    |-- conftest.py
    |-- test_acquisition.py
    |-- test_cli.py
    |-- test_config.py
    |-- test_storage.py
    `-- test_validation.py
```

### Module responsibilities

- `config.py` loads and validates JSON settings, then resolves configured paths
  relative to `config.json`.
- `datasets.py` stores the supported identifiers and NSE page URLs.
- `acquisition.py` handles the HTTP boundary, retries, timeouts, response status,
  and content-type checks.
- `validation.py` checks caller-provided expected columns and non-empty data,
  and removes exact duplicate rows.
- `storage.py` creates dated CSVs from a validation result without overwriting
  existing output.
- `logging_config.py` configures console and structured file logging.
- `cli.py` connects those components and handles selection and per-dataset
  failures.
- `main.py` is the Windows-friendly script to run from the project folder.

## Set up in VS Code on Windows

Open the project folder in VS Code, then open a PowerShell terminal in that
folder. Create a virtual environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell prevents environment activation, allow it only for the current
terminal session and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

When activation works, the terminal prompt starts with `(.venv)`. To leave the
environment later, run `deactivate`. More setup guidance is also in
[`SETUP.md`](SETUP.md).

Dependencies are:

- `pandas` for tabular data and CSV parsing/writing.
- `requests` for HTTP requests.
- `pytest` for automated tests.

## Configuration

The project reads [`config.json`](config.json) by default:

```json
{
  "output_dir": "output",
  "logs_dir": "logs",
  "expected_columns": {},
  "request_timeout_seconds": 20,
  "max_retries": 3,
  "retry_backoff_seconds": 1,
  "automated_access_permitted": false
}
```

- `output_dir`: folder for CSV files. Relative paths are resolved from the
  configuration file's directory.
- `logs_dir`: folder for the application log, resolved the same way.
- `expected_columns`: map of dataset identifiers to lists of confirmed column
  names. It is empty because the actual NSE schemas have not been verified.
  Do not add guessed headers.
- `request_timeout_seconds`: timeout for each HTTP request.
- `max_retries`: number of retries after the initial request. The loader allows
  values from 0 through 5.
- `retry_backoff_seconds`: base delay between transient retries. Delay grows
  exponentially with each retry.
- `automated_access_permitted`: remains `false` unless an explicitly permitted
  automated retrieval method has been confirmed.

The CLI will not save a dataset unless its expected columns are configured.
Changing the permission flag alone does not verify that the access method or
schema is authorized.

## Run the command line

From the project directory in the activated virtual environment:

```powershell
python main.py --help
```

Download all configured datasets (the default selection):

```powershell
python main.py
```

Choose one dataset by identifier:

```powershell
python main.py --dataset top-gainers-losers
python main.py --dataset upper-band-hitters
python main.py --dataset volume-gainers-spurts
python main.py --dataset 52-week-high-equity-market
```

Supply a trading date for the filename:

```powershell
python main.py --dataset upper-band-hitters --date 2026-10-23
```

The default date is the computer's local date. To use a configuration file
elsewhere, provide its path:

```powershell
python main.py --config C:\path\to\config.json --dataset all
```

**Current expected behavior:** with the checked-in configuration, acquisition
stops before a network request because automated access is disabled. The CLI
reports each selected dataset as failed and continues through the selection.
This is intentional and prevents accidental automated access before permission
is confirmed.

Exit codes:

- `0`: all selected datasets completed successfully.
- `1`: at least one selected dataset failed.
- `2`: configuration or logging could not be initialized.

## Acquisition, retries, and errors

Each request uses the configured timeout. Connection failures, timeouts, HTTP
408, and HTTP 5xx responses can be retried up to `max_retries` times, with
exponential backoff. HTTP 401, 403, and 429 responses are reported immediately
and are **not retried**. Other unsuccessful HTTP statuses also fail.

Empty bodies and unsupported content types are errors. The acquisition module
only accepts non-empty JSON or CSV media types; it does not consider an HTML
response a dataset. The CLI currently parses CSV only. JSON data is rejected
because no JSON schema/shape has been verified.

Expected acquisition, parsing, validation, and storage errors are reported for
each dataset. When processing `all`, one failure does not prevent attempts for
the remaining datasets.

## Validation, CSV filenames, and duplicate handling

Expected column names must be configured from an authorized, verified data
source. Validation rejects datasets with no rows, all-blank data, or missing
expected columns. Exact duplicate rows are removed and the number removed is
reported. Rows that differ in any column are retained.

Each successful CSV uses this pattern:

```text
<dataset-identifier>_<YYYY-MM-DD>.csv
```

For example, a hypothetical successful output would be named
`top-gainers-losers_2026-10-23.csv`. This filename example is not a claim that
the file exists or contains market data.

The deterministic daily filename is never silently overwritten. If the same
dataset/date file already exists, the save fails and leaves the existing file
unchanged; it does not create a confusing numbered duplicate. The CSV is first
written to a temporary file in the destination folder and only published after
the write completes. Failed writes do not leave a partial final CSV.

## Logging

The application creates the configured logs directory and writes
`nse-market-data-downloader.log` as JSON Lines, with timestamps, operation,
status, record counts, dataset identifiers, and useful error details. A concise
human-readable message is also written to the console. The log directory is
excluded from version control by `.gitignore`.

## Tests

Run the full automated suite:

```powershell
python -m pytest -q
```

Run with each test name shown:

```powershell
python -m pytest -v
```

Check Python syntax compilation:

```powershell
python -m compileall -q src tests
```

The tests use mocked HTTP responses and temporary local files. A shared pytest
fixture blocks unmocked `requests` HTTP calls. Test/example values are synthetic
fixtures only; they are not NSE market data and must not be presented as such.

The most recently completed test suite reported **64 passing tests**. Re-run the
commands above to verify the current workspace.

## Sample output and scheduling limitations

No sample market-data CSVs are included. They can only be created after a
permitted data-access method and real dataset schemas are confirmed and genuine
data is successfully retrieved and validated. Fabricated or guessed sample
market data would be misleading.

The application does not include an internal scheduler. If periodic execution
is later appropriate and permitted, Windows Task Scheduler can run the same
`python main.py` command at a selected time; scheduling does not grant permission
to automate data access.

## Assignment deliverables and remaining work

Present in the workspace: modular Python source, configuration, dependency
manifest, automated tests, and this README. The program has handling for four
separate dated CSV outputs, but no genuine output files are currently present
because no authorized live retrieval has been completed.

Before claiming a live downloader is operational, confirm the authorized access
method, allowed request frequency, response format, and expected columns for
each dataset. Keep automated access disabled until then.
