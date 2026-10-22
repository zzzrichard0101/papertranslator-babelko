from types import SimpleNamespace as Obj
from unittest.mock import patch
from babelko.references import entry,select,preserve
from babelko.storage import read


APA='Daley, K. J. (2007). Qualitative methods for family studies. Thousand Oaks, CA: Sage.'
IEEE='[1] A. Smith, A study of translation. Journal of Research, 12(2), 30-42, 2020.'


def paragraph(value,label='plain text'):
    return Obj(unicode=value,layout_label=label,debug_id=value[:10])


def document(*pages):
    return Obj(page=[Obj(page_number=i,pdf_paragraph=list(p)) for i,p in enumerate(pages)])


def test_entries_require_bibliographic_structure_not_an_inline_citation():
    assert entry(APA)
    assert entry(IEEE)
    assert not entry('Smith (2020) found that the method works.')
    assert not entry('Smith, J. (2020). We found that the method works.')
    assert not entry('[1] found that the method works in 2020.')
    assert not entry('The References section includes Smith, J. (2020). A study. Oxford University Press.')


def test_confirmed_section_preserves_fragments_and_stops_at_appendix():
    heading=paragraph('REFERENCES','title');a=paragraph(APA);tail=paragraph('https://doi.org/10.1234/example')
    appendix=paragraph('Appendix A','title');body=paragraph('The appendix explains the result (2020).')
    doc=document([heading,a,tail,appendix,body])
    chosen=[p for _,p,_ in select(doc)]
    assert chosen==[heading,a,tail]
    assert a.unicode==APA


def test_does_not_exempt_toc_or_bleed_into_next_page_without_entry_evidence():
    toc=paragraph('References');other=paragraph('Chapter 2','title')
    heading=paragraph('References','title');a=paragraph(APA)
    body=paragraph('The next chapter discusses the references and clinical evidence.')
    doc=document([toc,other],[heading,a],[body])
    assert [p for _,p,_ in select(doc)]==[heading,a]


def test_standalone_reference_block_is_detected_when_ocr_heading_is_missing():
    a=paragraph(APA+' Deaver, S. P. (2002). What constitutes art therapy research? Journal of Research, 19(1), 23-27.')
    doc=document([paragraph('REFERENCFS'),a,paragraph('Discussion','title'),paragraph('We discuss Smith (2020).')])
    assert [p for _,p,_ in select(doc)]==[a]


def test_damaged_leading_entry_and_interleaved_ocr_still_identify_a_bibliography():
    value=("<style id='1'>of </style>R. (2001). A handbook of inquiry. "
        'Author, W. (1989). Learning from experience. action research (pp. 250-260). '
        'Thousand Oaks, CA: Sage. Philadelphia, PA: Falmer Press. '
        'Writer, H. F. (1994). Transforming qualitative data. Thousand Oaks, CA: Sage.')
    a=paragraph(value);body=paragraph('We used Author (1989) and Writer (1994) to explain these results.')
    assert entry(value)
    assert [p for _,p,_ in select(document([a,body]))]==[a]
    assert not entry('We discuss Author, W. (1989). '+('A long explanation of our research results. '*40)+
        'Writer, H. F. (1994). Oxford University Press. '+('More body prose. '*40))


def test_native_filter_keeps_compositions_and_never_submits_references(tmp_path):
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly as Native
    a=paragraph(APA);body=paragraph('This is the main text.');doc=document([a,body])
    compositions=Obj(original=True);a.pdf_paragraph_composition=compositions
    submitted=[]
    def translate(self,docs):
        assert not self._should_translate_paragraph(a)
        self.process_page(docs.page[0],None,translated_ids=set())
    def process_page(self,page,executor,pbar,tracker,executor2,translated_ids):
        submitted.extend(p.unicode for p in page.pdf_paragraph if id(p) not in translated_ids)
    with patch.object(Native,'translate',translate),patch.object(Native,'process_page',process_page):
        with preserve(tmp_path):
            instance=object.__new__(Native);instance.translate(doc)
    assert submitted==[body.unicode] and a.pdf_paragraph_composition is compositions
    report=read(tmp_path/'reference-preservation.json')
    assert report['policy']=='original' and len(report['paragraphs'])==1
