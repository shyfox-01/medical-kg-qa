"""Lexical validation applied to the exact statement that will be executed."""

import re
from dataclasses import dataclass

from medkg.graph.schema import LABELS, PROPERTIES, RELATIONS


class CypherRejected(ValueError):
    pass


@dataclass
class Verdict:
    stmt: str
    limit: int


def lex_skeleton(text: str) -> str:
    out, i = list(text), 0
    while i < len(text):
        if text[i:i+2] == '//':
            end = text.find('\n', i)
            end = len(text) if end < 0 else end
            out[i:end] = ' ' * (end - i)
            i = end
        elif text[i:i+2] == '/*':
            end = text.find('*/', i+2)
            if end < 0:
                raise CypherRejected('Unclosed comment')
            end += 2
            out[i:end] = ' ' * (end-i)
            i = end
        elif text[i] in ('"', "'"):
            quote = text[i]
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == '\\':
                    out[i:i+2] = '  '
                    i += 2
                else:
                    out[i] = ' '
                    i += 1
            if i >= len(text):
                raise CypherRejected('Unclosed string')
            i += 1
        elif text[i] == '`':
            end = text.find('`', i+1)
            if end < 0:
                raise CypherRejected('Unclosed identifier')
            if not re.fullmatch(r'[A-Za-z_]\w*', text[i+1:end]):
                raise CypherRejected('Unsupported escaped identifier')
            i = end+1
        else:
            i += 1
    return ''.join(out)


def check(cypher: str, max_limit: int = 200, default_limit: int = 25,
          max_path_hops: int = 2) -> Verdict:
    stmt = cypher.strip().removesuffix(';').rstrip()
    if not stmt or len(stmt) > 20000:
        raise CypherRejected('Empty or oversized statement')
    code = lex_skeleton(stmt)
    if ';' in code:
        raise CypherRejected('Multiple statements are prohibited')
    if re.search(r'\bUNION\b',code,re.I):
        raise CypherRejected('UNION is unsupported: branch limits do not bound the total result')
    if not re.match(r'^(MATCH|OPTIONAL\s+MATCH|WITH|RETURN|CALL\s*\{)\b', code, re.I):
        raise CypherRejected('Expected a read query')
    forbidden = r'\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD|SHOW|TERMINATE|ALTER|GRANT|DENY|REVOKE|USE|PROFILE|EXPLAIN|INSERT|FINISH)\b'
    if re.search(forbidden, code, re.I) or re.search(r'\bIN\s+TRANSACTIONS?\b', code, re.I):
        raise CypherRejected('Write/admin operation prohibited')
    if re.search(r'\b(apoc|db|dbms|gds|genai|internal|vector|spatial|algo)\s*\.', code, re.I):
        raise CypherRejected('Namespaced procedure/function prohibited')
    if re.search(r'\)\s*(?:\+|\*|\{\s*\d)',code):
        raise CypherRejected('Quantified path patterns are unsupported; use bounded classical paths')
    for m in re.finditer(r'\bCALL\b', code, re.I):
        if not code[m.end():].lstrip().startswith('{'):
            raise CypherRejected('Stored procedures prohibited')
    if not re.search(r'\bRETURN\b', code, re.I):
        raise CypherRejected('RETURN is required')
    for body in re.findall(r'[(\[]([^)\]]*)', code):
        for token in re.findall(r'[:|]\s*`?(\w+)', body.split('{')[0]):
            if token not in (*LABELS, *RELATIONS):
                raise CypherRejected(f'Unknown schema type: {token}')
    for var, prop in re.findall(r'(?<![\w.$])(\w+)\s*\.\s*`?(\w+)', code):
        if not var.isdigit() and prop not in PROPERTIES:
            raise CypherRejected(f'Unknown property: {prop}')
    for body in re.findall(r'\[([^\]]*)\]', code):
        if '*' not in body:
            continue
        match = re.search(r'\*\s*(\d*)\s*(\.\.)?\s*(\d*)', body)
        lo, dots, hi = match.groups()
        if (dots and not hi) or (not dots and not lo):
            raise CypherRejected('Unbounded path prohibited')
        if int(hi or lo) > max_path_hops:
            raise CypherRejected(f'At most {max_path_hops} hops')
    for match in reversed(list(re.finditer(r'\bLIMIT\s+(\d+)\b', code, re.I))):
        number = min(int(match[1]), max_limit)
        stmt = stmt[:match.start(1)] + str(number) + stmt[match.end(1):]
    code = lex_skeleton(stmt)
    for match in re.finditer(r'\bLIMIT\b', code, re.I):
        if not re.match(r'\s+\d+(?=\s*(?:$|\}|UNION\b))', code[match.end():], re.I):
            raise CypherRejected('LIMIT must be a literal integer, without an expression')
    tail = re.search(r'\bLIMIT\s+(\d+)\s*$', code, re.I)
    limit = int(tail[1]) if tail else min(default_limit, max_limit)
    if tail is None:
        stmt += f'\nLIMIT {limit}'
    return Verdict(stmt, limit)
