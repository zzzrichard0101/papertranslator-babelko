from babelko.ocr import reading_order


def run(x,y,name,width=220):return dict(bbox=(x,y,x+width,y+12),text=name)


def test_repeated_two_columns_read_entire_left_then_right():
    runs=[run(x,y,f'{x}-{y}') for y in [100,120,140] for x in [40,330]]
    assert [r['text'] for r in reading_order(runs,600)]==[f'{x}-{y}' for x in [40,330] for y in [100,120,140]]


def test_full_width_bands_keep_header_and_footer_on_correct_sides():
    header=run(40,40,'header',500);footer=run(40,600,'footer',500)
    runs=[run(x,y,f'{x}-{y}') for y in [100,120,140] for x in [40,330]]
    ordered=reading_order(runs+[footer,header],600)
    assert ordered[0]['text']=='header' and ordered[-1]['text']=='footer'
    assert [r['text'] for r in ordered[1:-1]]==[f'{x}-{y}' for x in [40,330] for y in [100,120,140]]


def test_weak_or_indented_single_column_does_not_become_two_columns():
    runs=[run(40,100,'body',400),run(150,150,'quote',300),run(40,200,'body2',400)]
    assert [r['text'] for r in reading_order(list(reversed(runs)),600)]==['body','quote','body2']
