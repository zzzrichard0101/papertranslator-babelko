"""Recover a PDF's simple shifted character encoding in extracted text.

Some born-digital figures expose character codes as NUL-prefixed ASCII. The
observed font maps each printable code to Unicode code point +29. Keep the raw
IL for layout and tracking, and use this reading only for translation checks.
"""
import re

ENCODED_RUN=re.compile(r'(?:\x00[\x21-\x5e]){2,}')
PLACEHOLDER=re.compile(r'\{v\d+\}')


def decode(text):
    if not isinstance(text,str) or '\x00' not in text:return text
    def recover(match):
        codes=match.group()[1::2]
        return ''.join(chr(ord(char)+29) for char in codes)
    return ENCODED_RUN.sub(recover,text)


def metric_identifiers(text):
    """A sequence of metric codes and cells is data, not English prose."""
    original=decode(text) or ''
    text=PLACEHOLDER.sub(' ',original).strip()
    names=re.findall(r'[A-Za-z][A-Za-z0-9-]*',text)
    return (len(names)>=2 and len(PLACEHOLDER.findall(original))>=2 and
        all(re.fullmatch(r'[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)?',name) for name in names) and
        not re.sub(r'[A-Za-z0-9\s,-]','',text))
