"""
DataPrep-DSL :: Semantic Analysis & Intermediate Representation (Module 2)
----------------------------------------------------------------------------
Walks the AST, performs light semantic checks (dataframe-alias existence,
duplicate LOAD detection) and lowers each statement into a flat,
linear IR: a list of (op, args-dict) instructions that the backend
(Module 3) can optimize and then execute independently of the
original DSL syntax.
"""

from . import ast_nodes as A


class SemanticError(Exception):
    def __init__(self, message, line):
        super().__init__(f"Semantic error at line {line}: {message}")
        self.line = line


class IRInstruction:
    def __init__(self, op, df, args, line):
        self.op = op
        self.df = df
        self.args = args
        self.line = line

    def to_dict(self):
        return {"op": self.op, "df": self.df, "args": self.args, "line": self.line}

    def __repr__(self):
        return f"IR({self.op}, df={self.df}, args={self.args})"


def generate_ir(program: A.Program):
    """Returns (ir_list, warnings). Raises SemanticError on hard failures."""
    ir = []
    warnings = []
    known_dfs = set()

    for stmt in program.statements:
        if isinstance(stmt, A.Load):
            if stmt.alias in known_dfs:
                warnings.append(f"Line {stmt.line}: dataframe '{stmt.alias}' re-loaded, "
                                 f"previous contents will be discarded")
            known_dfs.add(stmt.alias)
            ir.append(IRInstruction("LOAD", stmt.alias, {"path": stmt.path}, stmt.line))
            continue

        # every other statement references a dataframe alias -- check it exists
        df_alias = stmt.df
        if df_alias not in known_dfs:
            raise SemanticError(
                f"dataframe '{df_alias}' is used before it is LOADed", stmt.line
            )

        if isinstance(stmt, A.Drop):
            ir.append(IRInstruction("DROP_COLUMNS", df_alias, {"columns": stmt.columns}, stmt.line))
        elif isinstance(stmt, A.FillNa):
            ir.append(IRInstruction("FILLNA", df_alias,
                                     {"column": stmt.column, "strategy": stmt.strategy}, stmt.line))
        elif isinstance(stmt, A.Normalize):
            ir.append(IRInstruction("NORMALIZE", df_alias, {"column": stmt.column}, stmt.line))
        elif isinstance(stmt, A.Standardize):
            ir.append(IRInstruction("STANDARDIZE", df_alias, {"column": stmt.column}, stmt.line))
        elif isinstance(stmt, A.Encode):
            ir.append(IRInstruction("ENCODE", df_alias,
                                     {"column": stmt.column, "method": stmt.method}, stmt.line))
        elif isinstance(stmt, A.Rename):
            ir.append(IRInstruction("RENAME", df_alias,
                                     {"old": stmt.old, "new": stmt.new}, stmt.line))
        elif isinstance(stmt, A.Filter):
            ir.append(IRInstruction("FILTER", df_alias,
                                     {"conditions": stmt.conditions}, stmt.line))
        elif isinstance(stmt, A.Deduplicate):
            ir.append(IRInstruction("DEDUPLICATE", df_alias, {}, stmt.line))
        elif isinstance(stmt, A.Clip):
            ir.append(IRInstruction("CLIP", df_alias,
                                     {"column": stmt.column, "min": stmt.min_v, "max": stmt.max_v},
                                     stmt.line))
        elif isinstance(stmt, A.CastType):
            ir.append(IRInstruction("CAST_TYPE", df_alias,
                                     {"column": stmt.column, "dtype": stmt.dtype}, stmt.line))
        elif isinstance(stmt, A.TextCase):
            ir.append(IRInstruction("TEXT_CASE", df_alias,
                                     {"column": stmt.column, "mode": stmt.mode}, stmt.line))
        elif isinstance(stmt, A.SortBy):
            ir.append(IRInstruction("SORT_BY", df_alias,
                                     {"column": stmt.column, "direction": stmt.direction}, stmt.line))
        elif isinstance(stmt, A.Export):
            ir.append(IRInstruction("EXPORT", df_alias, {"path": stmt.path}, stmt.line))
        else:
            raise SemanticError(f"unhandled statement type {type(stmt).__name__}", stmt.line)

    if "EXPORT" not in [i.op for i in ir]:
        warnings.append("No EXPORT statement found -- the pipeline result will only be "
                         "shown in the preview, no output file will be written.")

    return ir, warnings
