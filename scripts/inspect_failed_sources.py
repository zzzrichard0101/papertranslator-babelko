"""Replay cached native input preparation for failed sources; no model or targets edited."""
import argparse,json,re,copy
from types import SimpleNamespace
from babelko.storage import read,save


def main(job,output):
    from babelko.hybrid import HybridTranslator,prepare_layout,errors
    from babelko.layout_cache import LayoutCache
    from babelko.scan_evidence import cached,plan,normalize_input
    from babelko.recovery import ScanRecovery
    from babelko.text_structure import normalize_input as normalize_text,repair_caption_input
    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
    from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
    output.mkdir(parents=True,exist_ok=True)
    records=[read(job/'hybrid'/(v['key']+'.json')) for v in read(job/'pending-review.json')['pending']]
    by_source={r['source']:r for r in records};cache=LayoutCache(job);docs=cache.load(read(cache.manifest)['identity'])
    if docs is None:raise RuntimeError('검증된 문서 분석 캐시 없음')
    repairs={};prepare_layout(docs,output,repairs,job/'Layout-input.pdf')
    plans=plan(docs,job,cached(job),output);recovery=ScanRecovery(job,by_source)
    native=object.__new__(ILTranslator);native.translate_engine=object.__new__(HybridTranslator)
    native.translation_config=SimpleNamespace(disable_rich_text_translate=False)
    native.font_mapper=FontMapper(SimpleNamespace(primary_font_family=None,lang_out='ko'))
    native._formula_placeholder_pattern=re.compile(r'\{v\d+\}');native._style_left_placeholder_pattern=re.compile(r"<style id='\d+'>");native._style_right_placeholder_pattern=re.compile(r'</style>')
    results=[]
    for page in docs.page:
        fonts={f.font_id:f for f in page.pdf_font}
        for paragraph in page.pdf_paragraph:
            value=native.get_translate_input(paragraph,fonts,False)
            value=repair_caption_input(normalize_text(value),repairs.get(paragraph.debug_id,{}))
            if value is None or value.unicode not in by_source:continue
            original=value.unicode;item=plans.get((page.page_number,paragraph.debug_id))
            formula_count=sum(p.__class__.__name__=='FormulaPlaceholder' for p in value.placeholders)
            expanded=original
            for placeholder in value.placeholders:
                if p:=getattr(placeholder,'formula',None):
                    expanded=expanded.replace(placeholder.placeholder,''.join(c.char_unicode or '' for c in p.pdf_character))
            actions=[]
            if item:
                value,actions=recovery(value,paragraph,item)
                _,_,more=normalize_input(value,item);actions+=more
            row=by_source[original];candidate=row.get('final') or row.get('draft') or ''
            result=dict(key=row['key'],page=page.page_number+1,debug_id=paragraph.debug_id,before=original,after=value.unicode,
                actions=actions,candidate_structural_errors=errors(value.unicode,candidate,row['label']))
            if item:result['source_rect']=item['source_rect']
            if formula_count>=5 and not actions and item:
                observation=recovery.observe(item)
                result['diagnostic']=dict(expanded=expanded,ocr300=' '.join(r['text'] for r in observation['rows']),
                    ocr400=' '.join(r['text'] for r in observation['second_rows']),formula_count=formula_count)
            results.append(result);save(output/'results.json',results)
            print(json.dumps(dict(key=row['key'][:9],page=result['page'],changed=original!=value.unicode,actions=[a.get('action','ocr_confusion') for a in actions],errors=result['candidate_structural_errors']),ensure_ascii=False),flush=True)
    save(output/'summary.json',dict(failed=len(records),mapped=len(results),changed=sum(r['before']!=r['after'] for r in results),
        unmapped=[r['key'] for r in records if r['key'] not in {v['key'] for v in results}]))


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();main(args.job,args.output)
