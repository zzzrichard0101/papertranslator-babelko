import copy
from types import SimpleNamespace as NS
import pytest
from babelko.scan_evidence import corrections,apply,rule_only,raster_single_glyph,duplicate_title,running_scan_headers,suspect_regions
from babelko.translator import number_errors


def test_named_research_levels_and_world_war_ordinal_are_not_invented_numbers():
    assert not number_errors('A primary source and a secondary source.', '1차 자료와 2차 자료.')
    assert not number_errors('Six people were interned during WWII.', '제2차 세계대전 중 6명이 수용되었다.')
    assert number_errors('A primary source.', '1차 자료와 7건의 사례.')


def test_lowercase_roman_enumeration_is_not_an_arabic_quantity():
    source='Therefore, using Lemma 2.1, part i., there exists a solution.'
    assert not number_errors(source, '따라서 보조정리 2.1의 i)항을 이용하면 해가 존재한다.')
    assert number_errors(source, '따라서 보조정리 2.2의 i)항을 이용하면 해가 존재한다.')
    assert not number_errors('Part II covers World War II.', '제2부는 제2차 세계대전을 다룬다.')


def test_repeated_decade_resolves_source_reference_without_hiding_other_dates():
    source='1980s: The journal started in 1983. At the end of the decade, research grew.'
    target='1980년대: 학술지는 1983년에 창간되었다. 1980년대 말 연구가 늘었다.'
    assert not number_errors(source,target)
    assert number_errors(source,target.replace('1983','1984'))


def test_weekly_session_can_explicitly_be_once_per_week():
    source='One hour per weekly session over 12 weeks.'
    assert not number_errors(source,'12주 동안 주 1회, 매회 1시간씩 진행한다.')
    assert number_errors(source,'12주 동안 주 3회, 매회 1시간씩 진행한다.')


def test_polynomial_degree_terms_license_only_corresponding_korean_ordinals():
    assert not number_errors('A quadratic and a cubic system.','2차 및 3차 반응계.')
    assert not number_errors('A second-order quadratic system.','2차 2차 반응계.')
    assert number_errors('A quadratic system.','2차 반응계와 3개의 해.')
    assert number_errors('A quadratic system.','3차 반응계.')


def test_overlapping_short_scan_title_does_not_repeat_full_heading():
    from types import SimpleNamespace as Obj
    full=Obj(unicode='NON-EXPERIMENTAL DESCRIPTIVE RESEARCH',layout_label='title',
        box=Obj(x=87,y=350,x2=522,y2=380))
    fragment=Obj(unicode='DESCRIPTIVE RESE RCH',layout_label='title',
        box=Obj(x=285,y=355,x2=505,y2=373))
    assert duplicate_title(fragment,[full,fragment])
    assert not duplicate_title(full,[full,fragment])
    fragment.box=Obj(x=285,y=400,x2=505,y2=420)
    assert not duplicate_title(fragment,[full,fragment])


def test_numbered_scan_running_header_stays_in_original_raster():
    box=lambda y,y2:NS(x=80,y=y,x2=530,y2=y2)
    header=NS(unicode='112 WIRSuCion io AYTORRPY RESIN, cece sss',layout_label='title',box=box(777,820))
    overlap=NS(unicode='Introduction to 112 Research',layout_label='title',box=box(788,815))
    chapter=NS(unicode='A SEARCH FOR HOME',layout_label='title',box=box(295,345))
    unrelated=NS(unicode='113 independent experiments',layout_label='title',box=box(650,675))
    assert running_scan_headers([header,overlap,chapter,unrelated],842)=={id(header),id(overlap)}


def test_raster_page_with_no_ocr_text_gets_independent_full_page_check():
    import pymupdf as fitz
    with fitz.open() as printed:
        page=printed.new_page(width=400,height=300)
        page.insert_text((30,100),'Visible words on a scanned page.',fontsize=12)
        image=page.get_pixmap()
        with fitz.open() as scanned:
            raster=scanned.new_page(width=400,height=300)
            raster.insert_image(raster.rect,pixmap=image)
            assert raster.get_text().strip()==''
            assert suspect_regions(raster)==[raster.rect]
        blank=printed.new_page(width=400,height=300)
        assert suspect_regions(blank)==[]


def test_missing_primary_ocr_text_flows_into_cached_second_reader(tmp_path,monkeypatch):
    import pymupdf as fitz
    from babelko.scan_evidence import Reader,evidence
    from babelko.storage import digest,save
    folder=tmp_path/'job';folder.mkdir()
    with fitz.open() as printed:
        page=printed.new_page(width=400,height=300)
        page.insert_text((30,100),'Several important source words are visible here.',fontsize=12)
        image=page.get_pixmap()
        with fitz.open() as scanned:
            raster=scanned.new_page(width=400,height=300)
            raster.insert_image(raster.rect,pixmap=image)
            scanned.save(folder/'Original.pdf')
    (folder/'Input.pdf').write_bytes((folder/'Original.pdf').read_bytes())
    save(folder/'state.json',dict(ocr_pages=[0],source_sha256=digest(folder/'Original.pdf'),
                                  input_sha256=digest(folder/'Input.pdf')))
    calls=[]
    def recognize(self,page,clip=None):
        calls.append(clip)
        return [dict(text='Several important source words are visible here.',score=.99,
                     bbox=[30,85,350,105])]
    monkeypatch.setattr(Reader,'recognize',recognize)
    first=evidence(folder,[0]);second=evidence(folder,[0])
    assert first==second and len(calls)==1
    assert calls[0]==fitz.Rect(0,0,400,300)


def test_two_pixel_reads_can_restore_shuffled_title_without_adding_letters():
    from babelko.recovery import reordered_title
    source='REVIEW BOARD THEINSTITUTIONAL RESEARCH AND THE DEFINITION OF'
    image='THE INSTITUTIONAL REVIEW BOARD AND THE DEFINITION OF RESEARCH'
    assert reordered_title(source,image,image)==image
    assert reordered_title(source,image,image+' METHODS') is None
    assert reordered_title(source,image+' METHODS',image+' METHODS') is None


@pytest.mark.parametrize('source,target',[
    ('World War II ended in 1945.','제2차 세계대전은 1945년에 끝났다.'),
    ('Throughout Part II and Part III.','제2부와 제3부 전반에서.'),
    ('Thirty-four participants attended.','34명이 참석했다.'),
    ('Mid-20th century theory.','20세기 중반의 이론.'),
])
def test_equivalent_number_spellings(source,target):assert not number_errors(source,target)


def test_explicit_decade_to_ten_years_preserves_other_numbers():
    assert not number_errors('Over more than a decade, the context grew to 2M tokens.',
                             '10년 이상에 걸쳐 문맥이 200만 토큰으로 늘었다.')
    assert not number_errors('One decade passed.', '10년이 지났다.')
    assert number_errors('A decade passed, and 24 people participated.', '10년이 지났다.')
    assert number_errors('A decade passed.', '20년이 지났다.')
    assert number_errors('Several decades passed.', '10년이 지났다.')
    assert not number_errors('The share fell over the last decade.', '지난 10년 동안 비중이 감소했다.')
    assert number_errors('The share fell over the last decade.', '지난 20년 동안 비중이 감소했다.')


def test_spelled_large_quantities_and_zeroth_order_keep_exact_values():
    assert not number_errors('We computed up to one million prime gaps.', '소수 간격을 100만 개까지 계산했다.')
    assert not number_errors('Two million points and a zeroth-order term.', '200만 개의 점과 0차 항.')
    assert number_errors('We computed up to one million prime gaps and 24 cases.', '소수 간격을 100만 개까지 계산했다.')
    assert number_errors('Two million points.', '200만 점과 7개 사례.')
    assert number_errors('A zeroth-order term.', '1차 항.')


def test_exact_24_hour_clock_conversion_keeps_other_quantities_strict():
    source='Observed 3 November 2021 around 18:00 UT and lasted 30 minutes.'
    assert not number_errors(source,'2021년 11월 3일 오후 6시경 관측되었고 30분 지속되었다.')
    assert number_errors(source,'2021년 11월 3일 오후 7시경 관측되었고 30분 지속되었다.')
    assert number_errors(source,'2021년 11월 3일 오전 6시경 관측되었고 30분 지속되었다.')
    assert number_errors(source,'2021년 11월 3일 오후 6시경 관측되었다.')


def test_transliterated_proper_name_suffix_is_not_a_negative_number():
    source='Helios-1 and Helios-2 measured 10 mV, while the temperature was -5.'
    target='헬리오스-1과 헬리오스-2가 10 mV를 측정했고 기온은 -5였다.'
    assert not number_errors(source,target)
    assert number_errors(source,target.replace('헬리오스-2','헬리오스-3'))
    assert number_errors(source,target.replace('기온은 -5','기온은 5'))
    assert number_errors('The temperature was 5.','기온-5였다.')


@pytest.mark.parametrize('source,target',[
    ('World War II ended in 1945.','제3차 세계대전은 1945년에 끝났다.'),
    ('Thirty-four participants attended.','30명이 참석했다.'),
    ('The temperature is -20.','기온은 20이다.'),
    ('The variable I is 10.','변수 1은 10이다.'),
])
def test_number_guard_remains_strict(source,target):assert number_errors(source,target)


def test_ocr_correction_requires_two_sided_independent_image_evidence():
    source='Go 10 its Website to find information.'
    result,edits=corrections(source,[dict(text='Go to its Website to find information.',score=.99)])
    # Not enough left context: never guess, even on an apparently obvious typo.
    assert result==source and not edits
    source='The authors recommend that you go 10 its Website to find information.'
    good=[dict(text='The authors recommend that you go to its Website to find information.',score=.99)]
    result,edits=corrections(source,good)
    assert result==source.replace('10','to') and len(edits)==1
    assert corrections(source,[{**good[0],'score':.8}])==(source,[])
    assert corrections(source,[dict(text=source,score=.99)])==(source,[])
    assert number_errors(source,'저자들은 웹사이트에 방문하라고 권한다.')


def test_scan_typography_changes_only_output_styles_without_shared_mutation():
    shared=NS(font_size=40,font_id='f1');formula=NS(pdf_style=shared)
    run=NS(pdf_style=shared,unicode='번역문')
    p=NS(debug_id='p',pdf_style=shared,pdf_paragraph_composition=[NS(pdf_same_style_unicode_characters=run,pdf_formula=None),NS(pdf_same_style_unicode_characters=None,pdf_formula=formula)])
    docs=NS(page=[NS(page_number=0,pdf_paragraph=[p])]);apply(docs,{(0,'p'):dict(size=11)})
    assert run.pdf_style.font_size==p.pdf_style.font_size==11
    assert formula.pdf_style.font_size==shared.font_size==40 and run.unicode=='번역문'


def test_rule_exclusion_needs_pixel_evidence_and_retains_real_text():
    import pymupdf as f
    with f.open() as d:
        p=d.new_page(width=400,height=200);p.draw_line((30,80),(350,80),width=1)
        assert rule_only(p,NS(x=25,x2=355,y=110,y2=130))
        p.insert_text((30,120),'The result is 10, not 20.',fontsize=12)
        assert not rule_only(p,NS(x=25,x2=355,y=70,y2=90))


def test_raster_single_glyph_preserves_a_scanned_section_letter_but_not_a_heading():
    import pymupdf as f
    def scanned(label):
        with f.open() as vector:
            page=vector.new_page(width=600,height=180)
            page.draw_line((70,50),(530,50),width=1)
            page.insert_text((290,79),label,fontname='hebo',fontsize=26)
            page.draw_line((70,90),(530,90),width=1)
            pixels=page.get_pixmap(matrix=f.Matrix(2,2)).tobytes('png')
        pdf=f.open();page=pdf.new_page(width=600,height=180)
        page.insert_image(page.rect,stream=pixels)
        return pdf
    box=NS(x=70,x2=530,y=180-95,y2=180-45)
    with scanned('C') as pdf:
        assert raster_single_glyph(pdf[0],box,'C BE Nr re TI SI TTC Tm a i.')
    with scanned('Research') as pdf:
        assert not raster_single_glyph(pdf[0],box,'Research methods and context')


def test_band_reconstruction_keeps_neighboring_runs_and_original_scan():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200)
        src.insert_text((30,80),'Correct source row',fontsize=12)
        p=derived.new_page(width=400,height=200)
        p.insert_text((30,20),'Outside top',fontsize=12)
        p.insert_text((30,80),'a',fontsize=48)
        # Its bbox overlaps the band. Redaction would delete its first letters.
        p.insert_text((30,108),'Neighbor must survive',fontsize=12)
        before=[original.xref_stream(x) for x in src.get_contents()]
        count=reconstruct_band(p,src,f.Rect(0,45,400,100),[dict(text='Correct source row',score=.99,bbox=[30,65,150,84])])
        assert count==1 and [original.xref_stream(x) for x in src.get_contents()]==before
        text=p.get_text()
        assert 'Correct source row' in text and '\na\n' not in text
        assert 'Outside top' in text and 'Neighbor must survive' in text
        assert max(s['size'] for b in p.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans'])<20


def test_incomplete_second_ocr_cannot_delete_a_table_row_or_duplicate_it():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200);p=derived.new_page(width=400,height=200)
        p.insert_text((20,80),'Treatment A',fontsize=12)
        p.insert_text((170,80),'Important unmatched outcome',fontsize=12)
        n=reconstruct_band(p,src,f.Rect(0,45,400,100),[dict(text='Treatment A',score=.99,bbox=[20,65,100,84])])
        text=p.get_text()
        assert 'Important unmatched outcome' in text
        assert text.count('Treatment A')==1


def test_agreed_word_keeps_its_text_while_inflated_ocr_font_is_repaired():
    import pymupdf as f
    from babelko.scan_evidence import reconstruct_band
    with f.open() as original,f.open() as derived:
        src=original.new_page(width=400,height=200);p=derived.new_page(width=400,height=200)
        src.insert_text((50,80),'behavioral therapy',fontsize=12)
        p.insert_text((50,80),'behavioral',fontsize=48)
        for y in [20,120,160]:p.insert_text((20,y),'Ordinary neighboring row',fontsize=12)
        reconstruct_band(p,src,f.Rect(0,40,400,105),[dict(text='behavioral therapy',score=.88,bbox=[50,67,250,84])])
        spans=[s for b in p.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans']]
        word=next(s for s in spans if s['text']=='behavioral')
        assert word['size']<20 and p.get_text().count('behavioral')==1
