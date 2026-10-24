"""Build a source-bound, blinded real-document translation review.

The private pack stays in test_vault. Model output and automated checks are
never treated as expert gold. A review is scored only after independent human
annotations have been supplied for all three candidates of each item.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from babelko.storage import digest, read, save

METHODS = ('hy_draft', 'qwen_single', 'hybrid')
ISSUES = ('omission', 'addition', 'reversed_meaning', 'wrong_relation', 'terminology', 'other')


def fingerprint(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def eligible(row):
    source = row.get('source', '')
    return (row.get('label') in {'text', 'plain text'} and
            isinstance(source, str) and 90 <= len(source) <= 1000 and
            len(re.findall(r'[A-Za-z]{3,}', source)) >= 16 and
            all(isinstance(row.get(k), str) and row[k].strip() for k in ('draft', 'final')) and
            not row.get('final_error'))


def prepare(corpus, output, per_document=2):
    if per_document < 1:
        raise ValueError('per_document must be positive')
    manifest = read(corpus / 'manifest.json')
    rows = []
    for case in manifest['cases']:
        if case['key'] == 'controlled':
            continue
        source_file = Path(case['source'])
        if digest(source_file) != case['sha256']:
            raise ValueError(f"Source PDF changed: {case['key']}")
        run_path = corpus / 'runs' / (case['key'] + '.json')
        if not run_path.is_file():
            continue
        run = read(run_path)
        job = Path(run['job'])
        candidates = []
        for path in (job / 'hybrid').glob('*.json'):
            row = read(path)
            if eligible(row):
                candidates.append(row)
        # Deterministic stratification by length, not by model decision or QA.
        candidates.sort(key=lambda r: (len(r['source']), fingerprint(r['source'])))
        for slot in range(per_document):
            if not candidates:
                break
            row = candidates[round((slot + .5) * (len(candidates) - 1) / per_document)]
            item_id = fingerprint(case['sha256'] + '\0' + row['source'])[:20]
            if any(x['item_id'] == item_id for x in rows):
                continue
            rows.append(dict(item_id=item_id, document=case['key'], source_pdf_sha256=case['sha256'],
                             source=row['source'], source_sha256=fingerprint(row['source']),
                             label=row['label'], context=row.get('context', ''),
                             candidates=dict(hy_draft=row['draft'], hybrid=row['final'])))
    output.mkdir(parents=True, exist_ok=True)
    pack = dict(schema=1, scope='selected real PDF units; no expert labels or accuracy score yet',
                corpus_manifest_sha256=digest(corpus / 'manifest.json'), items=rows)
    save(output / 'private-pack.json', pack)
    return pack


def make_review(pack, *, require_all=True):
    items = []
    for row in pack['items']:
        if require_all and set(row['candidates']) != set(METHODS):
            continue
        methods = [m for m in METHODS if m in row['candidates']]
        methods.sort(key=lambda m: fingerprint(row['item_id'] + '\0' + m))
        options = {chr(65 + i): row['candidates'][method] for i, method in enumerate(methods)}
        items.append(dict(item_id=row['item_id'], document=row['document'], source=row['source'],
                          source_sha256=row['source_sha256'], options=options))
    return dict(schema=1, instructions='Compare each option to the English source. Record all major omissions, additions, reversed meanings and wrong relations with a source quote. Model identities are withheld.',
                items=items)


def export_review(pack, output):
    review = make_review(pack)
    save(output / 'review-blind.json', review)
    key = {}
    for row in pack['items']:
        if set(row['candidates']) != set(METHODS):
            continue
        methods = sorted(METHODS, key=lambda m: fingerprint(row['item_id'] + '\0' + m))
        key[row['item_id']] = {chr(65 + i): m for i, m in enumerate(methods)}
    save(output / 'answer-key.json', key)
    return review


def run_qwen(pack, output):
    """Translate frozen source units with Qwen alone; never edit source/final."""
    from babelko.engine import LocalEngine
    from babelko.translator import KoreanTranslator
    from pdf2zh_next.config.model import SettingsModel, TranslationSettings
    from pdf2zh_next.config.translate_engine_model import OpenAISettings
    from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter

    with LocalEngine(output, key='qwen38') as engine:
        engine.start(lambda *_: None)
        settings = SettingsModel(translation=TranslationSettings(lang_in='en', lang_out='ko'),
            translate_engine_settings=OpenAISettings(
            openai_model=engine.model['id'], openai_base_url=engine.url,
            openai_api_key=engine.key, openai_timeout='300'))
        translator = KoreanTranslator(settings, BaseRateLimiter(), output)
        try:
            for row in pack['items']:
                if 'qwen_single' in row['candidates']:
                    continue
                try:
                    target = translator._checked_plain(translator.prompt(row['source']), row['source'])
                    row['candidates']['qwen_single'] = target
                    row['qwen_model_sha256'] = engine.model['sha256']
                    save(output / 'private-pack.json', pack)
                    print(row['document'], row['item_id'], 'done', flush=True)
                except Exception as exc:
                    row['qwen_error'] = type(exc).__name__ + ': ' + str(exc)
                    save(output / 'private-pack.json', pack)
                    print(row['document'], row['item_id'], 'failed', flush=True)
        finally:
            translator.client.close()
    return pack


def structural_report(pack):
    """Observable contract failures, explicitly separate from meaning scores."""
    from babelko.hybrid import errors
    results = {}
    for method in METHODS:
        checked = []
        unavailable = []
        for row in pack['items']:
            target = row['candidates'].get(method)
            if target is None:
                unavailable.append(dict(item_id=row['item_id'], document=row['document'],
                                        error=row.get('qwen_error') if method == 'qwen_single' else None))
                continue
            checked.append(dict(item_id=row['item_id'], document=row['document'],
                                issues=errors(row['source'], target, row['label'])))
        results[method] = dict(available=len(checked), unavailable=unavailable,
                               flagged=[x for x in checked if x['issues']])
    return dict(scope='Automatic source/target contract checks only; semantic accuracy not scored',
                total_items=len(pack['items']), methods=results)


def score(pack, review, annotations):
    if not annotations.get('reviewer_id') or not annotations.get('independent_of_model_generation'):
        raise ValueError('Independent reviewer attestation required')
    answer_key = {row['item_id']: {letter: method for letter, method in zip(
        sorted(make_review(dict(items=[row]))['items'][0]['options']),
        sorted(METHODS, key=lambda m: fingerprint(row['item_id'] + '\0' + m)))}
        for row in pack['items'] if set(row['candidates']) == set(METHODS)}
    expected = {row['item_id'] for row in review['items']}
    if not expected:
        raise ValueError('No complete three-method review items')
    canonical = make_review(pack)
    if review != canonical:
        raise ValueError('Blinded review differs from frozen source/candidates')
    judgments = annotations.get('items', [])
    if len(judgments) != len(expected) or {x.get('item_id') for x in judgments} != expected:
        raise ValueError('Exactly one judgment is required per complete review item')
    totals = {method: dict(major_errors=0, minor_errors=0, items=0) for method in METHODS}
    for judgment in judgments:
        item = next(x for x in review['items'] if x['item_id'] == judgment['item_id'])
        if set(judgment.get('options', {})) != set(item['options']):
            raise ValueError('Every blinded option must be reviewed')
        for letter, issues in judgment['options'].items():
            if not isinstance(issues, list):
                raise ValueError('Issues must be a list')
            result = totals[answer_key[judgment['item_id']][letter]]
            result['items'] += 1
            for issue in issues:
                if issue.get('type') not in ISSUES or issue.get('severity') not in {'major', 'minor'}:
                    raise ValueError('Invalid issue type or severity')
                quote = issue.get('source_quote', '')
                if not quote or quote not in item['source'] or not issue.get('reason'):
                    raise ValueError('Each issue needs an exact source quote and explanation')
                result[issue['severity'] + '_errors'] += 1
    return dict(scope='Human-reviewed selected units only; no document-wide accuracy guarantee',
                reviewer_id=annotations['reviewer_id'], units=len(expected), methods=totals)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'qwen', 'export', 'checks', 'score'))
    parser.add_argument('--corpus', type=Path, default=Path('test_vault/accuracy-diverse-20261021'))
    parser.add_argument('--output', type=Path, default=Path('test_vault/accuracy-blind'))
    parser.add_argument('--per-document', type=int, default=2)
    parser.add_argument('--annotations', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        pack = prepare(args.corpus.resolve(), args.output.resolve(), args.per_document)
        print(json.dumps(dict(items=len(pack['items']), documents=sorted({x['document'] for x in pack['items']})), ensure_ascii=False))
    else:
        pack = read(args.output / 'private-pack.json')
        if args.action == 'qwen':
            pack = run_qwen(pack, args.output)
            print(json.dumps(dict(complete_items=sum(set(x['candidates']) == set(METHODS) for x in pack['items']), total_items=len(pack['items']))))
        elif args.action == 'export':
            review = export_review(pack, args.output)
            print(json.dumps(dict(complete_items=len(review['items']), total_items=len(pack['items']))))
        elif args.action == 'checks':
            result = structural_report(pack)
            save(args.output / 'structural-checks.json', result)
            print(json.dumps({name: dict(available=data['available'], flagged=len(data['flagged']),
                                         unavailable=len(data['unavailable']))
                              for name, data in result['methods'].items()}, ensure_ascii=False))
        else:
            if args.annotations is None:
                parser.error('--annotations is required for scoring')
            result = score(pack, read(args.output / 'review-blind.json'), read(args.annotations))
            save(args.output / 'human-score.json', result)
            print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
