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


def test_arxiv_only_references_continue_across_page_boundary():
    heading=paragraph('References','title')
    first=paragraph('[1] Anwar, Usman et al. "Foundational Challenges in Safety." ArXiv abs/2404.09932 (2024): n. pag.')
    clipped=paragraph('abs/2309.13788 (2023): n. pag.')
    second=paragraph('[3] Chung, Hyung Won et al. "Scaling Instruction-Finetuned Language Models." ArXiv abs/2210.11416 (2022): n. pag.')
    chosen=[p for _,p,_ in select(document([heading,first],[clipped,second]))]
    assert chosen==[heading,first,clipped,second]


def test_clipped_fused_arxiv_column_preserved_after_pdf_placeholder_extraction():
    heading=paragraph('References','title')
    first=paragraph('[1] Doe, Jane et al. "Initial study." ArXiv abs/2309.13788 (2023): n. pag.')
    fused=paragraph('abs/2309.13788 (2023): n. pag.{v1}Anwar, Usman et al. '
        '"Foundational Challenges in Safety." ArXiv abs/2404.09932 (2024): n. pag.'
        '{v2}Chung, Hyung Won et al. "Scaling Models." ArXiv abs/2210.11416 (2022): n. pag.')
    body=paragraph('We compare models in 2024 and cite ArXiv abs/2404.09932.')
    assert entry(fused.unicode) and not entry(body.unicode)
    assert [p for _,p,_ in select(document([heading,first],[fused,body]))]==[heading,first,fused,body]


def test_bracketed_reference_column_and_single_final_entry_continue_across_pages():
    heading=paragraph('References','title')
    first=paragraph('[1] Smith, J.: Initial results. Journal of Materials 12, 1452 (2020) https://doi.org/10.1234/a')
    fused=paragraph('under cycling fields. Applied Physics Letters 91(2), 022907 (2007). '
        '[12] Lebeugle, D., Colson, D.: Electric polarization. Nature 432, 737 (2004). '
        '[13] Stachiotti, M.G., Sepliarsky, M.: Toroidal ferroelectricity. '
        'Phys. Rev. Lett. 106, 137601 (2011).')
    clipped=paragraph('dynamics simulation. J. Phys.: Condens Matter 16, 3495 (2004)','abandon')
    final=paragraph('[14] Todorov, I.T., Smith, W.: New simulations. '
        'J. Mater. Chem. 16, 1911 (2006)')
    page_number=paragraph('11','abandon')
    appendix=paragraph('Appendix A','title')
    body=paragraph('We compare results from 2004 and 2011.')
    assert entry(fused.unicode) and entry(final.unicode)
    assert not entry('We cite [12] and [13] from 2004 and 2011 in the introduction.')
    chosen=[p for _,p,_ in select(document([heading,first],[fused],[clipped,final,page_number,appendix,body]))]
    assert chosen==[heading,first,fused,clipped,final]


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


def test_split_first_entry_and_fused_numbered_column_stop_before_author_bio():
    heading=paragraph('REFERENCES .','title')
    fragments=[paragraph('1'),paragraph('Laposky, A'),paragraph('.','title')]
    fused=paragraph('D., et al., Sleep and circadian rhythms. FEBS letters, 2008. '
        '582(1): p. 142-151. 2. Wulff, K., et al., Sleep disruption. '
        'Nature Reviews Neuroscience, 2010. 11(8): p. 589-599. '
        '3. Berry, R.B., et al., The scoring manual. AASM, 2012. 176(2): p. 7.')
    continuation=paragraph('18. Dai, Y., et al., Sleep stage classification. '
        'IEEE Journal, 2023. 27(9): p. 4204-4215.')
    bio=paragraph('MUHAMMAD SUDIPTO SIAM DIP received the B.Sc. degree in Electrical Engineering.')
    bio_tail=paragraph('His current research interests include signal processing.')
    doc=document([heading,*fragments,fused],[continuation,bio,bio_tail])
    assert entry(fused.unicode)
    assert [p for _,p,_ in select(doc)]==[heading,*fragments,fused,continuation]


def test_numbered_methods_and_result_prose_are_not_bibliography():
    methods=paragraph('1. Smith, J. collected data in 2020. 2. Jones, A. analyzed 12 records in 2021. '
        'The study used two steps to reduce bias.')
    assert not entry(methods.unicode)
    assert select(document([methods]))==[]


def test_repeated_running_header_is_kept_original_without_exempting_body():
    header='A Long Paper Title: A Framework for Automatic Analysis of Complex Signals'
    first=paragraph(header,'abandon');second=paragraph(header,'abandon')
    body=paragraph('We evaluate the framework on two datasets.')
    chosen=select(document([first,body],[second]))
    assert [(p,reason) for _,p,reason in chosen]==[(first,'repeated_running_matter'),(second,'repeated_running_matter')]


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
