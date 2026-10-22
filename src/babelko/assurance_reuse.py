"""Reuse checked evidence, never a guessed similarity or an editor verdict."""
import collections,copy,hashlib,json,re
from .assurance import REVISION,view,tasks,checked,accepted,fingerprint,validate
from .storage import read

POLICY='exact-input-and-local-repair-1'
FIELDS=('key','label','source','final','context','neighbors','formula_hints','assurance')


def hints(record):
    return [view(record.get('context','')),[view(s) for s in record.get('neighbors',[])],record.get('formula_hints',{})]


def identity(record):
    # These are precisely the canonical sentences seen by the auditor, plus
    # every meaning hint. Keep numbers, punctuation, case, order and formulas.
    data=[REVISION,record.get('label'),tasks(record['source'],record.get('final') or ''),hints(record)]
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def snapshot(record):return copy.deepcopy({k:record[k] for k in FIELDS if k in record})


def preserve(record):
    """Save the last complete checked candidate before an automatic repair."""
    if checked(record):record['audit_base']=snapshot(record)


class AuditMemory:
    def __init__(self,folder):self.folder=folder;self.index=None

    def _add(self,record):
        if not accepted(record):return
        key=identity(record)
        # One exact-input result suffices. Conflicting model outcomes are never
        # merged; only complete, faithful evidence enters this index.
        self.index.setdefault(key,snapshot(record))

    def remember(self,record):
        if self.index is not None:self._add(record)

    def restore(self,record):
        if accepted(record):return False
        if self.index is None:
            self.index={}
            for path in self.folder.glob('*.json'):
                row=read(path)
                if path.stem==row.get('key'):self._add(row)
        previous=self.index.get(identity(record))
        if previous is None:return False
        from .hybrid import errors
        if errors(record['source'],record.get('final',''),record.get('label','text')):return False
        proof=checked(previous)
        if not proof or any(c['verdict']!='faithful' for c in proof):return False
        values=[{k:c[k] for k in ('id','verdict','evidence','reason')} for c in proof]
        proof=validate(tasks(record['source'],record['final']),values,record['source'],record['final'])
        record['assurance']={**copy.deepcopy(previous['assurance']),
            'fingerprint':fingerprint(record),'checks':proof,'reused_checks':len(proof),'checked_now':0,
            'reuse':dict(policy=POLICY,from_key=previous.get('key'),from_fingerprint=fingerprint(previous),identity=identity(record))}
        return accepted(record)


# A local factual-word repair may be independent. A logic, reference, quantity,
# equation or list-boundary change retains the complete original audit path.
SCOPE=re.compile(r'\d|\{v\d+\}|[=<>∑∫≤≥]|\b(?:not|no|never|none|all|only|unless|if|except|must|may|can|more|less|than|because|therefore|it|its|they|their|this|that|these|those)\b|'
    r'않|없|못|아니|오직|모든|전부|일부|제외|조건|경우|반드시|가능|보다|때문|따라서|그러나|이것|그것|이들|그들|이러한|그러한|해당|앞서|후술|각각|전자|후자',re.I)


def delta_checks(previous,current):
    """Retain independent faithful checks after a small TARGET-only repair.

    The model still sees the whole current source/target. All defective checks,
    changed sentences, adjacent sentences and transitive evidence dependents
    are checked again. Uncertain boundaries/scope use the unchanged full path.
    """
    if not previous or previous.get('label')!=current.get('label') or view(previous['source'])!=view(current['source']) or hints(previous)!=hints(current):return {}
    proof=checked(previous)
    if not proof or re.search(r'\{v\d+\}|[=<>∑∫≤≥]',current['source']):return {}
    source=view(current['source'])
    if not re.match(r'^[A-Z]',source) or not re.search(r'[.!?][\"\x27)]?$',source):return {}
    # Unchanged logic/coreference elsewhere can still depend on a repaired
    # noun. Keep full review for those paragraphs and for indexed fragments
    # that are not complete sentences (including long-clause splits/lists).
    if SCOPE.search(source):return {}
    old={c['id']:c for c in proof};catalog={c['id']:c for c in tasks(current['source'],current['final'])}
    if set(old)!=set(catalog):return {}
    if any(not re.search(r'[.!?][\"\x27)]?$',c['text']) for c in catalog.values()):return {}
    targets=[k for k in catalog if k.startswith('t')]
    changed=[k for k in targets if old[k]['text']!=catalog[k]['text']]
    if not changed or len(changed)>2 or len(changed)>len(targets)*.25:return {}
    if any(SCOPE.search(old[k]['text']) or SCOPE.search(catalog[k]['text']) for k in changed):return {}
    # Sentence moves/duplicate-text ambiguity are not a small local repair.
    if any(catalog[k]['text'] in [v['text'] for key,v in old.items() if key!=k and key.startswith('t')] for k in changed):return {}
    dirty=set(changed)|{k for k,c in old.items() if c['verdict']!='faithful'}
    for key in changed:
        i=targets.index(key);dirty.update(targets[max(0,i-1):i+2])
    def close():
        while True:
            added={k for k,c in old.items() if any(e in dirty for e in c['evidence'])}-dirty
            if not added:return
            dirty.update(added)
    close()
    sources=[k for k in catalog if k.startswith('s')]
    for key in list(dirty):
        if key in sources:
            i=sources.index(key);dirty.update(sources[max(0,i-1):i+2])
    close()
    result={}
    for key,c in old.items():
        if key in dirty or c['verdict']!='faithful' or c['text']!=catalog[key]['text']:continue
        if any(e not in catalog or old[e]['text']!=catalog[e]['text'] for e in c['evidence']):continue
        value={k:c[k] for k in ('id','verdict','evidence','reason')}
        result[key]=validate([catalog[key]],[value],current['source'],current['final'])[0]
    return result if len(result)>=4 else {}
