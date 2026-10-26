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


REVISION = 'native-layer-to-il-evidence-2'
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


def region_id(source_hash, page_number, kind, box, value, ordinal=0):
    """Stable source occurrence identity, independent of parser object IDs."""
    payload = '\0'.join((source_hash, str(page_number), kind, str(box), value, str(ordinal)))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def same_visual_line(left, right):
    """Corroborate two extractors using position and words, not text alone."""
    a, b = left['box'], right['box']
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    words_a, words_b = set(left['tokens']), set(right['tokens'])
    return bool(area > 0 and overlap/area >= .45 and words_a and words_b
                and len(words_a & words_b)/min(len(words_a), len(words_b)) >= .65)


def evidence_export_valid(output, coverage):
    """Check a declared evidence file; legacy reports have no declaration."""
    meta = (coverage or {}).get('evidence_ledger') or {}
    if not meta:
        return True
    path = output / 'SourceEvidence.json'
    return bool(meta.get('status') == 'available' and meta.get('sha256')
                and path.is_file() and digest(path) == meta['sha256'])


def inspect(input_pdf, docs, cancel=None, pixel_rows=None):
    """Compare native PDF rows with IL text before any model sees it."""
    started = time.perf_counter()
    pixel_rows = pixel_rows or {}
    pages = []
    evidence_rows = []
    source_hash = digest(input_pdf)
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
            paragraph_rows = []
            for index, paragraph in enumerate(paragraphs):
                value = getattr(paragraph, 'unicode', '') or ''
                original_box = getattr(paragraph, 'box', None)
                position = ([round(float(getattr(original_box, key)), 2)
                             for key in ('x', 'y', 'x2', 'y2')]
                            if original_box is not None else None)
                paragraph_rows.append(dict(
                    id=region_id(source_hash, number + 1, 'il_paragraph', None, value, index),
                    source_page=number + 1, extractor='il_paragraph',
                    box=position, box_coordinate_system='pdf_bottom_left',
                    text=value,
                    resolution='parsed',
                    text_sha256=hashlib.sha256(value.encode('utf-8')).hexdigest(),
                    excerpt=value[:160],
                    tokens=evidence_tokens(value)))
            evidence_rows.extend({key: value for key, value in paragraph.items() if key != 'tokens'}
                                 for paragraph in paragraph_rows)
            paragraph_terms = [(paragraph['id'], set(paragraph['tokens']))
                               for paragraph in paragraph_rows]
            candidates = list(source_lines(source[number]))
            independent = [candidate_line(row.get('text', ''), row['bbox'])
                           for row in pixel_rows.get(number, [])
                           if row.get('score', 0) >= .94 and row.get('bbox')]
            independent = [row for row in independent if row]
            def missing(lines, source_name):
                suspect = []
                for ordinal, line in enumerate(lines):
                    lexical, sequence = line_score(line, parsed_unique, parsed_triples)
                    matched = lexical >= .45 or sequence >= .2
                    resolution = ('matched' if sequence >= .2 else
                                  'weak_match' if lexical >= .45 else 'suspected_missing')
                    linked = []
                    line_terms = set(line['tokens'])
                    for paragraph_id, para_terms in paragraph_terms:
                        score = len(line_terms & para_terms)/len(line_terms)
                        if score >= .45:
                            linked.append((round(score, 3), paragraph_id))
                    linked.sort(reverse=True)
                    identity = region_id(source_hash, number + 1, source_name,
                                         line['box'], line['text'], ordinal)
                    evidence_rows.append(dict(id=identity, source_page=number + 1,
                        extractor=source_name, box=line['box'], text=line['text'],
                        text_sha256=hashlib.sha256(line['text'].encode('utf-8')).hexdigest(),
                        il_paragraph_ids=[key for _, key in linked[:3]],
                        resolution=resolution,
                        lexical=lexical, sequence=sequence, corroborated_by=[]))
                    if not matched:
                        suspect.append(dict(line_id=identity, box=line['box'],
                                            excerpt=line['text'][:160], lexical=lexical,
                                            sequence=sequence))
                return suspect
            start = len(evidence_rows)
            native_missing = missing(candidates, 'native')
            pixel_missing = missing(independent, 'pixels')
            native_rows = evidence_rows[start:start + len(candidates)]
            pixel_evidence = evidence_rows[start + len(candidates):]
            for native, native_line in zip(native_rows, candidates):
                for pixel, pixel_line in zip(pixel_evidence, independent):
                    if same_visual_line(native_line, pixel_line):
                        native['corroborated_by'].append(pixel['id'])
                        pixel['corroborated_by'].append(native['id'])
            pixel_status = {entry['id']: entry['resolution'] for entry in pixel_evidence}
            corroborated = [entry['id'] for entry in native_rows
                            if entry['resolution'] == 'suspected_missing'
                            and any(pixel_status.get(peer) == 'suspected_missing'
                                    for peer in entry['corroborated_by'])]
            pages.append(dict(source_page=number + 1, native_candidate_lines=len(candidates),
                              il_paragraphs=len(paragraphs), suspected_missing=native_missing,
                              pixel_candidate_rows=len(independent),
                              pixel_suspected_missing=pixel_missing,
                              corroborated_suspected_missing=corroborated,
                              il_region_ids=[paragraph['id'] for paragraph in paragraph_rows]))
    return dict(revision=REVISION, status='diagnostic', input_sha256=source_hash,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                inspected_pages=len(pages), candidate_lines=sum(p['native_candidate_lines'] for p in pages),
                suspected_missing_lines=sum(len(p['suspected_missing']) for p in pages),
                weak_match_lines=sum(row['resolution']=='weak_match' for row in evidence_rows
                                     if row['extractor']=='native'),
                pixel_checked_pages=len(pixel_rows),
                pixel_candidate_rows=sum(p['pixel_candidate_rows'] for p in pages),
                pixel_suspected_missing_rows=sum(len(p['pixel_suspected_missing']) for p in pages),
                corroborated_suspected_missing_lines=sum(len(p['corroborated_suspected_missing']) for p in pages),
                pages_without_prose_evidence=[p['source_page'] for p in pages
                                              if not p['native_candidate_lines'] and not p['pixel_candidate_rows']],
                pages=pages, evidence_rows=evidence_rows,
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
            rows = report.pop('evidence_rows', None)
            if rows is not None:
                path = folder / 'source-evidence.json'
                original_pdf = folder / 'Original.pdf'
                original_sha256 = digest(original_pdf) if original_pdf.is_file() else report['input_sha256']
                report['original_sha256'] = original_sha256
                save(path, dict(revision=REVISION, input_sha256=report['input_sha256'],
                                original_sha256=original_sha256, rows=rows))
                report['evidence_ledger'] = dict(file='SourceEvidence.json',
                                                 sha256=digest(path), rows=len(rows))
            save(folder / 'source-coverage.json', report)
        return original(self, docs)

    with patch.object(ILTranslatorLLMOnly, 'translate', translate):
        yield
