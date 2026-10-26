"""Lays out and highlights a report's SQL for reading, changing only whitespace."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

WIDTH = 80
INDENT = "  "

TOKEN = re.compile(
    r"""(?P<ws>\s+)
    |(?P<comment>--[^\n]*|/\*.*?(?:\*/|\Z))
    |(?P<string>'(?:[^']|'')*(?:'|\Z)|\$(?P<tag>[^\W\d]\w*|)\$.*?(?:\$(?P=tag)\$|\Z))
    |(?P<ident>"(?:[^"]|"")*(?:"|\Z))
    |(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)
    |(?P<word>[^\W\d]\w*)
    |(?P<op>::|:=|->>|->|<=|>=|<>|!=|\|\||\*\*|//)
    |(?P<char>.)""",
    re.VERBOSE | re.DOTALL,
)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


STARTERS = _words(
    "with select from where group having qualify window order limit offset union except"
    " intersect join left right inner full cross natural asof positional anti semi"
)
JOIN_MODIFIERS = _words("left right inner outer full cross natural asof positional anti semi")
SUBQUERY_HEADS = frozenset(("select", "with", "from", "values"))
KEYWORDS = STARTERS | _words(
    "by as on using and or not in is null like ilike glob between case when then else end"
    " distinct all any some exists over partition filter within asc desc nulls first last true"
    " false cast try_cast interval rows range groups preceding following unbounded current row"
    " exclude replace recursive lateral outer values pivot unpivot"
)
PAREN_KEYWORDS = _words(
    "in over filter exists using as any all not and or on values within when then else from"
    " select where join"
)


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str


@dataclass(slots=True)
class Group:
    items: list[Token | Group] = field(default_factory=list)
    closed: bool = False

    def is_subquery(self) -> bool:
        first = next((i for i in self.items if _significant(i)), None)
        return (
            isinstance(first, Token)
            and first.kind == "word"
            and first.text.lower() in SUBQUERY_HEADS
        )


def tokenize(sql: str) -> list[Token]:
    return [Token(m.lastgroup or "char", m[0]) for m in TOKEN.finditer(sql)]


def format_sql(sql: str) -> str:
    """The query with each clause on its own line, subqueries indented, and long lists wrapped."""
    return _sequence(_tree(tokenize(sql.strip())), 0)


def highlight_sql(sql: str) -> str:
    """Escaped HTML of the query with keywords, functions, types, and literals in spans."""
    tokens = tokenize(sql)
    out = []
    for i, t in enumerate(tokens):
        cls = _class(tokens, i)
        out.append(
            f'<span class="sql-{cls}">{html.escape(t.text, quote=False)}</span>'
            if cls
            else html.escape(t.text, quote=False)
        )
    return "".join(out)


def _class(tokens: list[Token], i: int) -> str | None:
    t = tokens[i]
    if t.kind in ("comment", "string", "number"):
        return {"comment": "c", "string": "s", "number": "n"}[t.kind]
    if t.kind != "word":
        return None
    word = t.text.lower()
    nxt = tokens[i + 1] if i + 1 < len(tokens) else None
    if nxt is not None and nxt.text == "(" and word not in PAREN_KEYWORDS:
        return "f"
    if i > 0 and tokens[i - 1].text == "::":
        return "t"
    return "k" if word in KEYWORDS else None


def _significant(item: Token | Group) -> bool:
    return isinstance(item, Group) or item.kind not in ("ws", "comment")


def _tree(tokens: list[Token]) -> list[Token | Group]:
    stack = [Group()]
    for t in tokens:
        if t.text == "(":
            stack.append(Group())
        elif t.text == ")" and len(stack) > 1:
            group = stack.pop()
            group.closed = True
            stack[-1].items.append(group)
        else:
            stack[-1].items.append(t)
    while len(stack) > 1:
        group = stack.pop()
        stack[-1].items.append(group)
    return stack[0].items


def _is_starter(items: list[Token | Group], i: int) -> bool:
    item = items[i]
    if not isinstance(item, Token) or item.kind != "word":
        return False
    word = item.text.lower()
    if word not in STARTERS:
        return False
    if i + 1 < len(items) and isinstance(items[i + 1], Group):
        return False
    prev = next((p for p in reversed(items[:i]) if _significant(p)), None)
    return not (isinstance(prev, Token) and prev.text.lower() in JOIN_MODIFIERS)


def _sequence(items: list[Token | Group], depth: int) -> str:
    clauses: list[list[Token | Group]] = [[]]
    for i, item in enumerate(items):
        if _is_starter(items, i) and any(_significant(p) for p in clauses[-1]):
            clauses.append([])
        clauses[-1].append(item)
    return "\n".join(_clause(c, depth) for c in clauses if c)


def _clause(items: list[Token | Group], depth: int) -> str:
    pieces: list[list[Token | Group]] = [[]]
    for item in items:
        pieces[-1].append(item)
        if isinstance(item, Token) and item.text == ",":
            pieces.append([])
    pieces = [p for p in pieces if any(_significant(i) for i in p)]
    texts = [_inline(p, depth) for p in pieces]
    pad, cont = INDENT * depth, INDENT * (depth + 1)
    out = pad + texts[0] if texts else ""
    for i in range(1, len(texts)):
        text, last = texts[i], out.rsplit("\n", 1)[-1]
        if _ends_in_line_comment(pieces[i - 1]):
            out += "\n" + cont + text
        elif "\n" in texts[i - 1]:
            out += "\n" + pad + text
        elif len(last) + 1 + len(text.split("\n", 1)[0]) > WIDTH:
            out += "\n" + cont + text
        else:
            out += " " + text
    return out


def _inline(items: list[Token | Group], depth: int) -> str:
    parts: list[str] = []
    space = False
    for item in items:
        if isinstance(item, Token) and item.kind == "ws":
            space = bool(parts)
            continue
        if parts and parts[-1] == "\n":
            parts.append(INDENT * (depth + 1))
        elif space:
            parts.append(" ")
        space = False
        parts.append(_group(item, depth) if isinstance(item, Group) else item.text)
        if isinstance(item, Token) and item.kind == "comment" and item.text.startswith("--"):
            parts.append("\n")
    return "".join(parts).rstrip("\n")


def _ends_in_line_comment(items: list[Token | Group]) -> bool:
    last = next((i for i in reversed(items) if not (isinstance(i, Token) and i.kind == "ws")), None)
    return isinstance(last, Token) and last.kind == "comment" and last.text.startswith("--")


def _group(group: Group, depth: int) -> str:
    close = ")" if group.closed else ""
    if group.is_subquery():
        return "(\n" + _sequence(group.items, depth + 1) + "\n" + INDENT * depth + close
    inner = _inline(group.items, depth)
    if close and _ends_in_line_comment(group.items):
        inner += "\n" + INDENT * depth
    return "(" + inner + close
