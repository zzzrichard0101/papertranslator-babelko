from types import SimpleNamespace as NS
import pymupdf as fitz
from babelko.region_ledger import RegionLedger,pixels_preserved
from babelko.storage import save


def row(identity,page,x,y,text='12'):
    return dict(id=identity,source_page=page,source_box=[x,y,x+15,y+12],role='table',source=text,
        policy='translate',inputs=[text],record_keys=['shared-content-key'],target=text,
        glyphs=[dict(text=c,box=[x+i*6,y,x+(i+1)*6,y+12]) for i,c in enumerate(text)])


def fixture(tmp_path,rows,move=None,omit=None):
    path=tmp_path/'fixture.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        for item in rows:
            if item['id']==omit:continue
            for glyph in item['glyphs']:
                x,y,x2,y2=glyph['box'];dx=120 if item['id']==move else 0
                page.insert_text((x+dx,800-y2+10),glyph['text'],fontsize=12)
        pdf.save(path)
    # Use actual font boxes as the post-typesetting plan, independently of
    # which output glyphs will later be moved/deleted by the exporter fault.
    with fitz.open(path) as pdf:
        for item in rows:
            if item['id']==omit:continue
            text=pdf[0].get_text('rawdict');chars=[c for b in text['blocks'] for l in b.get('lines',[]) for s in l['spans'] for c in s['chars']]
            original=item['glyphs']
            chosen=chars[(0 if item is rows[0] else len(rows[0]['glyphs'])):][:len(original)]
            for g,c in zip(original,chosen):
                a,b,d,e=c['bbox'];offset=120 if item['id']==move else 0
                g['box']=[a-offset,800-e,d-offset,800-b]
    ledger=RegionLedger(tmp_path);ledger.rows=rows
    return ledger.inspect(path,[0])


def test_same_numeric_value_in_two_cells_requires_two_correct_positions(tmp_path):
    rows=[row('left',1,50,700),row('right',1,350,700)]
    report=fixture(tmp_path,rows)
    assert report['status']=='passed' and report['checked_regions']==2


def test_short_cell_moved_to_wrong_column_fails_even_though_text_still_exists(tmp_path):
    report=fixture(tmp_path,[row('left',1,50,700),row('right',1,350,700)],move='right')
    assert report['status']=='failed'
    assert report['issues'][0]['region_id']=='right'
    assert 'pdf_glyph_missing_or_moved' in report['issues'][0]['codes']


def test_missing_one_duplicate_cell_cannot_borrow_the_other_cell(tmp_path):
    report=fixture(tmp_path,[row('left',1,50,700),row('right',1,350,700)],omit='right')
    assert report['status']=='failed' and report['issues'][0]['region_id']=='right'


def test_source_prose_omitted_before_translation_is_detected(tmp_path):
    r=row('omitted',1,50,700,'Text');r.update(inputs=[],target=None,record_keys=[])
    report=fixture(tmp_path,[r])
    assert report['status']=='failed' and 'source_region_not_submitted' in report['issues'][0]['codes']


def test_preserved_chart_label_is_checked_for_glyphs_without_model_submission(tmp_path):
    r=row('axis',1,50,700,'11.7');r.update(role='fallback_line',inputs=[],target=None,record_keys=[])
    assert fixture(tmp_path,[r])['status']=='passed'
    assert fixture(tmp_path,[r],omit='axis')['status']=='failed'


def test_exactly_preserved_fallback_pixels_resolve_unreliable_font_coordinates(tmp_path):
    source=tmp_path/'source.pdf';output=tmp_path/'output.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((50,100),'Axis',fontsize=12)
        pdf.save(source)
    output.write_bytes(source.read_bytes())
    r=row('axis',1,45,690,'Axis')
    r.update(source_box=[45,680,100,710],role='fallback_line',inputs=[],target=None,record_keys=[])
    # Some embedded-font IL glyph boxes are unrelated to PDF text boxes.
    for glyph in r['glyphs']:glyph['box']=[300,680,310,690]
    ledger=RegionLedger(tmp_path);ledger.rows=[r]
    assert ledger.inspect(output,[0],source)['status']=='passed'
    with fitz.open() as pdf:
        pdf.new_page(width=600,height=800)
        pdf.save(output,incremental=False)
    assert ledger.inspect(output,[0],source)['status']=='failed'


def test_new_punctuation_drawing_fragment_is_not_unmapped_translation(tmp_path):
    ledger=RegionLedger(tmp_path);ledger.collecting=True
    ledger.pre(NS(debug_id='new',unicode='—'),'.')
    assert ledger.unknown==[]
    ledger.pre(NS(debug_id='new',unicode='Untranslated body text'),'Untranslated body text')
    assert len(ledger.unknown)==1


def test_source_occurrence_ids_distinguish_page_and_geometry_but_share_content(tmp_path):
    def paragraph(x):return NS(unicode='Same source.',box=NS(x=x,y=50,x2=x+100,y2=70),layout_label='text',debug_id='repeated')
    pages=[NS(page_number=0,pdf_paragraph=[paragraph(50),paragraph(350)]),NS(page_number=1,pdf_paragraph=[paragraph(50)])]
    ledger=RegionLedger(tmp_path);ledger.begin(NS(page=pages))
    assert len({r['id'] for r in ledger.rows})==3
    assert len({r['source'] for r in ledger.rows})==1


def test_batch_worker_and_paragraph_worker_bind_by_source_and_returned_target(tmp_path):
    import threading
    p=NS(unicode='A result.',box=NS(x=50,y=50,x2=150,y2=70),layout_label='text',debug_id='a')
    ledger=RegionLedger(tmp_path);ledger.begin(NS(page=[NS(page_number=0,pdf_paragraph=[p])]))
    ledger.pre(p,'A result.')
    thread=threading.Thread(target=lambda:ledger.link(dict(key='actual',source='A result.',final='결과이다.')))
    thread.start();thread.join();ledger.post(p,'결과이다.')
    assert ledger.rows[0]['record_keys']==['actual']
    ledger.post(p,'다른 내용이다.')
    # A second post cannot keep a stale link from a different target.
    assert ledger.rows[0]['record_keys']==[]


def test_cached_repeated_cell_links_only_exact_complete_target(tmp_path):
    folder=tmp_path/'job';(folder/'hybrid').mkdir(parents=True)
    save(folder/'unit-order.json',dict(active_keys=['short','exact','other']))
    for key,target in [('short','우리의'),('exact','우리의 방법'),('other','저희 방법')]:
        save(folder/'hybrid'/(key+'.json'),dict(key=key,source='Ours',final=target))
    ledger=RegionLedger(folder)
    item=dict(inputs=['Ours'],target='우리의 방법',record_keys=[])
    ledger.relink_saved_row(item)
    assert item['record_keys']==['exact']


def test_preserved_pixel_tolerance_accepts_edge_noise_but_rejects_lost_ink():
    original=bytes([0]*700+[255]*9300)
    noisy=bytes([0]*696+[255]*4+[255]*9271+[180]*29)
    assert pixels_preserved(NS(width=100,height=100,samples=original),NS(width=100,height=100,samples=noisy))
    missing=bytes([255]*60+[0]*640+[255]*9300)
    assert not pixels_preserved(NS(width=100,height=100,samples=original),NS(width=100,height=100,samples=missing))


def test_cropbox_excludes_hidden_spread_and_rebases_visible_glyphs(tmp_path):
    source=tmp_path/'source.pdf';output=tmp_path/'output.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((130,100),'Visible',fontsize=12)
        page.set_cropbox(fitz.Rect(100,0,500,800))
        pdf.save(source)
    output.write_bytes(source.read_bytes())
    with fitz.open(output) as pdf:
        chars=[c for b in pdf[0].get_text('rawdict')['blocks'] for line in b.get('lines',[])
            for span in line.get('spans',[]) for c in span.get('chars',[])]
    visible=row('visible',1,130,690,'Visible')
    visible['glyphs']=[dict(text=c['c'],box=[c['bbox'][0]+100,800-c['bbox'][3],
        c['bbox'][2]+100,800-c['bbox'][1]]) for c in chars]
    hidden=row('hidden',1,30,690,'Hidden')
    ledger=RegionLedger(tmp_path);ledger.rows=[visible,hidden]
    result=ledger.inspect(output,[0],source)
    assert result['status']=='passed' and result['checked_regions']==1
