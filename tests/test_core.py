import copy
from pathlib import Path
import pytest
from babelko.pipeline import selected_pages
from babelko.translator import validate_items
from babelko.upstream import prepare


@pytest.mark.parametrize('spec,expected',[('',[0,1,2,3]),('1-2,4',[0,1,3]),('2-',[1,2,3]),('-2',[0,1]),('2,2',[1])])
def test_page_selection(spec,expected):assert selected_pages(spec,4)==expected

@pytest.mark.parametrize('spec',['0','5','3-1','1--2','1,x'])
def test_bad_selection(spec):
    with pytest.raises(ValueError):selected_pages(spec,4)


def test_korean_alias_selects_korean_primary_fonts():
    prepare()
    from babeldoc.assets.assets import get_font_family
    assert get_font_family('ko')['normal']==get_font_family('KR')['normal']
    assert all('KR-' in s for s in get_font_family('ko')['normal'][:4])


def inputs():return [dict(id=0,input="The value is {v1}<style id='2'>24</style>."),dict(id=1,input='The change was -2.5.')]
def outputs():return [dict(id=0,output="값은 {v1}<style id='2'>24</style>이다."),dict(id=1,output='변화량은 -2.5였다.')]


def test_complete_batch_preserves_placeholders_and_number_counts():assert validate_items(inputs(),outputs())==outputs()

@pytest.mark.parametrize('change',['lost','duplicate','tag','number','sign','extra','blank','bad_id','bad_type'])
def test_invalid_batch_is_never_accepted(change):
    value=outputs()
    if change=='lost':value.pop()
    if change=='duplicate':value[1]['id']=0
    if change=='tag':value[0]['output']=value[0]['output'].replace('{v1}','')
    if change=='number':value[0]['output']=value[0]['output'].replace('24','42')
    if change=='sign':value[1]['output']=value[1]['output'].replace('-2.5','2.5')
    if change=='extra':value[1]['output']+=' 99'
    if change=='blank':value[1]['output']=''
    if change=='bad_id':value[1]['id']=True
    if change=='bad_type':value[1]['output']=False
    with pytest.raises(ValueError):validate_items(inputs(),value)


@pytest.mark.parametrize('source,target',[('We used100K samples.','100K개의 표본을 사용했다.'),('We used 35-45 samples.','35~45개의 표본을 사용했다.'),('Mip-NeRF360 uses 1080p.','Mip-NeRF360은 1080p를 사용한다.'),('There were three groups.','집단은 3개였다.'),('The model is four times smaller.','모델 크기는 4분의 1이다.')])
def test_legitimate_numeric_forms_do_not_retry(source,target):
    assert validate_items([dict(id=0,input=source)],[dict(id=0,output=target)])


@pytest.mark.parametrize('source,target',[('Use one-fourth of the points.','점의 4분의 1을 사용한다.'),('Use one-third of the samples.','표본의 3분의 1을 사용한다.')])
def test_written_fraction_equivalence(source,target):
    assert validate_items([dict(id=0,input=source)],[dict(id=0,output=target)])


def test_wrong_fraction_is_still_rejected():
    with pytest.raises(ValueError):validate_items([dict(id=0,input='Use one-fourth of the points.')],[dict(id=0,output='점의 3분의 1을 사용한다.')])



def test_plain_fallback_has_same_guards_and_bounded_retry():
    import threading
    from babelko.translator import KoreanTranslator
    t=object.__new__(KoreanTranslator);t.lock=threading.Lock();t.cancel=lambda:False;t.retries=0;t.hard_failures=[]
    replies=iter(['값은 42이다.','값은 24이다.']);t._request=lambda *a:next(replies)
    assert t.do_llm_translate('Rules. Now translate the following text:\nThe value is 24.')=='값은 24이다.'
    assert t.retries==1 and not t.hard_failures


def test_plain_failure_is_recorded_and_cannot_be_reported_as_success():
    import threading
    from babelko.translator import KoreanTranslator
    t=object.__new__(KoreanTranslator);t.lock=threading.Lock();t.cancel=lambda:False;t.retries=0;t.hard_failures=[]
    t._request=lambda *a:'값은 42이다.'
    with pytest.raises(ValueError):t.do_llm_translate('Rules. Now translate the following text:\nThe value is 24.')
    assert t.retries==1 and len(t.hard_failures)==1
