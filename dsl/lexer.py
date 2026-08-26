"""
DataPrep-DSL :: Lexical Analyzer (Module 1)
--------------------------------------------
Converts raw DSL source text into a stream of Tokens using a
regex-driven maximal-munch scanner.
"""

import re


class LexError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"Lexical error at line {line}, col {col}: {message}")
        self.line = line
        self.col = col


class Token:
    __slots__ = ("type", "value", "line", "col")

    def __init__(self, type_, value, line, col):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, L{self.line}:C{self.col})"

    def to_dict(self):
        return {"type": self.type, "value": self.value, "line": self.line, "col": self.col}


KEYWORDS = {
    "LOAD", "AS", "DROP", "COLUMN", "COLUMNS", "FROM", "FILLNA", "WITH",
    "MEAN", "MEDIAN", "MODE", "ZERO", "NORMALIZE", "STANDARDIZE",
    "ENCODE", "METHOD", "ONEHOT", "LABEL", "FILTER", "WHERE",
    "DEDUPLICATE", "EXPORT", "AND", "OR", "RENAME", "TO", "CLIP",
    "MIN", "MAX", "LOWERCASE", "UPPERCASE", "TRIM", "TYPE", "AS_TYPE",
    "INT", "FLOAT", "STRINGTYPE", "SORT", "BY", "ASC", "DESC",
}

TOKEN_SPEC = [
    ("COMMENT",   r"\#[^\n]*"),
    ("NEWLINE",   r"\n"),
    ("SKIP",      r"[ \t\r]+"),
    ("STRING",    r'"([^"\\]|\\.)*"'),
    ("NUMBER",    r"\d+\.\d+|\d+"),
    ("OP",        r">=|<=|==|!=|>|<|="),
    ("IDENT",     r"[A-Za-z_][A-Za-z0-9_]*"),
    ("MISMATCH",  r"."),
]

MASTER_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_SPEC))


def tokenize(source: str):
    """Returns (tokens, errors) -- a list of Token and a list of LexError-like dicts."""
    tokens = []
    errors = []
    line = 1
    line_start = 0

    for mo in MASTER_RE.finditer(source):
        kind = mo.lastgroup
        value = mo.group()
        col = mo.start() - line_start + 1

        if kind == "NEWLINE":
            line += 1
            line_start = mo.end()
            continue
        elif kind in ("SKIP", "COMMENT"):
            continue
        elif kind == "STRING":
            literal = value[1:-1].replace('\\"', '"')
            tokens.append(Token("STRING", literal, line, col))
        elif kind == "NUMBER":
            num = float(value) if "." in value else int(value)
            tokens.append(Token("NUMBER", num, line, col))
        elif kind == "IDENT":
            upper = value.upper()
            if upper in KEYWORDS:
                tokens.append(Token(upper, value, line, col))
            else:
                tokens.append(Token("IDENT", value, line, col))
        elif kind == "OP":
            tokens.append(Token(value, value, line, col))
        elif kind == "MISMATCH":
            errors.append({"message": f"Unexpected character {value!r}", "line": line, "col": col})
        else:
            tokens.append(Token(kind, value, line, col))

    tokens.append(Token("EOF", None, line, 1))
    return tokens, errors
