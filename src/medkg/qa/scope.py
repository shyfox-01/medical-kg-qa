"""Finite deterministic rejection of administrative and injection requests.

This is a narrow scope guard, not a general prompt-injection classifier. The
generated-query guard and read-only database transactions remain necessary.
"""

import re

MESSAGE = ('I cannot execute administrative commands, disclose credentials or '
           'override instructions. Please ask about the supported medical knowledge base.')

PATTERNS = (
    r'\b(?:credentials?|passwords?|api[ _-]?keys?|access[ _-]?tokens?)\b',
    r'\b(?:system|developer)\s+(?:prompts?|instructions?)\b',
    r'\b(?:ignore|override|bypass|disregard)\b[^.!?\n]{0,80}'
    r'\b(?:instructions?|rules?|guardrails?|safety|polic(?:y|ies))\b',
    r'<\s*/?\s*(?:system|developer)\b',
    r'\b(?:execute|run)\b[^.!?\n]{0,40}'
    r'\b(?:shell|operating system|terminal|powershell|bash|commands?)\b',
    r'\b(?:drop|alter)\s+(?:the\s+)?(?:constraints?|indexes?|databases?|tables?)\b',
    r'\bload\s+csv\b',
    r'\bcall\s+(?:db\.|dbms\.|gds\.|apoc\.|\{)',
    r'\b(?:create|merge)\s*\(',
    r'\b(?:detach\s+)?delete\s+[a-z_]\w*\s*(?:[,;}]|\breturn\b|$)',
    r'\bset\s+[a-z_]\w*\s*\.\s*[a-z_]\w*\s*=',
    r'\b(?:delete|remove)\s+(?:(?:all|every|the)\s+)?'
    r'(?:nodes?|relationships?|edges?|database|graph)\b',
    r'\b(?:set|update)\b[^.!?\n]{0,40}\b(?:all|every)\s+(?:names?|nodes?|properties)\b',
)


def blocked(question: str) -> bool:
    return any(re.search(pattern, question, re.I) for pattern in PATTERNS)
