"""Source-bound native IL cache. JSON dataclasses only; never executable pickle."""
import dataclasses,functools,gzip,hashlib,json,math,time,types,typing,uuid
from contextlib import ExitStack,contextmanager
from pathlib import Path
from unittest.mock import patch
from .storage import digest,read,save

REVISION='native-pretranslation-il-1'


@functools.cache
def fields(cls):return {f.name:f.type for f in dataclasses.fields(cls)}


def decode(kind,value,name=''):
    """Strictly reconstruct the pinned, local dataclass schema; no class names in data."""
    args=typing.get_args(kind);origin=typing.get_origin(kind)
    if origin in (types.UnionType,typing.Union):
        if value is None and type(None) in args:return None
        options=[t for t in args if t is not type(None)]
        if len(options)!=1:raise ValueError('Unsupported cached IL union')
        return decode(options[0],value,name)
    if origin is list:
        if not isinstance(value,list):raise ValueError('Cached IL list expected')
        return [decode(args[0],v) for v in value]
    if dataclasses.is_dataclass(kind):
        schema=fields(kind)
        if not isinstance(value,dict) or set(value)!=set(schema):raise ValueError('Cached IL fields differ')
        return kind(**{k:decode(schema[k],v,k) for k,v in value.items()})
    if kind is object:return value  # JSON-only matrices and primitive paths.
    if kind is float and type(value) in (int,float) and math.isfinite(value):return value
    # The pinned native frontend emits 0/1 font flags and string debug labels
    # despite its legacy bool annotations. Preserve those values exactly.
    if kind is bool and type(value) is int and value in (0,1):return value
    if kind is bool and name=='debug_info' and type(value) is str:return value
    if kind in (str,int,bool) and type(value) is kind:return value
    raise ValueError('Cached IL primitive differs')


class GraphEncoder:
    """Preserve shared character/style objects, including references across pages."""
    def __init__(self):self.ids={};self.count=0
    def page(self,page):
        nodes=[];start=self.count
        def encode(value):
            if dataclasses.is_dataclass(value):
                if id(value) in self.ids:return {'ref':self.ids[id(value)]}
                index=self.count;self.count+=1;self.ids[id(value)]=index;slot=len(nodes);nodes.append(None)
                node={k:encode(getattr(value,k)) for k in fields(type(value))}
                nodes[slot]=[type(value).__name__,node];return {'ref':index}
            if isinstance(value,(list,tuple)):return [encode(v) for v in value]
            if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
            if hasattr(value,'materialize'):return value.materialize()
            return value
        root=encode(page);return dict(start=start,root=root,nodes=nodes)


class GraphDecoder:
    def __init__(self):self.nodes=[];self.objects={};self.visiting=set()
    def page(self,payload):
        from babeldoc.format.pdf.document_il import il_version_1 as il
        if payload['start']!=len(self.nodes):raise ValueError('Cached IL node sequence differs')
        self.nodes.extend(payload['nodes']);return self.value(il.Page,payload['root'])
    def value(self,kind,value,name=''):
        origin=typing.get_origin(kind);args=typing.get_args(kind)
        if origin in (types.UnionType,typing.Union):
            if value is None and type(None) in args:return None
            options=[t for t in args if t is not type(None)]
            if len(options)!=1:raise ValueError('Unsupported IL union')
            return self.value(options[0],value,name)
        if origin is list:
            if not isinstance(value,list):raise ValueError('Cached IL list differs')
            return [self.value(args[0],v) for v in value]
        if not dataclasses.is_dataclass(kind):return decode(kind,value,name)
        if not isinstance(value,dict) or set(value)!={'ref'} or type(value['ref']) is not int:raise ValueError('Cached IL reference differs')
        index=value['ref']
        if not 0<=index<len(self.nodes):raise ValueError('Cached IL reference outside graph')
        if index in self.objects:
            if type(self.objects[index]) is not kind:raise ValueError('Cached IL reference type differs')
            return self.objects[index]
        node_type,data=self.nodes[index]
        if node_type!=kind.__name__ or set(data)!=set(fields(kind)):raise ValueError('Cached IL node schema differs')
        if index in self.visiting:raise ValueError('Cyclic cached IL')
        if index not in self.objects:
            self.visiting.add(index)
            self.objects[index]=kind(**{k:self.value(t,data[k],k) for k,t in fields(kind).items()})
            self.visiting.remove(index)
            self.nodes[index]=(node_type,None)
        if type(self.objects[index]) is not kind:raise ValueError('Cached IL reference type differs')
        return self.objects[index]


def prepared_hash(doc):
    """Bind all native xrefs/stream bytes; trailer IDs may change on each save."""
    sha=hashlib.sha256()
    def part(data):sha.update(len(data).to_bytes(8,'big'));sha.update(data)
    part(str((len(doc),doc.xref_length(),[doc.xref_get_key(-1,k) for k in ('Root','Info','Encrypt')])).encode())
    for xref in range(1,doc.xref_length()):
        part(doc.xref_object(xref,compressed=True).encode())
        if doc.xref_is_stream(xref):part(doc.xref_stream_raw(xref))
    return sha.hexdigest()


def configuration(config):
    omitted={'input_file','output_dir','working_dir','progress_monitor','report_interval','metadata_extra_data'}
    result={}
    for name,value in vars(config).items():
        if name.startswith('_') or name in omitted:continue
        try:json.dumps(value)
        except (TypeError,ValueError):continue
        result[name]=value
    return result


class LayoutCache:
    def __init__(self,folder):self.folder=Path(folder);self.base=self.folder/'layout-cache';self.manifest=self.base/'manifest.json'
    def load(self,identity):
        from babeldoc.format.pdf.document_il import il_version_1 as il
        import orjson
        if not self.manifest.is_file():return None
        try:
            row=read(self.manifest)
            if row.get('identity')!=identity or row.get('encoding')!='dataclass-graph-1':return None
            generation=row['generation']
            if len(generation)!=32 or any(c not in '0123456789abcdef' for c in generation):return None
            pages=[];decoder=GraphDecoder()
            for n,item in enumerate(row['pages']):
                path=self.base/generation/f'page-{n}.json.gz'
                if digest(path)!=item['sha256']:return None
                with gzip.open(path,'rb') as f:value=orjson.loads(f.read())
                pages.append(decoder.page(value))
            return il.Document(page=pages,total_pages=row['total_pages'])
        except (OSError,ValueError,KeyError,TypeError,EOFError):return None
    def store(self,identity,docs):
        from babeldoc.format.pdf.document_il.xml_converter import _orjson_default
        import orjson
        generation=uuid.uuid4().hex;target=self.base/generation;target.mkdir(parents=True)
        pages=[];encoder=GraphEncoder();decoder=GraphDecoder()
        for n,page in enumerate(docs.page):
            payload=orjson.dumps(encoder.page(page),default=_orjson_default)
            restored=decoder.page(orjson.loads(payload))
            if orjson.dumps(restored)!=orjson.dumps(page,default=_orjson_default):raise ValueError('Cached IL roundtrip differs')
            path=target/f'page-{n}.json.gz'
            with gzip.open(path,'wb',compresslevel=1) as f:f.write(payload)
            pages.append(dict(sha256=digest(path)))
        save(self.manifest,dict(revision=REVISION,encoding='dataclass-graph-1',identity=identity,generation=generation,pages=pages,total_pages=docs.total_pages))


@contextmanager
def native_layout_cache(folder,input_pdf,config,progress,performance):
    """Reuse only completed pretranslation analysis with an exact source/config binding."""
    if config.debug or config.split_strategy or config.auto_enable_ocr_workaround:
        save(Path(folder)/'layout-cache-report.json',dict(status='disabled',reason='unsupported_configuration'))
        yield;return
    import babeldoc.format.pdf.high_level as high
    import babeldoc.format.pdf.new_parser.native_parse as native
    cache=LayoutCache(folder);warm=[False];identity=[None];report={}
    source=digest(input_pdf)
    policy=digest(Path(__file__));grouping=digest(Path(__file__).with_name('source_flow.py'))
    upstream=read(Path(__file__).resolve().parents[2]/'upstream.lock.json')
    original_parse=native.parse_prepared_pdf_with_new_parser_to_legacy_ir
    def parse(path,*,config,doc_pdf):
        value=[REVISION,source,prepared_hash(doc_pdf),configuration(config),upstream,policy,grouping]
        identity[0]=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with performance.measure('layout.cache_read'):docs=cache.load(identity[0])
        warm[0]=docs is not None;report.update(status='hit' if warm[0] else 'miss',identity=identity[0])
        if warm[0]:
            progress('저장된 PDF 문서 분석 재사용')
            performance.add('layout.cache_hits');return docs
        with performance.measure('layout.parse'):return original_parse(path,config=config,doc_pdf=doc_pdf)
    def wrap(cls):
        original=cls.process
        def process(self,docs,*args,**kwargs):
            if warm[0]:return docs
            with performance.measure('layout.'+cls.__name__):result=original(self,docs,*args,**kwargs)
            if cls is high.StylesAndFormulas:
                try:
                    with performance.measure('layout.cache_write'):cache.store(identity[0],docs)
                except (OSError,TypeError,ValueError) as exc:
                    report.update(status='uncacheable',reason=type(exc).__name__)
                report['pages']=len(docs.page)
            return result
        return process
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(native,'parse_prepared_pdf_with_new_parser_to_legacy_ir',parse))
            for cls in (high.DetectScannedFile,high.LayoutParser,high.TableParser,high.ParagraphFinder,high.StylesAndFormulas):
                stack.enter_context(patch.object(cls,'process',wrap(cls)))
            yield
    finally:save(Path(folder)/'layout-cache-report.json',report)
