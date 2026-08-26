# DataPrep-DSL — A Domain-Specific Compiler for Automated Data Preprocessing

A working compiler + web app for a small domain-specific language (DSL) that
describes data-cleaning pipelines. Write a script like:

```
LOAD "input.csv" AS df
DROP COLUMN "id" FROM df
FILLNA COLUMN "age" WITH MEAN FROM df
NORMALIZE COLUMN "salary" FROM df
ENCODE COLUMN "gender" METHOD ONEHOT FROM df
FILTER df WHERE "age" >= 18
DEDUPLICATE df
EXPORT df AS "output.csv"
```

...upload a CSV, click **Compile & Run**, and the app shows you every stage
of the compiler pipeline — tokens, AST, IR, the optimized IR, the generated
standalone Python script, an execution trace, and the resulting table —
then lets you download the cleaned CSV and the compiled `.py` script.

## How the three modules map to the code

| Capstone module | What it does | Where it lives |
|---|---|---|
| **Module 1** — Language, Lexical & Syntax Analysis | Regex-based lexer tokenizes the script; a hand-written recursive-descent parser builds an AST and reports line/column syntax errors | `dsl/lexer.py`, `dsl/parser.py`, `dsl/ast_nodes.py` |
| **Module 2** — Automated Preprocessing & IR Generation | Walks the AST, checks each dataframe alias is loaded before use (semantic analysis), and lowers each statement into a flat, linear intermediate representation (IR) | `dsl/ir.py` |
| **Module 3** — Optimization, Backend Compilation & Web Interface | Optimizer passes (dead-code elimination, redundant-op folding, filter pushdown, load dedup) run on the IR; the backend compiles optimized IR into a standalone pandas script *and* executes it live for the preview; Flask serves the single-page UI | `dsl/optimizer.py`, `dsl/backend.py`, `app.py`, `templates/`, `static/` |

### Request flow
```
Browser (script + CSV)
   -> POST /compile
        -> lexer.tokenize()          Module 1
        -> Parser().parse_program()  Module 1
        -> ir.generate_ir()          Module 2 (semantic checks + IR)
        -> optimizer.optimize()      Module 3
        -> backend.codegen()         Module 3 (-> pipeline.py)
        -> backend.execute()         Module 3 (-> live preview via pandas)
   <- JSON: tokens, ast, ir, optimized_ir, optimizer_notes,
            generated_code, preview, trace, errors
```

Every stage returns structured errors with line/column info, so a mistake
in the script (bad token, bad syntax, using a dataframe before `LOAD`,
referencing a dropped column, a runtime pandas error) is caught at the
right stage and shown in the UI instead of crashing the server.

## DSL language reference

```
LOAD "<path>" AS <alias>
DROP COLUMN "<col>" [, "<col2>" ...] FROM <alias>
FILLNA COLUMN "<col>" WITH (MEAN | MEDIAN | MODE | ZERO | <number>) FROM <alias>
NORMALIZE COLUMN "<col>" FROM <alias>          # min-max scale to [0,1]
STANDARDIZE COLUMN "<col>" FROM <alias>        # z-score
ENCODE COLUMN "<col>" METHOD (ONEHOT | LABEL) FROM <alias>
RENAME COLUMN "<old>" TO "<new>" FROM <alias>
CLIP COLUMN "<col>" MIN <number> MAX <number> FROM <alias>
TYPE COLUMN "<col>" AS_TYPE (INT | FLOAT | STRINGTYPE) FROM <alias>
LOWERCASE COLUMN "<col>" FROM <alias>
UPPERCASE COLUMN "<col>" FROM <alias>
TRIM COLUMN "<col>" FROM <alias>
FILTER <alias> WHERE "<col>" (> | < | >= | <= | == | !=) value [ (AND|OR) "<col>" op value ]...
DEDUPLICATE <alias>
SORT <alias> BY "<col>" [ASC | DESC]
EXPORT <alias> AS "<path>"
# a line starting with # is a comment
```

## Project layout

```
dataprep-dsl/
├── app.py                  Flask web server / API
├── requirements.txt
├── dsl/
│   ├── lexer.py             Module 1 — tokenizer
│   ├── parser.py            Module 1 — recursive-descent parser + AST build
│   ├── ast_nodes.py         Module 1 — AST node classes
│   ├── ir.py                Module 2 — semantic checks + IR generation
│   ├── optimizer.py         Module 3 — IR optimization passes
│   └── backend.py           Module 3 — codegen (.py output) + pandas execution
├── templates/index.html      web UI shell
├── static/style.css          UI styling
├── static/script.js          UI logic (calls /compile, renders tabs)
├── sample_data/sample.csv    sample dataset to try immediately
├── examples/example.dsl      example script matching the sample dataset
└── runs/                     created at runtime; per-run output files
```

---

## Running it locally (Windows / macOS / Linux, via cmd / terminal)

You need **Python 3.9+** installed (check with `python --version` or
`python3 --version`). Get it from https://python.org if you don't have it —
on Windows, tick "Add python.exe to PATH" during install.

### 1. Unzip the project
Unzip `dataprep-dsl.zip` anywhere, then open a terminal there.

**Windows (cmd.exe):**
```
cd path\to\dataprep-dsl
```
**macOS / Linux:**
```
cd path/to/dataprep-dsl
```

### 2. Create and activate a virtual environment (recommended)

**Windows (cmd.exe):**
```
python -m venv venv
venv\Scripts\activate
```
**macOS / Linux:**
```
python3 -m venv venv
source venv/bin/activate
```
Your prompt should now start with `(venv)`.

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Run the server
```
python app.py
```
You should see:
```
============================================================
 DataPrep-DSL local server
 Open this in your browser:  http://127.0.0.1:5000
============================================================
 * Running on http://127.0.0.1:5000
```

### 5. Open it in your browser
Go to **http://127.0.0.1:5000**

- The script editor is pre-filled with a working example.
- Click **Sample CSV** to download `sample.csv`, then use the file box to
  upload it (or use your own CSV — just make sure the column names in
  your script match your file's headers).
- Click **Compile & Run** (or press `Ctrl+Enter` / `Cmd+Enter` in the editor).
- Use the tabs on the right to inspect **Tokens**, **AST**, **IR**,
  **Optimized IR**, the **Generated .py**, the execution **Trace**, and
  the final **Output** table.
- Download the cleaned CSV or the standalone compiled Python script from
  the Output tab.

### 6. Stop the server
Press `Ctrl+C` in the terminal.

### Re-running later
```
cd path/to/dataprep-dsl
venv\Scripts\activate        (Windows)
source venv/bin/activate     (macOS/Linux)
python app.py
```

### Troubleshooting
- **"python is not recognized"** (Windows): Python isn't on PATH — reinstall
  and check "Add python.exe to PATH", or use `py app.py` instead of `python app.py`.
- **Port 5000 already in use**: edit the last line of `app.py` and change
  `port=5000` to e.g. `port=5050`, then open `http://127.0.0.1:5050`.
- **`pip install` fails on `pandas`**: upgrade pip first with
  `python -m pip install --upgrade pip`, then retry.
- **Blank page / styles missing**: hard-refresh the browser
  (`Ctrl+Shift+R` / `Cmd+Shift+R`) — the browser may have cached an old
  version of `style.css`/`script.js`.
