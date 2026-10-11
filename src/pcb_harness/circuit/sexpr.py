"""Small non-evaluating KiCad S-expression reader and escaping writer."""
import json
import re


class Atom(str):
    """Unquoted S-expression token, distinct from a quoted string."""


def parse_sexpr(text):
    tokens = re.findall(r'\s+|;[^\n]*|\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+', text)
    if "".join(tokens) != text:
        raise ValueError("malformed S-expression string")
    stack = []
    roots = []
    for token in tokens:
        if token.isspace() or token.startswith(";"):
            continue
        if token == "(":
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("unmatched closing parenthesis")
            stack.pop()
        else:
            if not stack:
                raise ValueError("token outside root")
            try:
                value = json.loads(token) if token.startswith('"') else Atom(token)
            except ValueError as error:
                raise ValueError("malformed quoted string") from error
            stack[-1].append(value)
    if stack or len(roots) != 1:
        raise ValueError("incomplete or multiple S-expression roots")
    return roots[0]


def dump_sexpr(node):
    if isinstance(node, list):
        return "(" + " ".join(dump_sexpr(value) for value in node) + ")"
    if isinstance(node, Atom):
        if not re.fullmatch(r'[^\s()";]+', node):
            raise ValueError("unsafe unquoted atom")
        return str(node)
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    if type(node) in (int, float):
        return json.dumps(node, allow_nan=False)
    raise ValueError("unsupported S-expression value")


def children(node, key):
    return [value for value in node if isinstance(value, list) and value and value[0] == key]


def child(node, key):
    values = children(node, key)
    if len(values) != 1:
        raise ValueError(f"expected one {key} node")
    return values[0]


def walk(node, key):
    if isinstance(node, list):
        if node and node[0] == key:
            yield node
        for value in node:
            yield from walk(value, key)
