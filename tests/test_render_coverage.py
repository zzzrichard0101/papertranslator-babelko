import pymupdf as fitz
from babelko.render_coverage import inspect,short_evidence
from babelko.storage import save


def test_pdf_generation_does_not_hide_lost_translation(tmp_path):
    pdf=tmp_path/'result.pdf';tracker=tmp_path/'tracking.json'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((30,50),'translated prose missing');doc.save(pdf)
    save(tracker,dict(page=[dict(pdf_unicode='Original',input='Original',output='이 문장은 최종 출력에 반드시 있어야 하는 번역문입니다.')]))
    assert inspect(pdf,tracker)['status']=='failed'


def test_spaces_style_tokens_and_formula_boundaries_do_not_look_like_omissions(tmp_path):
    pdf=tmp_path/'result.pdf';tracker=tmp_path/'tracking.json'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((30,50),'이문장은최종출력에표시되는한국어번역입니다',fontname='korea');doc.save(pdf)
    save(tracker,dict(page=[dict(pdf_unicode='Original',input='Original',output="<style id='1'>이 문장은 최종 출력에 표시되는 한국어 번역입니다</style>{v2}")]))
    assert inspect(pdf,tracker)['status']=='passed'


def test_rotated_page_bounds_are_checked_in_display_coordinates(tmp_path):
    from babelko.validation import inspect_output
    pdf=tmp_path/'rotated.pdf'
    with fitz.open() as doc:
        p=doc.new_page(width=300,height=500);p.insert_text((30,450),'A valid rotated page.');p.set_rotation(90);doc.save(pdf)
    assert inspect_output(pdf,[0])['status']=='passed'
    # A mismatched count reports a diagnostic rather than an IndexError.
    assert inspect_output(pdf,[])['status']=='failed'


def test_duplicate_title_on_another_page_cannot_hide_a_lost_running_header(tmp_path):
    pdf=tmp_path/'two-pages.pdf';tracker=tmp_path/'tracking.json';text='이것은 원래의 페이지에 표시되어야 하는 반복 제목입니다'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((30,50),text,fontname='korea');doc.new_page();doc.save(pdf)
    save(tracker,dict(page=[dict(paragraph=[dict(pdf_unicode='Title',input='Title',output=text)]),dict(paragraph=[dict(pdf_unicode='Header',input='Header',output=text)])]))
    result=inspect(pdf,tracker)
    assert result['status']=='failed' and result['missing'][0]['page']==2


def test_one_phrase_cannot_pay_for_two_occurrences_even_with_a_title_prefix(tmp_path):
    pdf=tmp_path/'one-page.pdf';tracker=tmp_path/'tracking.json';title='원래의 위치에 있어야 하는 한국어 반복 제목입니다'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((30,50),'연구보고서 '+title,fontname='korea');doc.save(pdf)
    save(tracker,dict(page=[dict(paragraph=[dict(pdf_unicode='Title',input='Title',output='연구보고서 '+title),dict(pdf_unicode='Header',input='Header',output=title)])]))
    assert inspect(pdf,tracker)['status']=='failed'


def test_individually_drawn_korean_glyphs_reconstruct_visual_row(tmp_path):
    pdf=tmp_path/'glyphs.pdf';tracker=tmp_path/'tracking.json'
    text='지침서의 배경 및 개발 과정'
    with fitz.open() as doc:
        page=doc.new_page();x=30
        for char in text:
            page.insert_text((x,50),char,fontname='korea',fontsize=10)
            x+=12 if char!=' ' else 6
        doc.save(pdf)
    save(tracker,dict(page=[dict(pdf_unicode='Background',input='Background',output=text)]))
    assert inspect(pdf,tracker)['status']=='passed'


def test_missing_short_translation_fails_even_on_an_empty_page(tmp_path):
    pdf=tmp_path/'missing-short.pdf';tracker=tmp_path/'tracking.json'
    with fitz.open() as doc:
        doc.new_page();doc.save(pdf)
    save(tracker,dict(page=[dict(pdf_unicode='disabled',input='disabled',output='비활성화')]))
    result=inspect(pdf,tracker)
    assert result['status']=='failed'
    assert result['missing_short_fragments']==1
    assert result['missing'][0]['code']=='short_text_missing'


def test_short_phrase_is_present_and_repeated_short_phrase_needs_two_occurrences(tmp_path):
    pdf=tmp_path/'short.pdf';tracker=tmp_path/'tracking.json'
    with fitz.open() as doc:
        doc.new_page().insert_text((30,50),'비활성화',fontname='korea');doc.save(pdf)
    save(tracker,dict(page=[dict(paragraph=[
        dict(pdf_unicode='disabled',input='disabled',output='비활성화'),
        dict(pdf_unicode='disabled again',input='disabled again',output='비활성화')])]))
    result=inspect(pdf,tracker)
    assert result['status']=='failed' and result['missing_short_fragments']==1
    save(tracker,dict(page=[dict(pdf_unicode='disabled',input='disabled',output='비활성화')]))
    assert inspect(pdf,tracker)['status']=='passed'


def test_long_sentence_cannot_also_pay_for_a_missing_short_unit(tmp_path):
    pdf=tmp_path/'embedded.pdf';tracker=tmp_path/'tracking.json'
    long='이 문장은 비활성화 상태가 표시된다는 사실을 설명합니다'
    with fitz.open() as doc:
        doc.new_page().insert_text((30,50),long,fontname='korea');doc.save(pdf)
    save(tracker,dict(page=[dict(paragraph=[
        dict(pdf_unicode='Long',input='Long',output=long),
        dict(pdf_unicode='Short',input='Short',output='비활성화')])]))
    result=inspect(pdf,tracker)
    assert result['status']=='failed' and result['missing_short_fragments']==1


def test_long_cross_page_fragment_reserves_before_one_syllable_page_fragment():
    pages=['우변에서는다른대상에는']
    short=[(0,0,'는'),(1,None,'우변에서는')]
    assert short_evidence(pages,pages,[],short)==[True,True]
    assert short_evidence(['우변에서는'],['우변에서는'],[],short)==[False,True]
