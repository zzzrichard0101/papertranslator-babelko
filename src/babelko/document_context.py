"""CPU-only, source-quoted abbreviation context, never an invented glossary."""
import collections,json,re
from .storage import save

REVISION='source-terminology-1'
ABBREVIATION=re.compile(r'\b([A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){1,9})\s*\(([A-Z][A-Z0-9-]{1,11})\)')
CONNECTORS={'a','an','and','of','the','for','in','to','on','with'}


def definitions(text):
    for match in ABBREVIATION.finditer(text):
        words=match[1].split();short=match[2]
        letters=re.sub('[^A-Z]','',short)
        if len(letters)<2:continue
        # A match can include preceding sentence words. Require an exact
        # initial-letter expansion, retaining only the shortest unique suffix.
        for n in range(2,len(words)+1):
            phrase=words[-n:]
            # OCR can leave a trailing/duplicated hyphen ("art- therapy",
            # "evidence--based"). Empty split components carry no initials.
            initials=''.join(w[0].upper() for word in phrase for w in word.split('-') if w and w.lower() not in CONNECTORS)
            if initials==letters:
                suffix=re.search(r'\b'+r'\s+'.join(map(re.escape,phrase))+r'$',match[1])
                quote=text[match.start(1)+suffix.start():match.end()]
                if len(quote)<=260:yield short,' '.join(phrase),quote
                break


class DocumentContext:
    def __init__(self,rows):
        found=collections.defaultdict(list)
        for page,text in rows:
            for short,long,quote in definitions(text):
                found[short].append(dict(expansion=long,source_page=page,quote=quote))
        # Conflicting expansions remain in the report, never propagated as hints.
        self.ambiguous=sorted(k for k,v in found.items() if len({x['expansion'].casefold() for x in v})>1)
        self.entries={k:v[0] for k,v in sorted(found.items()) if k not in self.ambiguous}

    def hints(self,source):
        selected={k:v for k,v in self.entries.items() if re.search(r'(?<![\w-])'+re.escape(k)+r'(?![\w-])',source)}
        # Bound prompt cost. Relevance is exact source occurrence, never an
        # unrelated whole-book glossary or an inferred Korean word alignment.
        ordered=sorted(selected.items(),key=lambda kv:source.find(kv[0]))[:5];selected={}
        for key,value in ordered:
            if len(json.dumps({**selected,key:value},ensure_ascii=False))<=1100:selected[key]=value
        return dict(revision=REVISION,definitions=selected) if selected else None

    def report(self):return dict(revision=REVISION,entries=self.entries,ambiguous=self.ambiguous,
        scope='Exact source-quoted abbreviation definitions; no generated Korean mappings or semantic approval.')

    @classmethod
    def from_document(cls,docs,folder):
        from .references import select
        references={id(p) for _,p,_ in select(docs)}
        instance=cls((page.page_number+1,p.unicode or '') for page in docs.page for p in page.pdf_paragraph if id(p) not in references)
        save(folder/'document-context.json',instance.report());return instance
