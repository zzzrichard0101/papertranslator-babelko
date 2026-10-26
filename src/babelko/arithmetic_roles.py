"""Conservative source-grounded checks for multi-step arithmetic prose.

This is a defect detector, not a translator. Single operations and mathematical
notation are left to the bilingual auditor because their Korean surface forms
are too varied for a reliable count comparison.
"""

import collections
import re


SOURCE_OPERATION = re.compile(
    r'\b(?P<verb>add(?:ed|ing)?|subtract(?:ed|ing)?|multipl(?:y|ied|ying)|'
    r'divid(?:e|ed|ing))\s+(?P<operand>(?:\d+(?:\.\d+)?|it|them)\b)',
    re.I,
)
TARGET_OPERATION = re.compile(
    r'(?P<add>더하|더해|더한|더했|추가하|추가한|추가해|추가했|가산|합산)'
    r'|(?P<subtract>빼|뺀|뺐|제하|차감|감산)'
    r'|(?P<multiply>곱하|곱해|곱한|곱했|곱하였|곱셈)'
    r'|(?P<divide>나누|나눈|나눴|나눗셈|제산)',
)
NOTATION = re.compile(r'[+×÷]|[−-]\s*(?:\d|\{v\d+\})|\b(?:sqrt|frac)\s*\(', re.I)
KOREAN = re.compile(r'[가-힣]')


def source_claims(source):
    """Return explicit ordered operations with their literal or resolved operand."""
    claims = []
    previous_number = None
    for match in SOURCE_OPERATION.finditer(source):
        verb = match['verb'].lower()
        operation = ('add' if verb.startswith('add') else
                     'subtract' if verb.startswith('subtract') else
                     'multiply' if verb.startswith('multipl') else 'divide')
        operand = match['operand']
        if operand.lower() in {'it', 'them'}:
            operand = previous_number
        else:
            previous_number = operand
        # A pronoun without a local numeric antecedent cannot be verified here.
        if operand is None:
            continue
        following = source[match.end():match.end() + 80]
        scope = 'inside_square_root' if re.match(r'\s+(?:in|inside|within)\s+(?:the\s+)?square\s+root\b', following, re.I) else None
        claims.append(dict(operation=operation, operand=operand, scope=scope,
                           source_span=match.group()))
    return claims


def errors(source, target):
    claims = source_claims(source)
    if len(claims) < 2 or not KOREAN.search(target) or NOTATION.search(target):
        return []
    required = collections.Counter(c['operation'] for c in claims)
    observed = collections.Counter(m.lastgroup for m in TARGET_OPERATION.finditer(target))
    # Extra Korean arithmetic words may explain a formula in prose. Flag only
    # definitely missing steps; the bilingual audit handles added claims.
    missing = required - observed
    if not missing:
        return []
    names = {'add': '더하기', 'subtract': '빼기', 'multiply': '곱하기', 'divide': '나누기'}
    detail = ', '.join(f'{names[k]} {v}회' for k, v in missing.items())
    return [f'원문 연산 단계 누락: {detail}. 숫자 출현만 맞추지 말고 각 연산의 대상과 순서를 복원하세요.']
