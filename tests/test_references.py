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


def test_scan_noise_between_bibliography_heading_and_entry_is_preserved():
    heading=paragraph('REFERENCES','title')
    noise=paragraph('ey Ew Bea petty ff peed im pe bei na BI Ra a','title')
    citation=paragraph(APA)
    appendix=paragraph('Appendix A','title')
    body=paragraph('A real paragraph about methods.')
    chosen=[p for _,p,_ in select(document([heading,noise,citation,appendix,body]))]
    assert chosen==[heading,noise,citation]


def test_bibliography_heading_survives_split_first_entry():
    heading=paragraph('REFERENCES','title')
    noise=paragraph('ey Ew Bea petty ff peed im pe bei na BI Ra a','title')
    author=paragraph('Argyris, C., & Schon, D. A. (1974).')
    publisher=paragraph('Theories in practice. San Francisco, CA: Jossey-Bass.')
    citation=paragraph(APA)
    chosen=[p for _,p,_ in select(document([heading,noise,author,publisher,citation]))]
    assert chosen==[heading,noise,author,publisher,citation]


def test_numbered_full_name_bibliography_continues_across_pages():
    heading=paragraph('References','title')
    first=paragraph('[1] Bernhard Kerbl, Georgios Kopanas, and George Drettakis. '
        '3D Gaussian splatting for real-time rendering. ACM Transactions on Graphics, 42(4), 2023.')
    clipped=paragraph('10] Chi Jin, Rong Ge, and Michael Jordan. How to escape saddle points '
        'efficiently. In International conference on machine learning, pages 1724–1732. PMLR, 2017.')
    continuation=paragraph('Vision and Pattern Recognition, pages 7330–7339, 2026.')
    next_entry=paragraph('[21] Scott Kirkpatrick, C Daniel Gelatt Jr, and Mario Vecchi. '
        'Optimization by simulated annealing. Science, 220(4598):671–680, 1983.')
    appendix=paragraph('Appendix','title');body=paragraph('We prove that the method converges.')
    chosen=[p for _,p,_ in select(document([heading,first,clipped],[continuation,next_entry],[appendix,body]))]
    assert chosen==[heading,first,clipped,continuation,next_entry]


def test_fused_appendix_contents_are_preserved_without_hiding_appendix_body():
    heading=paragraph('Appendix','title')
    top=paragraph('A The proof of orthogonality','title')
    a=paragraph('A.1 Preliminaries . . . . . . . . . . . . . . . . . 16')
    b=paragraph('B.1 Gradient decomposition . . . . . . . . . . . . . . 20')
    page_number=paragraph('21','fallback_line')
    section=paragraph('A. The proof of orthogonality','title')
    body=paragraph('We prove that the two vectors are orthogonal.')
    chosen=[p for _,p,_ in select(document([heading,top,a,b,page_number,section,body]))]
    assert chosen==[top,a,b,page_number]


def test_dense_index_keeps_locator_pages_original_when_first_header_is_missing():
    first=[paragraph(f'Term {i}, {i+20}') for i in range(45)]
    middle=[paragraph(f'More term {i}, {i+50}') for i in range(45)]
    second=[paragraph('Index','title')]+[paragraph(f'Other term {i}, {i+80}') for i in range(45)]
    prose=[paragraph('In this study, 24 participants completed the task.')]
    chosen=[p for _,p,_ in select(document(prose,first,middle,second))]
    assert chosen==first+middle+second


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
