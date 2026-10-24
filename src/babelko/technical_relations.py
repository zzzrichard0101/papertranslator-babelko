"""Conservative preservation of explicitly defined technical abbreviations."""
import collections
import re

from .document_context import definitions


REVISION = 'defined-acronym-relations-1'
STYLE = re.compile(r"<style\s+id=['\"]\d+['\"]>|</style>")
PARENTHETICAL = re.compile(r'\(([A-Z][A-Z0-9-]{1,11})\)')


def errors(source, target):
    if not isinstance(source, str) or not isinstance(target, str):
        return []
    source = STYLE.sub('', source)
    target = STYLE.sub('', target)
    defined = collections.Counter(short for short, _, _ in definitions(source))
    if not defined:
        return []
    rendered = collections.Counter(PARENTHETICAL.findall(target))
    # A translator may put an expansion in Korean without parenthesized Latin
    # initials. Judge only an explicit one-for-one parenthetical replacement.
    if sum(rendered.values()) == sum(defined.values()) and rendered != defined:
        return ['정의된 전문용어의 괄호 속 약어가 다른 약어로 바뀌었습니다.']
    return []
