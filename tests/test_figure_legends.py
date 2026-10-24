import json
from types import SimpleNamespace as NS

import pymupdf as fitz

from babelko.figure_legends import REVISION,explanatory_label,export,preserve,select,image_manifest_valid,rebuild_images
from babelko.storage import save,digest


def box(x,y,x2,y2):
    return NS(x=x,y=y,x2=x2,y2=y2)


def paragraph(name,text,rect,role='fallback_line'):
    return NS(debug_id=name,unicode=text,box=box(*rect),layout_label=role)


def test_confident_figure_protects_internal_text_but_not_caption_or_prose():
    labels=[paragraph('axis','Improved patient care',(150,150,270,165)),
        paragraph('tick','20',(100,125,115,140)),
        paragraph('caption','Figure 1. The EBP process.',(100,80,300,95),'figure_caption'),
        paragraph('body','This is body prose.',(100,300,260,315)),
        paragraph('edge','Partly outside figure',(290,150,330,165))]
    page=NS(page_number=0,pdf_paragraph=labels,page_layout=[NS(class_name='figure',conf=.97,box=box(95,110,310,290))])
    ids,figures=select(NS(page=[page]))
    assert ids=={id(labels[0]),id(labels[1])}
    assert [x['explanatory'] for x in figures[0]['labels']]==[True,False]
    page.page_layout[0].conf=.6
    assert select(NS(page=[page]))[0]==set()


def test_uppercase_multiword_label_is_meaningful_but_panel_and_acronym_are_not():
    assert explanatory_label('CONTROL GROUP')
    assert explanatory_label('ACCURACY')
    assert not explanatory_label('GPU')
    assert not explanatory_label('(a)')
    assert not explanatory_label('12.5')


def test_preserve_filters_only_figure_interior(tmp_path,monkeypatch):
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly as Native
    inside=paragraph('inside','Treatment group',(150,150,240,170))
    caption=paragraph('caption','Figure 1. Comparison',(100,80,280,100),'figure_caption')
    docs=NS(page=[NS(page_number=0,pdf_paragraph=[inside,caption],
        page_layout=[NS(class_name='figure',conf=.96,box=box(100,120,300,250))])])
    seen=[]
    monkeypatch.setattr(Native,'translate',lambda self,d: [seen.append(p.debug_id) for p in d.page[0].pdf_paragraph
        if Native._should_translate_paragraph(self,p)])
    monkeypatch.setattr(Native,'_should_translate_paragraph',lambda self,p,*a,**k:True)
    with preserve(tmp_path):Native.translate(NS(),docs)
    assert seen==['caption']
    report=json.loads((tmp_path/'figure-preservation.json').read_text(encoding='utf-8'))
    assert report['protected_paragraphs']==1


def test_legend_export_uses_local_model_only_for_meaningful_labels(tmp_path):
    original=tmp_path/'source.pdf';out=tmp_path/'result';out.mkdir()
    with fitz.open() as pdf:
        page=pdf.new_page(width=400,height=400)
        page.insert_text((120,150),'Control group')
        page.insert_text((120,175),'25')
        pdf.save(original)
    save(tmp_path/'figure-preservation.json',dict(revision=REVISION,figures=[dict(source_page=1,figure_index=1,
        source_box=[100,200,300,300],labels=[dict(source='Control group',explanatory=True),
            dict(source='25',explanatory=False)])],protected_paragraphs=2))
    class Translator:
        calls=[]
        def _request(self,messages,schema):
            self.calls.append(messages)
            return json.dumps([dict(id=0,output='대조군')],ensure_ascii=False)
    translator=Translator();report=export(tmp_path,out,original,translator)
    assert report['status']=='passed' and report['translated_labels']==1
    assert len(translator.calls)==1 and 'Control group' in translator.calls[0][1]['content']
    assert '25' not in translator.calls[0][1]['content']
    assert (out/'FigureImages/page-1-figure-1.png').is_file()
    assert '대조군' in (out/'FigureLegends.html').read_text(encoding='utf-8')
    assert report['translations']==[dict(source='Control group',target='대조군')]
    name='FigureImages/page-1-figure-1.png'
    assert report['image_hashes']=={name:digest(out/name)}
    assert image_manifest_valid(out,report,{name:report['image_hashes'][name]})
    (out/name).write_bytes(b'damaged image')
    assert not image_manifest_valid(out,report,{name:report['image_hashes'][name]})
    restored=rebuild_images(tmp_path,out,original,report)
    assert restored['image_hashes']==report['image_hashes']
    assert image_manifest_valid(out,restored,{name:restored['image_hashes'][name]})
    (out/name).unlink()
    assert not image_manifest_valid(out,restored,{name:restored['image_hashes'][name]})


def test_invalid_legend_response_reports_incomplete_without_inventing_text(tmp_path):
    original=tmp_path/'source.pdf';out=tmp_path/'result';out.mkdir()
    with fitz.open() as pdf:pdf.new_page(width=400,height=400);pdf.save(original)
    save(tmp_path/'figure-preservation.json',dict(figures=[dict(source_page=1,figure_index=1,
        source_box=[100,100,300,300],labels=[dict(source='Treatment group',explanatory=True)])],
        protected_paragraphs=1))
    class Translator:
        def _request(self,messages,schema):return json.dumps([dict(id=0,output='Treatment group')])
    report=export(tmp_path,out,original,Translator())
    assert report['status']=='partial' and report['translated_labels']==0
    assert report['unresolved_labels'][0]['source']=='Treatment group'
