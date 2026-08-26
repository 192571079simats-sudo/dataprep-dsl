"""
DataPrep-DSL :: IR Optimizer (Module 3: Code Optimization)
--------------------------------------------------------------
Applies simple, provably-safe optimization passes over the linear IR
produced by Module 2. Each pass returns (new_ir, notes) where notes
is a human-readable log entry describing what changed, so the web UI
can show a "before / after" optimization report.

Passes implemented:
  1. dead_column_elimination -- drop instructions that operate on a
     column that was already DROPped for that dataframe (the column
     no longer exists, so the instruction would be a runtime no-op
     or error; we remove it and warn).
  2. redundant_op_folding -- if the same (op, df, column) transform
     appears twice in a row with nothing in between that changes the
     column, only the last one has any effect, so earlier ones are
     removed.
  3. filter_pushdown -- FILTER instructions are moved to run as early
     as possible (right after LOAD / column-existence requirements),
     since filtering rows first means every subsequent transform
     touches fewer rows.
  4. load_dedup -- if a dataframe is LOADed twice, only the *last*
     LOAD instruction (and everything after it) survives -- earlier
     LOAD + orphaned instructions on that alias are dead code.
"""


def optimize(ir):
    notes = []
    ir = list(ir)

    ir, n = _load_dedup(ir)
    notes.extend(n)

    ir, n = _dead_column_elimination(ir)
    notes.extend(n)

    ir, n = _redundant_op_folding(ir)
    notes.extend(n)

    ir, n = _filter_pushdown(ir)
    notes.extend(n)

    if not notes:
        notes.append("No optimization opportunities found -- IR was already minimal.")

    return ir, notes


def _load_dedup(ir):
    """Keep only the segment of IR from the last LOAD of each alias onward,
    for instructions targeting that alias."""
    last_load_idx = {}
    for idx, instr in enumerate(ir):
        if instr.op == "LOAD":
            last_load_idx[instr.df] = idx

    notes = []
    new_ir = []
    for idx, instr in enumerate(ir):
        df = instr.df
        if df in last_load_idx and idx < last_load_idx[df] and instr.op == "LOAD":
            notes.append(f"Line {instr.line}: removed superseded LOAD for '{df}' "
                          f"(re-loaded later in the script)")
            continue
        new_ir.append(instr)
    return new_ir, notes


def _dead_column_elimination(ir):
    dropped_cols = {}  # df -> set of dropped column names
    notes = []
    new_ir = []

    col_bearing_ops = {"FILLNA", "NORMALIZE", "STANDARDIZE", "ENCODE", "RENAME",
                        "CLIP", "CAST_TYPE", "TEXT_CASE", "SORT_BY"}

    for instr in ir:
        df = instr.df
        dropped_cols.setdefault(df, set())

        if instr.op == "LOAD":
            dropped_cols[df] = set()
            new_ir.append(instr)
            continue

        if instr.op == "DROP_COLUMNS":
            col = instr.args["column"] if "column" in instr.args else None
            newly_dropped = set(instr.args.get("columns", []))
            still_relevant = [c for c in instr.args.get("columns", []) if c not in dropped_cols[df]]
            if len(still_relevant) < len(instr.args.get("columns", [])):
                removed = set(instr.args.get("columns", [])) - set(still_relevant)
                notes.append(f"Line {instr.line}: column(s) {sorted(removed)} already dropped "
                              f"from '{df}', removed duplicate drop")
            if still_relevant:
                instr.args = {"columns": still_relevant}
                new_ir.append(instr)
            dropped_cols[df] |= newly_dropped
            continue

        if instr.op in col_bearing_ops:
            target_col = instr.args.get("column") or instr.args.get("old")
            if target_col in dropped_cols[df]:
                notes.append(f"Line {instr.line}: {instr.op} on column '{target_col}' "
                              f"skipped -- that column was already dropped from '{df}' (dead code)")
                continue

        if instr.op == "RENAME":
            # after a rename, the old name is gone, the new one exists
            old, new = instr.args["old"], instr.args["new"]
            dropped_cols[df].discard(new)

        new_ir.append(instr)

    return new_ir, notes


def _redundant_op_folding(ir):
    """Remove an instruction that is an EXACT duplicate (same op, same
    dataframe, same args -- e.g. two identical FILLNA...WITH MEAN on the
    same column) of one already applied since the last LOAD/EXPORT of
    that dataframe. Only exact-argument duplicates are folded: unlike a
    same-op-different-args pair (e.g. TRIM then LOWERCASE both being
    TEXT_CASE, or FILLNA MEAN then FILLNA MEDIAN), an exact duplicate is
    provably a no-op the second time, so dropping the repeat can never
    change the pipeline's output."""
    foldable_ops = {"FILLNA", "NORMALIZE", "STANDARDIZE", "CLIP", "CAST_TYPE",
                     "TEXT_CASE", "DEDUPLICATE"}
    notes = []
    new_ir = []
    seen = set()  # (df, op, frozenset(args.items()))

    for instr in ir:
        if instr.op in ("EXPORT", "LOAD"):
            seen = {k for k in seen if k[0] != instr.df} if instr.op == "LOAD" else seen
            new_ir.append(instr)
            continue

        if instr.op in foldable_ops:
            key = (instr.df, instr.op, tuple(sorted(instr.args.items())))
            if key in seen:
                notes.append(f"Line {instr.line}: exact duplicate of an earlier {instr.op} "
                              f"already applied to '{instr.df}' -- removed as a no-op")
                continue
            seen.add(key)

        new_ir.append(instr)

    return new_ir, notes


def _filter_pushdown(ir):
    """Move FILTER instructions to immediately after their dataframe's LOAD
    (or after any preceding column-structural change they don't depend on),
    so row-filtering happens before per-cell transforms run on rows that
    would be discarded anyway. Conservative: only reorders past
    transform-type ops (FILLNA/NORMALIZE/STANDARDIZE/ENCODE/CLIP/CAST_TYPE/
    TEXT_CASE/SORT_BY/DEDUPLICATE) on the SAME dataframe, never past
    DROP_COLUMNS/RENAME/LOAD/EXPORT which could change what the filter's
    column references."""
    movable_past = {"FILLNA", "NORMALIZE", "STANDARDIZE", "ENCODE", "CLIP",
                     "CAST_TYPE", "TEXT_CASE", "SORT_BY", "DEDUPLICATE"}
    notes = []
    ir = list(ir)
    changed = True
    while changed:
        changed = False
        for i in range(1, len(ir)):
            cur, prev = ir[i], ir[i - 1]
            if cur.op == "FILTER" and prev.op in movable_past and prev.df == cur.df:
                ir[i - 1], ir[i] = ir[i], ir[i - 1]
                notes.append(f"Line {cur.line}: FILTER on '{cur.df}' pushed earlier, ahead of "
                              f"{prev.op} (line {prev.line}) -- filters rows before transforming them")
                changed = True
    return ir, notes
