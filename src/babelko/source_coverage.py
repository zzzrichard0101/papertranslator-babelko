"""Independent native-text-layer to pretranslation IL comparison.

This is deliberately diagnostic. PDF text extraction is not an OCR oracle:
figures, encodings, formula runs and reading-order repairs can differ.  The
report supplies source-grounded locations for a later calibrated completion
gate without silently changing the translation or its checkpoints.
"""
import hashlib
import re
import time
import unicodedata
from contextlib import contextmanager
from unittest.mock import patch

import pymupdf

from .storage import digest, save


REVISION = 'native-layer-to-il-1'
STYLE = re.compile(r'<[^>]+>|\{v\d+\}')
TOKEN = re.compile(r'[a-z]{3,}|\d+(?:[.,]\d+)*')
COMMON = frozenset({'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are',
                    'was', 'were', 'into', 'which', 'have', 'has', 'been',
                    'using', 'also', 'their', 'these', 'those', 'such'})


def words(value):
    value = unicodedata.normalize('NFKC', STYLE.sub(' ', value or '')).lower()
    return TOKEN.findall(value.replace('\u00ad', ''))


def evidence_tokens(value):
    return [word for word in words(value) if len(word) >= 4 and word not in COMMON]


def candidate_line(phrase, box):
    terms = evidence_tokens(phrase)
    # Short figure labels, table cells and page furniture do not establish
    # prose omission on their own. They remain outside this first scope.
    if len(words(phrase)) < 6 or len(set(terms)) < 4:
        return None
    box = [round(float(number), 2) for number in box]
    # arXiv stamps and marginal citations are often printed vertically.
    if box[3] - box[1] > 2 * (box[2] - box[0]):
        return None
    return dict(text=phrase, box=box, tokens=terms)


def source_lines(page):
    """Return visual native text rows; do not trust content-stream order."""
    grouped = {}
    for x0, y0, x1, y1, value, block, line, ordinal in page.get_text('words'):
        grouped.setdefault((block, line), []).append((ordinal, value, (x0, y0, x1, y1)))
    for row in grouped.values():
        row.sort(key=lambda item: item[0])
        phrase = ' '.join(value for _, value, _ in row)
        boxes = [box for _, _, box in row]
        box = [round(min(b[0] for b in boxes), 2), round(min(b[1] for b in boxes), 2),
               round(max(b[2] for b in boxes), 2), round(max(b[3] for b in boxes), 2)]
        candidate = candidate_line(phrase, box)
        if candidate:
            yield candidate


def line_score(line, parsed_unique, parsed_triples):
    """Combine order-sensitive and distinct-word evidence conservatively."""
    tokens = line['tokens']
    if not parsed_unique:
        return 0.0, 0.0
    source_unique = set(tokens)
    lexical = len(source_unique & parsed_unique) / len(source_unique)
    triples = set(zip(tokens, tokens[1:], tokens[2:]))
    sequence = len(triples & parsed_triples) / len(triples) if triples else 0.0
    return round(lexical, 3), round(sequence, 3)


def inspect(input_pdf, docs, cancel=None, pixel_rows=None):
    """Compare native PDF rows with IL text before any model sees it."""
    started = time.perf_counter()
    pixel_rows = pixel_rows or {}
    pages = []
    with pymupdf.open(input_pdf) as source:
        for page in docs.page:
            if cancel and cancel():
                raise InterruptedError('취소됨')
            number = getattr(page, 'page_number', None)
            if not isinstance(number, int) or not 0 <= number < len(source):
                raise ValueError('IL source page number does not match the input PDF')
            paragraphs = getattr(page, 'pdf_paragraph', [])
            parsed = [word for paragraph in paragraphs
                      for word in evidence_tokens(getattr(paragraph, 'unicode', ''))]
            parsed_unique = set(parsed)
            parsed_triples = set(zip(parsed, parsed[1:], parsed[2:]))
            candidates = list(source_lines(source[number]))
            independent = [candidate_line(row.get('text', ''), row['bbox'])
                           for row in pixel_rows.get(number, [])
                           if row.get('score', 0) >= .94 and row.get('bbox')]
            independent = [row for row in independent if row]
            def missing(lines, source_name):
                suspect = []
                for line in lines:
                    lexical, sequence = line_score(line, parsed_unique, parsed_triples)
                    if lexical >= 0.45 or sequence >= 0.2:
                        continue
                    identity = hashlib.sha256((str(number) + '\0' + source_name + '\0' +
                                               line['text'] + '\0' + str(line['box'])).encode('utf-8')).hexdigest()
                    suspect.append(dict(line_id=identity, box=line['box'],
                                        excerpt=line['text'][:160], lexical=lexical,
                                        sequence=sequence))
                return suspect
            pages.append(dict(source_page=number + 1, native_candidate_lines=len(candidates),
                              il_paragraphs=len(paragraphs), suspected_missing=missing(candidates, 'native'),
                              pixel_candidate_rows=len(independent),
                              pixel_suspected_missing=missing(independent, 'pixels')))
    return dict(revision=REVISION, status='diagnostic', input_sha256=digest(input_pdf),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                inspected_pages=len(pages), candidate_lines=sum(p['native_candidate_lines'] for p in pages),
                suspected_missing_lines=sum(len(p['suspected_missing']) for p in pages),
                pixel_checked_pages=len(pixel_rows),
                pixel_candidate_rows=sum(p['pixel_candidate_rows'] for p in pages),
                pixel_suspected_missing_rows=sum(len(p['pixel_suspected_missing']) for p in pages),
                pages_without_prose_evidence=[p['source_page'] for p in pages
                                              if not p['native_candidate_lines'] and not p['pixel_candidate_rows']],
                pages=pages,
                scope='Native/OCR-input text layer and already available independent high-confidence '
                      'scan OCR rows versus pretranslation IL prose; not full source-image OCR recall, '
                      'figure/table coverage, or a completion gate')


@contextmanager
def capture(folder, input_pdf, cancel=None, pixel_rows=None):
    """Record the first native pass in either translation mode, unchanged."""
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly

    original = ILTranslatorLLMOnly.translate
    captured = False

    def translate(self, docs):
        nonlocal captured
        if not captured:
            captured = True
            try:
                report = inspect(input_pdf, docs, cancel, pixel_rows)
            except InterruptedError:
                raise
            except Exception as exc:
                report = dict(revision=REVISION, status='unavailable', error=type(exc).__name__ + ': ' + str(exc)[:240],
                              scope='Diagnostic native text-layer comparison failed; translation continues')
            save(folder / 'source-coverage.json', report)
        return original(self, docs)

    with patch.object(ILTranslatorLLMOnly, 'translate', translate):
        yield
