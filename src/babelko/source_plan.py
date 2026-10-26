"""Classify source tokens before inference without changing the PDF text.

Only exact, high-confidence identifiers are locked. Ordinary capitalized
words remain prose, and an uncertain classification never exempts a unit from
translation or final source/target checks.
"""

import collections
import re


REVISION = 'source-anchor-profile-1'
STYLE_OR_FORMULA = r"\{v\d+\}|<style\s+id=['\"]\d+['\"]>|</style>"
STYLED_NUMBER = r"\d+<style\s+id=['\"]\d+['\"]>[,.]</style>\d+"
URL = r'https?://[^\s<>]+'
EMAIL = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
DOI = r'(?<![A-Za-z0-9])10\.\d{4,9}/[A-Za-z0-9._;()/:-]+'
# Letter/digit model IDs with a separator, such as LLaVA-665K. A plain
# hyphenated English word is deliberately not an identifier.
MODEL_ID = (r'(?<![A-Za-z0-9_])(?=[A-Za-z0-9._/-]*\d)'
            r'(?:[A-Z]{2,}[A-Za-z0-9]*|[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*)'
            r'(?:[-_/][A-Za-z0-9.]+)+(?![A-Za-z0-9_])')
NUMBER = r'(?<![A-Za-z0-9])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![A-Za-z0-9])'
SPINE = re.compile('|'.join((STYLED_NUMBER, STYLE_OR_FORMULA, URL, EMAIL, DOI, MODEL_ID, NUMBER)))
IDENTIFIERS = re.compile('|'.join((URL, EMAIL, DOI, MODEL_ID)))
KOREAN = re.compile(r'[가-힣]')


def locked_identifiers(source):
    """Return exact source identifiers, longest first, without URL overlap."""
    tokens = []
    for match in IDENTIFIERS.finditer(source):
        token = match.group().rstrip('.,;:')
        if token.lower().startswith(('http://','https://')):
            # A PDF may split a URL at an inline formula/style boundary.
            # Its prefix is not an exact identifier until the source is joined.
            if (token.endswith('/') or re.fullmatch(r'https?://doi\.org/10',token,re.I)
                or source[match.end():].startswith(('{v','<style'))):
                continue
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def profile(source):
    structural = len(re.findall(STYLE_OR_FORMULA, source))
    identifiers = locked_identifiers(source)
    numeric_source = source
    for identifier in identifiers:
        numeric_source = numeric_source.replace(identifier, ' ')
    quantities = len(re.findall(NUMBER, re.sub(STYLE_OR_FORMULA, ' ', numeric_source)))
    return dict(revision=REVISION, structural_tokens=structural,
                quantity_tokens=quantities, locked_identifiers=identifiers,
                risk='high' if structural >= 3 or quantities >= 3 or identifiers else 'ordinary')


def identifier_errors(source, target):
    """Never silently change an exact URL, DOI, email, or model ID."""
    if not isinstance(target, str) or not KOREAN.search(target):
        return []
    for token in locked_identifiers(source):
        if source.count(token) != target.count(token):
            return ['보호 식별자 누락 또는 변경']
    return []


def failure_summary(failures):
    """Explain unresolved evidence; this does not certify an error or override QA."""
    kinds = collections.Counter()
    for row in failures:
        error = row.get('error', '')
        if '숫자·부호' in error:
            kind = 'quantity'
        elif '영어' in error or '인코딩된 글꼴' in error:
            kind = 'untranslated_or_identifier'
        elif '문장별 원문·번역 대조' in error:
            kind = 'meaning_review'
        elif '자리표시자' in error or '서식' in error or '보호 식별자' in error:
            kind = 'protected_structure'
        else:
            kind = 'other'
        kinds[kind] += 1
    return dict(revision=REVISION, total=len(failures), by_kind=dict(kinds),
                interpretation='Unresolved source-grounded checks; automatic labels do not distinguish real errors from false alarms.')
