"""
DataPrep-DSL :: AST Node Definitions (Module 1)
"""


class Node:
    def to_dict(self):
        d = {"node": self.__class__.__name__}
        for k, v in self.__dict__.items():
            if isinstance(v, Node):
                d[k] = v.to_dict()
            elif isinstance(v, list):
                d[k] = [x.to_dict() if isinstance(x, Node) else x for x in v]
            else:
                d[k] = v
        return d


class Program(Node):
    def __init__(self, statements):
        self.statements = statements


class Load(Node):
    def __init__(self, path, alias, line):
        self.path = path
        self.alias = alias
        self.line = line


class Drop(Node):
    def __init__(self, columns, df, line):
        self.columns = columns
        self.df = df
        self.line = line


class FillNa(Node):
    def __init__(self, column, strategy, df, line):
        self.column = column
        self.strategy = strategy  # 'MEAN' | 'MEDIAN' | 'MODE' | 'ZERO' | numeric literal
        self.df = df
        self.line = line


class Normalize(Node):
    def __init__(self, column, df, line):
        self.column = column
        self.df = df
        self.line = line


class Standardize(Node):
    def __init__(self, column, df, line):
        self.column = column
        self.df = df
        self.line = line


class Encode(Node):
    def __init__(self, column, method, df, line):
        self.column = column
        self.method = method  # 'ONEHOT' | 'LABEL'
        self.df = df
        self.line = line


class Rename(Node):
    def __init__(self, old, new, df, line):
        self.old = old
        self.new = new
        self.df = df
        self.line = line


class Filter(Node):
    def __init__(self, df, conditions, line):
        self.df = df
        self.conditions = conditions  # list of (column, op, value, joiner)
        self.line = line


class Deduplicate(Node):
    def __init__(self, df, line):
        self.df = df
        self.line = line


class Clip(Node):
    def __init__(self, column, min_v, max_v, df, line):
        self.column = column
        self.min_v = min_v
        self.max_v = max_v
        self.df = df
        self.line = line


class CastType(Node):
    def __init__(self, column, dtype, df, line):
        self.column = column
        self.dtype = dtype
        self.df = df
        self.line = line


class TextCase(Node):
    def __init__(self, column, mode, df, line):
        self.column = column
        self.mode = mode  # 'LOWERCASE' | 'UPPERCASE' | 'TRIM'
        self.df = df
        self.line = line


class SortBy(Node):
    def __init__(self, column, direction, df, line):
        self.column = column
        self.direction = direction  # 'ASC' | 'DESC'
        self.df = df
        self.line = line


class Export(Node):
    def __init__(self, df, path, line):
        self.df = df
        self.path = path
        self.line = line
