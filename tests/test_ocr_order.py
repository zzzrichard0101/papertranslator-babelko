from babelko.ocr import reading_order,split_merged_column_lines,unsupported_punctuation


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


def test_merged_middle_line_splits_only_with_repeated_two_column_evidence():
    def line(x,y,words):
        spans=[dict(bbox=(x+n*30,y,x+(n+1)*30,y+12),text=word,size=12,origin=(x+n*30,y+10)) for n,word in enumerate(words)]
        return dict(bbox=(x,y,x+len(words)*30,y+12),spans=spans)
    source=[line(x,y,['one','two','three','four','five','six','seven'])
            for x in (40,340) for y in (100,140,180)]
    merged={**line(40,160,['left']*7),'spans':line(40,160,['left']*7)['spans']+line(340,160,['right']*7)['spans'],
            'bbox':(40,160,550,172)}
    parts=split_merged_column_lines(source+[merged],600)
    assert len(parts)==len(source)+2
    assert [' '.join(s['text'] for s in part['spans']) for part in parts[-2:]]==['left '*6+'left','right '*6+'right']
    assert split_merged_column_lines([merged],600)==[merged]


def test_footer_below_both_columns_follows_right_column():
    runs=[run(x,y,f'{x}-{y}') for y in [100,120,140] for x in [40,330]]
    footer=run(40,500,'footnote',180)
    ordered=reading_order(runs+[footer],600)
    assert ordered[-1]['text']=='footnote'


def test_punctuation_rejection_requires_blank_source_pixels():
    import numpy as np
    span=dict(text='~~',bbox=(4,4,8,8))
    white=np.full((15,15,3),255,dtype=np.uint8)
    assert unsupported_punctuation(span,white,1,1)
    white[5,5]=0
    assert not unsupported_punctuation(span,white,1,1)
    assert not unsupported_punctuation({**span,'text':'A.D.'},np.full((15,15,3),255,dtype=np.uint8),1,1)
