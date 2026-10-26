"""Connect pretranslation source occurrences to tracked translation output.

Exact page-bound matches are evidence. Ambiguous and cross-page matches remain
explicitly weaker, so this map never declares semantic or spatial correctness.
"""

import collections

from .render_coverage import TOKENS, canonical, records
from .storage import digest, read, save


REVISION = 'source-tracker-export-1'


def text_key(value):
    return canonical(TOKENS.sub('', value or ''))


def build(source_evidence, tracker, selected, rendered):
    """Use the same tracker order as render_coverage.inspect()."""
    evidence = read(source_evidence)
    tracked = read(tracker)
    sources = [row for row in evidence.get('rows', [])
               if row.get('extractor') == 'il_paragraph' and text_key(row.get('text'))]
    keys = {row['id']: text_key(row['text']) for row in sources}
    by_page = collections.defaultdict(list)
    for row in sources:
        by_page[row['source_page']].append(row)
    exact = collections.defaultdict(collections.deque)
    for row in sources:
        exact[(row['source_page'], keys[row['id']])].append(row['id'])
    page_map = (isinstance(tracked, dict) and len(tracked.get('page', [])) == len(selected))
    items = []
    if page_map:
        for index, page in enumerate(tracked['page']):
            items.extend((selected[index] + 1, index + 1, row)
                         for row in records(page))
        for kind in ('cross_page', 'cross_column'):
            items.extend((None, None, row) for row in records(tracked.get(kind, [])))
    else:
        items.extend((None, None, row) for row in records(tracked))
    missing = {row['tracked_unit'] for row in (rendered or {}).get('missing', [])}
    links = []
    for index, (source_page, output_page, item) in enumerate(items):
        key = text_key(item.get('pdf_unicode'))
        ids = []
        match = 'unlinked' if key else 'nontext_token'
        if source_page is not None and key:
            candidates = exact[(source_page, key)]
            if candidates:
                ids = [candidates.popleft()]
                match = 'exact_page_occurrence'
            elif len(key) >= 16:
                candidates = [row['id'] for row in by_page[source_page]
                              if key in keys[row['id']]]
                if len(candidates) == 1:
                    ids = candidates
                    match = 'unique_page_fragment'
        # A cross-page or cross-column unit has no single output-page box. A
        # unique contained source occurrence remains useful for diagnosis.
        elif key and len(key) >= 24:
            candidates = [row['id'] for row in sources if keys[row['id']] in key
                          and len(keys[row['id']]) >= 24]
            if candidates:
                ids = sorted(set(candidates))
                match = 'cross_boundary_fragments'
        links.append(dict(tracked_unit=index, source_page=source_page,
                          output_page=output_page, source_region_ids=ids,
                          match=match, rendered='missing' if index in missing else 'present',
                          source_excerpt=item.get('pdf_unicode', '')[:160]))
    by_unit = {row['tracked_unit']: row for row in links}
    for issue in (rendered or {}).get('missing', []):
        link = by_unit.get(issue['tracked_unit'])
        issue['source_region_ids'] = link['source_region_ids'] if link else []
        issue['source_page'] = link['source_page'] if link else None
    return dict(revision=REVISION, source_evidence_sha256=digest(source_evidence),
                tracker_page_map=page_map, tracked_units=len(links),
                matched_units=sum(bool(row['source_region_ids']) for row in links),
                nontext_units=sum(row['match']=='nontext_token' for row in links),
                unlinked_units=sum(row['match']=='unlinked' for row in links),
                missing_rendered_units=len(missing), rows=links,
                scope='Source IL paragraph to tracked unit and output page; not exact glyph position or semantic certification')


def export(output, source_evidence, tracker, selected, rendered):
    """Write a source-bound link file beside the PDFs and return its manifest."""
    if not source_evidence.is_file() or not tracker.is_file():
        return dict(revision=REVISION, status='unavailable', reason='source or tracker missing')
    try:
        report = build(source_evidence, tracker, selected, rendered)
        path = output / 'Provenance.json'
        save(path, report)
        return dict(revision=REVISION, status='available', file=path.name,
                    sha256=digest(path), tracked_units=report['tracked_units'],
                    matched_units=report['matched_units'],
                    nontext_units=report['nontext_units'],
                    unlinked_units=report['unlinked_units'],
                    missing_rendered_units=report['missing_rendered_units'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(revision=REVISION, status='unavailable',
                    reason=type(exc).__name__ + ': ' + str(exc)[:200])
