"""Local PDF geometry for an optional, read-only particle atlas.

The atlas describes visible source regions. A colored region reports only the
evidence actually available; a completed job is not a semantic certificate.
"""

import math
from functools import lru_cache
from pathlib import Path

import pymupdf


MAX_REGIONS = 90
MAX_PARTICLES = 900


def _clip_box(box, width, height):
    x0, y0, x1, y1 = [float(value) for value in box]
    x0, x1 = sorted((max(0.0, min(width, x0)), max(0.0, min(width, x1))))
    y0, y1 = sorted((max(0.0, min(height, y0)), max(0.0, min(height, y1))))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return [x0, y0, x1, y1]


def _overlaps(first, second):
    return (first[0] < second[2] and first[2] > second[0]
            and first[1] < second[3] and first[3] > second[1])


def _suspect_boxes(coverage, page_number):
    for row in coverage.get('pages', []):
        if row.get('source_page') != page_number:
            continue
        return [entry['box'] for key in ('suspected_missing', 'pixel_suspected_missing')
                for entry in row.get(key, []) if isinstance(entry.get('box'), list)]
    return []


@lru_cache(maxsize=32)
def _geometry(source, size, mtime_ns, page_index):
    """Reuse PDF analysis when browsing back and forth between pages."""
    with pymupdf.open(source) as document:
        if not 0 <= page_index < len(document):
            raise ValueError('문서 쪽 범위를 벗어났습니다.')
        page = document[page_index]
        width, height = page.rect.width, page.rect.height
        candidates = []
        for block in page.get_text('blocks'):
            if len(block) < 7 or block[6] != 0:
                continue
            content = str(block[4]).strip()
            clipped = _clip_box(block[:4], width, height)
            if not content or clipped is None:
                continue
            candidates.append(dict(kind='text', box=clipped, excerpt=' '.join(content.split())[:150],
                                   weight=min(65, max(5, round(math.sqrt(len(content)) * 3)))))
        for image in page.get_image_info():
            clipped = _clip_box(image.get('bbox', (0, 0, 0, 0)), width, height)
            if clipped is None:
                continue
            candidates.append(dict(kind='image', box=clipped, excerpt='원본 이미지 영역', weight=50))
        try:
            tables = page.find_tables().tables
            for table in tables:
                if table.row_count < 2 or table.col_count < 2:
                    continue
                clipped = _clip_box(table.bbox, width, height)
                if clipped is not None:
                    candidates.append(dict(kind='table', box=clipped, excerpt='원본 표 후보 영역', weight=65))
        except (ValueError, RuntimeError):
            # The atlas is optional; malformed vector drawings must not block
            # reading or translating the document.
            pass

        # Prefer the largest readable regions if a pathological PDF reports
        # thousands of drawing fragments. This is a visualization budget only.
        candidates.sort(key=lambda row: (row['kind'] != 'text', -row['weight']))
        candidates = candidates[:MAX_REGIONS]
        total = sum(row['weight'] for row in candidates) or 1
        scale = min(1.0, MAX_PARTICLES / total)
        return len(document), width, height, candidates, scale


def snapshot(source, page_index, *, coverage=None, translated_pages=None,
             processing_pages=None, selected_pages=None):
    """Return bounded, normalized blocks for one page; no OCR or model call.

    Status is based on page-specific evidence, never merely on a job-wide flag.
    All page sets use one-based physical PDF page numbers.
    """
    source = Path(source)
    stat = source.stat()
    pages, width, height, candidates, scale = _geometry(
        str(source.resolve()), stat.st_size, stat.st_mtime_ns, page_index)
    page_number = page_index + 1
    suspect = _suspect_boxes(coverage or {}, page_number)
    if selected_pages is not None and page_number not in selected_pages:
        base_status = 'outside_selection'
    elif page_number in (translated_pages or ()):
        base_status = 'output_created'
    elif page_number in (processing_pages or ()):
        base_status = 'processing'
    else:
        base_status = 'unprocessed'
    regions = []
    for index, row in enumerate(candidates):
        box = row['box']
        status = ('source_gap_suspected' if row['kind'] == 'text'
                  and any(_overlaps(box, gap) for gap in suspect)
                  else 'source_preserved' if row['kind'] == 'image' else base_status)
        regions.append(dict(id=f'{page_number}:{index}', kind=row['kind'], status=status,
                            x=round(box[0] / width, 5), y=round(box[1] / height, 5),
                            w=round((box[2] - box[0]) / width, 5),
                            h=round((box[3] - box[1]) / height, 5),
                            particles=max(2, round(row['weight'] * scale)),
                            excerpt=row['excerpt']))
    return dict(source_page=page_number, total_pages=pages,
                aspect=round(width / height, 5), regions=regions,
                suspect_regions=sum(row['status'] == 'source_gap_suspected' for row in regions),
                scope='PDF native text blocks and raster image boxes; visual grouping is approximate')
