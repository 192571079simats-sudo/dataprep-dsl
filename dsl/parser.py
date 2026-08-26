"""
DataPrep-DSL :: Recursive-Descent Parser (Module 1: Syntax Analysis)
----------------------------------------------------------------------
Grammar (EBNF-ish):

  program     := statement*
  statement   := load | drop | fillna | normalize | standardize
               | encode | rename | filter | dedup | clip
               | cast | textcase | sortby | export

  load        := LOAD STRING AS IDENT
  drop        := DROP COLUMN STRING (',' STRING)* FROM IDENT
  fillna      := FILLNA COLUMN STRING WITH (MEAN|MEDIAN|MODE|ZERO|NUMBER) FROM IDENT
  normalize   := NORMALIZE COLUMN STRING FROM IDENT
  standardize := STANDARDIZE COLUMN STRING FROM IDENT
  encode      := ENCODE COLUMN STRING METHOD (ONEHOT|LABEL) FROM IDENT
  rename      := RENAME COLUMN STRING TO STRING FROM IDENT
  filter      := FILTER IDENT WHERE condition
  condition   := STRING OP value ((AND|OR) STRING OP value)*
  dedup       := DEDUPLICATE IDENT
  clip        := CLIP COLUMN STRING MIN NUMBER MAX NUMBER FROM IDENT
  cast        := TYPE COLUMN STRING AS_TYPE (INT|FLOAT|STRINGTYPE) FROM IDENT
  textcase    := (LOWERCASE|UPPERCASE|TRIM) COLUMN STRING FROM IDENT
  sortby      := SORT IDENT BY STRING (ASC|DESC)?
  export      := EXPORT IDENT AS STRING
"""

from .lexer import tokenize
from . import ast_nodes as A


class ParseError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"Syntax error at line {line}, col {col}: {message}")
        self.line = line
        self.col = col


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # ---- helpers ----
    def peek(self, offset=0):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def advance(self):
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def check(self, type_):
        return self.peek().type == type_

    def match(self, *types):
        if self.peek().type in types:
            return self.advance()
        return None

    def expect(self, type_, what=None):
        tok = self.peek()
        if tok.type != type_:
            raise ParseError(
                f"expected {what or type_} but found {tok.type} ({tok.value!r})",
                tok.line, tok.col,
            )
        return self.advance()

    # ---- entry point ----
    def parse_program(self):
        statements = []
        while not self.check("EOF"):
            statements.append(self.parse_statement())
        return A.Program(statements)

    def parse_statement(self):
        tok = self.peek()
        dispatch = {
            "LOAD": self.parse_load,
            "DROP": self.parse_drop,
            "FILLNA": self.parse_fillna,
            "NORMALIZE": self.parse_normalize,
            "STANDARDIZE": self.parse_standardize,
            "ENCODE": self.parse_encode,
            "RENAME": self.parse_rename,
            "FILTER": self.parse_filter,
            "DEDUPLICATE": self.parse_dedup,
            "CLIP": self.parse_clip,
            "TYPE": self.parse_cast,
            "LOWERCASE": self.parse_textcase,
            "UPPERCASE": self.parse_textcase,
            "TRIM": self.parse_textcase,
            "SORT": self.parse_sortby,
            "EXPORT": self.parse_export,
        }
        if tok.type in dispatch:
            return dispatch[tok.type]()
        raise ParseError(
            f"unexpected token {tok.type} ({tok.value!r}) -- expected a statement keyword "
            f"(LOAD, DROP, FILLNA, NORMALIZE, STANDARDIZE, ENCODE, RENAME, FILTER, "
            f"DEDUPLICATE, CLIP, TYPE, LOWERCASE, UPPERCASE, TRIM, SORT, EXPORT)",
            tok.line, tok.col,
        )

    # ---- statements ----
    def parse_load(self):
        line = self.expect("LOAD").line
        path = self.expect("STRING", "a quoted file path").value
        self.expect("AS")
        alias = self.expect("IDENT", "a dataframe alias").value
        return A.Load(path, alias, line)

    def parse_drop(self):
        line = self.expect("DROP").line
        self.match("COLUMN", "COLUMNS")
        cols = [self.expect("STRING", "a column name").value]
        while self.match(","):
            cols.append(self.expect("STRING", "a column name").value)
        self.expect("FROM")
        df = self.expect("IDENT", "a dataframe alias").value
        return A.Drop(cols, df, line)

    def parse_fillna(self):
        line = self.expect("FILLNA").line
        self.expect("COLUMN")
        col = self.expect("STRING", "a column name").value
        self.expect("WITH")
        strat_tok = self.peek()
        if strat_tok.type in ("MEAN", "MEDIAN", "MODE", "ZERO"):
            strategy = self.advance().type
        elif strat_tok.type == "NUMBER":
            strategy = self.advance().value
        else:
            raise ParseError("expected MEAN, MEDIAN, MODE, ZERO or a number after WITH",
                              strat_tok.line, strat_tok.col)
        self.expect("FROM")
        df = self.expect("IDENT", "a dataframe alias").value
        return A.FillNa(col, strategy, df, line)

    def parse_normalize(self):
        line = self.expect("NORMALIZE").line
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.Normalize(col, df, line)

    def parse_standardize(self):
        line = self.expect("STANDARDIZE").line
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.Standardize(col, df, line)

    def parse_encode(self):
        line = self.expect("ENCODE").line
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("METHOD")
        method_tok = self.peek()
        if method_tok.type not in ("ONEHOT", "LABEL"):
            raise ParseError("expected ONEHOT or LABEL", method_tok.line, method_tok.col)
        method = self.advance().type
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.Encode(col, method, df, line)

    def parse_rename(self):
        line = self.expect("RENAME").line
        self.expect("COLUMN")
        old = self.expect("STRING").value
        self.expect("TO")
        new = self.expect("STRING").value
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.Rename(old, new, df, line)

    def parse_filter(self):
        line = self.expect("FILTER").line
        df = self.expect("IDENT", "a dataframe alias").value
        self.expect("WHERE")
        conditions = [self.parse_condition_term()]
        while self.peek().type in ("AND", "OR"):
            joiner = self.advance().type
            conditions.append((joiner,) + self.parse_condition_term())
        # normalize first term to have a None joiner
        first = conditions[0]
        conditions[0] = (None,) + first
        return A.Filter(df, conditions, line)

    def parse_condition_term(self):
        col = self.expect("STRING", "a column name").value
        op_tok = self.peek()
        if op_tok.type not in (">", "<", ">=", "<=", "==", "!="):
            raise ParseError("expected a comparison operator (> < >= <= == !=)",
                              op_tok.line, op_tok.col)
        op = self.advance().type
        val_tok = self.peek()
        if val_tok.type in ("NUMBER", "STRING"):
            value = self.advance().value
        else:
            raise ParseError("expected a number or string literal", val_tok.line, val_tok.col)
        return (col, op, value)

    def parse_dedup(self):
        line = self.expect("DEDUPLICATE").line
        df = self.expect("IDENT").value
        return A.Deduplicate(df, line)

    def parse_clip(self):
        line = self.expect("CLIP").line
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("MIN")
        min_v = self.expect("NUMBER").value
        self.expect("MAX")
        max_v = self.expect("NUMBER").value
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.Clip(col, min_v, max_v, df, line)

    def parse_cast(self):
        line = self.expect("TYPE").line
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("AS_TYPE")
        dtype_tok = self.peek()
        if dtype_tok.type not in ("INT", "FLOAT", "STRINGTYPE"):
            raise ParseError("expected INT, FLOAT or STRINGTYPE", dtype_tok.line, dtype_tok.col)
        dtype = self.advance().type
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.CastType(col, dtype, df, line)

    def parse_textcase(self):
        mode_tok = self.advance()
        self.expect("COLUMN")
        col = self.expect("STRING").value
        self.expect("FROM")
        df = self.expect("IDENT").value
        return A.TextCase(col, mode_tok.type, df, mode_tok.line)

    def parse_sortby(self):
        line = self.expect("SORT").line
        df = self.expect("IDENT").value
        self.expect("BY")
        col = self.expect("STRING").value
        direction = "ASC"
        if self.peek().type in ("ASC", "DESC"):
            direction = self.advance().type
        return A.SortBy(col, direction, df, line)

    def parse_export(self):
        line = self.expect("EXPORT").line
        df = self.expect("IDENT").value
        self.expect("AS")
        path = self.expect("STRING").value
        return A.Export(df, path, line)


def parse(source: str):
    """Full front-end pipeline: lex + parse. Returns (program, tokens, errors)."""
    tokens, lex_errors = tokenize(source)
    if lex_errors:
        return None, tokens, lex_errors
    try:
        program = Parser(tokens).parse_program()
        return program, tokens, []
    except ParseError as e:
        return None, tokens, [{"message": str(e), "line": e.line, "col": e.col}]
