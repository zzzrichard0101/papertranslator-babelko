"""High-confidence bindings between an exact number and its unit or label.

Only explicit surface forms are checked. This is deliberately not a parser for
all scientific prose and never infers a Korean translation of an English term.
"""
import collections
import re
import unicodedata
from .technical_relations import errors as technical_errors


REVISION = 'quantity-and-defined-term-relations-2'
STYLE = re.compile(r"<style\s+id=['\"]\d+['\"]>|</style>")
FORMULA = re.compile(r'\{v\d+\}')
NUMBER = r'[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+−-]?\d+)?'
SYMBOLS = {
    'µg': 'ug', 'μg': 'ug', 'ug': 'ug', 'mg': 'mg', 'g': 'g', 'kg': 'kg',
    'mg/dL': 'mg/dL', 'mmol/L': 'mmol/L',
    'mm': 'mm', 'cm': 'cm', 'km': 'km', 'nm': 'nm',
    'µm': 'um', 'μm': 'um', 'um': 'um', 'ms': 'ms',
    'Hz': 'Hz', 'kHz': 'kHz', 'MHz': 'MHz',
    'Pa': 'Pa', 'kPa': 'kPa', 'MPa': 'MPa',
    'mM': 'mM', 'µM': 'uM', 'μM': 'uM', 'uM': 'uM',
    'mL': 'mL', 'ml': 'mL', 'MB': 'MB', 'GB': 'GB', '%': '%',
}
KOREAN = {
    '마이크로그램': 'ug', '밀리그램': 'mg', '그램': 'g', '킬로그램': 'kg',
    '밀리미터': 'mm', '센티미터': 'cm', '킬로미터': 'km', '나노미터': 'nm',
    '마이크로미터': 'um', '밀리초': 'ms',
    '헤르츠': 'Hz', '킬로헤르츠': 'kHz', '메가헤르츠': 'MHz',
    '파스칼': 'Pa', '킬로파스칼': 'kPa', '메가파스칼': 'MPa',
    '밀리리터': 'mL', '메가바이트': 'MB', '기가바이트': 'GB', '퍼센트': '%',
}
UNIT = '|'.join(re.escape(x) for x in sorted((*SYMBOLS, *KOREAN), key=len, reverse=True))
PAIR = re.compile(r'(?<![\w.])(?P<number>' + NUMBER + r')\s*(?P<unit>' + UNIT + r')(?![A-Za-z])')
SHARED_RANGE = re.compile(r'(?<![\w.])(?P<low>' + NUMBER + r')\s*(?:[-–—~]|\bto\b|에서|부터)\s*'
                          r'(?P<high>' + NUMBER + r')\s*(?P<unit>' + UNIT + r')(?![A-Za-z])')
LABEL = re.compile(r'(?<![\w])(?P<label>[A-Za-z][A-Za-z0-9_]{0,15})\s*[:=]\s*(?P<number>' + NUMBER + r')(?![A-Za-z0-9_])')
SOURCE_GROUP = re.compile(r'\b(?:[Gg]roup|[Aa]rm|[Cc]ohort|[Cc]ondition|[Ss]ample)\s+(?P<id>[A-Z]{1,4})\b')
TARGET_GROUP = re.compile(r'(?<![A-Za-z0-9])(?P<id>[A-Z]{1,4})\s*(?:군|그룹|집단|조건|표본)')
BARE_NUMBER = re.compile(r'(?<![A-Za-z0-9_.])' + NUMBER + r'(?![0-9.])')


def visible(text):
    return unicodedata.normalize('NFKC', FORMULA.sub(' ', STYLE.sub('', text)))


def canonical_number(text):
    return text.replace(',', '').replace('−', '-')


def units(text):
    result = collections.Counter()
    text = visible(text)
    text = SHARED_RANGE.sub(lambda m: m['low'] + ' ' + m['unit'] + ' to ' + m['high'] + ' ' + m['unit'], text)
    for match in PAIR.finditer(text):
        token = match['unit']
        # 2%포인트 is a percentage-point delta, not the 2% rate. The existing
        # percentage-point validator handles that relation separately.
        if token == '%' and re.match(r'\s*포인트', text[match.end():]):
            continue
        result[(canonical_number(match['number']), SYMBOLS.get(token, KOREAN.get(token)))] += 1
    return result


def labels(text):
    result = collections.defaultdict(collections.Counter)
    for match in LABEL.finditer(visible(text)):
        result[match['label']][canonical_number(match['number'])] += 1
    return result


def group_values(text, pattern):
    """Bind groups only when each appears once and precedes one quantity."""
    text = visible(text)
    matches = list(pattern.finditer(text))
    if len(matches) < 2 or len({m['id'].upper() for m in matches}) != len(matches):
        return None
    result = {}
    for index, match in enumerate(matches):
        section = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        numbers = [canonical_number(m.group()) for m in BARE_NUMBER.finditer(section)]
        if len(numbers) != 1:
            return None
        result[match['id'].upper()] = numbers[0]
    return result


def errors(source, target):
    if not isinstance(source, str) or not isinstance(target, str):
        return []
    found = []
    original_units = units(source)
    if original_units and original_units != units(target):
        found.append('수치와 단위의 대응이 원문과 다릅니다.')
    original_labels, translated_labels = labels(source), labels(target)
    if any(original_labels[key] != translated_labels[key] for key in original_labels.keys() & translated_labels.keys()):
        found.append('식별자와 수치의 대응이 원문과 다릅니다.')
    source_groups = group_values(source, SOURCE_GROUP)
    target_groups = group_values(target, TARGET_GROUP)
    if source_groups and target_groups and source_groups.keys() == target_groups.keys() and source_groups != target_groups:
        found.append('집단 식별자와 수치의 대응이 원문과 다릅니다.')
    found.extend(technical_errors(source, target))
    return found
