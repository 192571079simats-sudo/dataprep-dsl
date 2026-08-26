"""
DataPrep-DSL :: Web Interface (Module 3)
------------------------------------------
Flask app that ties the whole pipeline together:

  upload CSV + DSL script
      -> lexer.tokenize            (Module 1)
      -> parser.parse -> AST       (Module 1)
      -> ir.generate_ir            (Module 2, with semantic checks)
      -> optimizer.optimize        (Module 3)
      -> backend.codegen           (Module 3 -- compiled .py output)
      -> backend.execute           (Module 3 -- live preview via pandas)
      -> JSON response for the single-page UI

Run locally with:  python app.py   (see README.md for full setup)
"""

import io
import json
import os
import uuid

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

from dsl.lexer import tokenize
from dsl.parser import Parser, ParseError
from dsl.ir import generate_ir, SemanticError
from dsl.optimizer import optimize
from dsl.backend import codegen, execute, RuntimeExecError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(BASE_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB upload cap

DEFAULT_SCRIPT = """\
# DataPrep-DSL example pipeline
LOAD "input.csv" AS df
DROP COLUMN "id" FROM df
FILLNA COLUMN "age" WITH MEAN FROM df
FILLNA COLUMN "city" WITH MODE FROM df
TRIM COLUMN "city" FROM df
NORMALIZE COLUMN "salary" FROM df
ENCODE COLUMN "gender" METHOD ONEHOT FROM df
FILTER df WHERE "age" >= 18
DEDUPLICATE df
SORT df BY "salary" DESC
EXPORT df AS "output.csv"
"""


@app.route("/")
def index():
    return render_template("index.html", default_script=DEFAULT_SCRIPT)


@app.route("/sample-csv")
def sample_csv():
    return send_from_directory(os.path.join(BASE_DIR, "sample_data"), "sample.csv",
                                as_attachment=True, download_name="sample.csv")


@app.route("/compile", methods=["POST"])
def compile_pipeline():
    script = request.form.get("script", "")
    upload = request.files.get("csv_file")

    result = {
        "stage": None,
        "tokens": [],
        "ast": None,
        "ir": [],
        "optimized_ir": [],
        "optimizer_notes": [],
        "semantic_warnings": [],
        "generated_code": None,
        "errors": [],
        "preview": None,
        "trace": [],
        "run_id": None,
    }

    # ---------- Module 1: Lexical analysis ----------
    tokens, lex_errors = tokenize(script)
    result["tokens"] = [t.to_dict() for t in tokens if t.type != "EOF"]
    if lex_errors:
        result["stage"] = "lexer"
        result["errors"] = lex_errors
        return jsonify(result), 200

    # ---------- Module 1: Syntax analysis ----------
    try:
        program = Parser(tokens).parse_program()
    except ParseError as e:
        result["stage"] = "parser"
        result["errors"] = [{"message": str(e), "line": e.line, "col": e.col}]
        return jsonify(result), 200
    result["ast"] = program.to_dict()

    # ---------- Module 2: Semantic analysis + IR generation ----------
    try:
        ir_list, warnings = generate_ir(program)
    except SemanticError as e:
        result["stage"] = "semantic"
        result["errors"] = [{"message": str(e), "line": e.line}]
        return jsonify(result), 200
    result["ir"] = [i.to_dict() for i in ir_list]
    result["semantic_warnings"] = warnings

    # ---------- Module 3: Optimization ----------
    optimized_ir, opt_notes = optimize(ir_list)
    result["optimized_ir"] = [i.to_dict() for i in optimized_ir]
    result["optimizer_notes"] = opt_notes

    # ---------- Module 3: Backend compilation (generated script) ----------
    csv_display_name = upload.filename if (upload and upload.filename) else "input.csv"
    result["generated_code"] = codegen(optimized_ir, csv_display_name=csv_display_name)

    # If no CSV was uploaded, stop here -- static analysis only, no execution.
    if not upload or not upload.filename:
        result["stage"] = "static-only"
        result["errors"] = []
        result["semantic_warnings"].append(
            "No CSV uploaded -- showing compiled pipeline only. Upload a CSV to run it live."
        )
        return jsonify(result), 200

    # ---------- Module 3: Execution against the uploaded CSV ----------
    try:
        raw_bytes = upload.read()
        source_df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as e:
        result["stage"] = "csv-parse"
        result["errors"] = [{"message": f"Could not parse uploaded CSV: {e}"}]
        return jsonify(result), 200

    try:
        dataframes, trace, export_info = execute(optimized_ir, source_df)
    except RuntimeExecError as e:
        result["stage"] = "runtime"
        result["errors"] = [{"message": str(e), "line": e.line}]
        return jsonify(result), 200
    except Exception as e:
        result["stage"] = "runtime"
        result["errors"] = [{"message": f"Unexpected runtime error: {e}"}]
        return jsonify(result), 200

    result["trace"] = trace

    run_id = uuid.uuid4().hex[:12]
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    # write generated script
    with open(os.path.join(run_dir, "pipeline.py"), "w") as f:
        f.write(result["generated_code"])

    # write final exported dataframe (if EXPORT was used) else last touched df
    final_df = None
    if export_info:
        df_name, _path = export_info
        final_df = dataframes.get(df_name)
    elif dataframes:
        final_df = list(dataframes.values())[-1]

    if final_df is not None:
        final_df.to_csv(os.path.join(run_dir, "output.csv"), index=False)
        preview_df = final_df.head(25)
        result["preview"] = {
            "columns": list(map(str, preview_df.columns)),
            "rows": json.loads(preview_df.to_json(orient="records")),
            "total_rows": int(len(final_df)),
            "total_cols": int(len(final_df.columns)),
        }

    result["run_id"] = run_id
    result["stage"] = "done"
    return jsonify(result), 200


@app.route("/download/<run_id>/<kind>")
def download(run_id, kind):
    run_dir = os.path.join(RUNS_DIR, run_id)
    if not os.path.isdir(run_dir):
        return "Run not found", 404
    filename = "output.csv" if kind == "csv" else "pipeline.py"
    if not os.path.isfile(os.path.join(run_dir, filename)):
        return "File not found", 404
    return send_from_directory(run_dir, filename, as_attachment=True)


if __name__ == "__main__":
    # Local dev run: `python app.py`
    # In production (Render etc.) gunicorn imports `app` directly and this
    # block never runs -- see Procfile.
    port = int(os.environ.get("PORT", 5000))
    is_local = "PORT" not in os.environ
    print("=" * 60)
    print(" DataPrep-DSL local server")
    print(f" Open this in your browser:  http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host="127.0.0.1" if is_local else "0.0.0.0", port=port, debug=is_local)
