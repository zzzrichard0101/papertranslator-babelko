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
    assert [p for _,p,_ in select(document([heading,first],[fused,body]))]==[heading,first,fused]


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


def test_fused_unnumbered_publication_columns_are_preserved():
    arxiv=(
        '{v1}Alice Morgan and Bob Lee. "First study." In: arXiv preprint arXiv:2401.01001 (2024).'
        '{v2}Carol Park and Dana Xu. "Second study." In: arXiv preprint arXiv:2302.01002 (2023).'
        '{v3}Evan Kim and Frank Li. "Third study." In: arXiv preprint arXiv:2203.01003 (2022).')
    astronomy=(
        'Carter, A., & Jones, B. 2016, SoPh, 291, 2629 '
        'Lee, C., Wang, D., & Park, E. 2023, ApJ, 298, 44 '
        'Smith, F., & Kim, G. 2014, JGR, 186, 35')
    materials=(
        'A. Jones, B. Lee, and C. Park, First result, Phys. Rev. B 110, 144420 (2024). '
        'D. Kim, E. Xu, and F. Wang, Second result, Phys. Rev. X 12, 031042 (2022). '
        'G. Bell, H. Chen, and I. Lee, Third result, Phys. Rev. B 106, 224429 (2022).')
    for value in (arxiv,astronomy,materials):
        assert entry(value)
        heading=paragraph('References','title');block=paragraph(value)
        appendix=paragraph('Appendix','title');body=paragraph('We compare these studies in detail.')
        assert [p for _,p,_ in select(document([heading,block,appendix,body]))]==[heading,block]
    assert not entry('We compare arXiv:2401.01001 (2024), arXiv:2302.01002 (2023), '
                     'and arXiv:2203.01003 (2022) as evidence for the new model.')
    assert not entry('The 2016, 2023, and 2014 observations were collected by Carter, A. '
                     'and Jones, B. for an independent analysis of the solar limb.')


def test_fused_numbered_full_name_publications_are_preserved():
    value=('[104] W Scott Terry. Learning and memory: Basic principles, processes, and procedures. '
           'Routledge, 2017. [105] Matteo Tiezzi, Michele Casoni, and Alessandro Betti. '
           'A recurrent model for long sequence learning. arXiv:2402.01001 (2024). '
           '[106] Alice Morgan and Bob Lee. A third study. arXiv:2301.01002 (2023).')
    assert entry(value)
    assert [p.unicode for _,p,_ in select(document([paragraph(value)]))]==[value]
    assert not entry('[104] W Scott Terry proposed a method in 2017. '
                     '[105] Matteo Tiezzi discussed the method in 2024. '
                     'We analyze these papers in the next section.')


def test_full_name_proceedings_entries_open_and_continue_references():
    first=paragraph('Josh Achiam, Steven Adler, Sandhini Agarwal, et al. 2023. '
                    'GPT-4 technical report. Preprint arXiv:2303.08774.')
    second=paragraph('Rami Al-Rfou, Dokook Choe, Noah Constant, Mandy Guo, and Llion Jones. '
                     '2019. Character-level language modeling. In Proc. Conference on '
                     'Artificial Intelligence, pages 3159–3166.')
    continuation=paragraph('Int. Conf. on Machine Learning, New York City, USA.')
    last=paragraph('Teven Le Scao, Thomas Wang, Daniel Hesslow, Stas Bekman, and Iz Beltagy. '
                   '2022. What language model to train? In Proc. Findings of Conf. on '
                   'Empirical Methods in Natural Language Processing, pages 765–782.')
    heading=paragraph('References','title')
    section=paragraph('A Reminder: Derivation of the dual form','title')
    body=paragraph('We derive the relation for the model in this section.')
    chosen=[p for _,p,_ in select(document(
        [heading,first,second,continuation],
        [last,section,body]))]
    assert chosen==[heading,first,second,continuation,last]
    assert not entry('We compare Josh Achiam and Steven Adler. 2023. '
                     'Their study informs our implementation of the model.')


def test_figures_and_publisher_notes_within_reference_region_stay_translatable():
    heading=paragraph('References','title')
    first=paragraph(APA)
    figure=paragraph('Figure A1. Original article reproduced with permission.')
    second=paragraph('Lee, C. (2023). Solar observations. Journal of Astronomy 22, 41 (2023).')
    note=paragraph('Publisher’s Note The publisher remains neutral on jurisdictional claims.')
    chosen=[p for _,p,_ in select(document([heading,first,figure,second,note]))]
    assert chosen==[heading,first,second]


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
