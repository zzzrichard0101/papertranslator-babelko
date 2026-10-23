from babelko.encoded_font import decode,metric_identifiers
from babelko.hybrid import errors,literal
from babelko.assurance import tasks


def test_pdf_shifted_font_is_read_as_words_but_keeps_formula_tokens():
    raw='\x00)\x00R\x00U\x00H\x00J\x00U\x00R\x00X\x00Q\x00G{v1}\x00,\x00W\x00H\x00U\x00D\x00W\x00L\x00R\x00Q'
    assert decode(raw)=='Foreground{v1}Iteration'
    assert decode('Ordinary PDF text')=='Ordinary PDF text'
    assert [item['text'] for item in tasks(raw,'전경{v1}반복 횟수') if item['side']=='source']==['Foreground{v1}Iteration']
    assert '인코딩된 글꼴 텍스트 미번역' in errors(raw,raw)
    assert not errors(raw,'전경{v1}반복 횟수')


def test_metric_cell_identifiers_are_preserved_as_literals():
    metrics='PSNR {v1}SSIM {v2}MS-SSIM {v3}D-SSIM{v4}LPIPS-vgg {v5}LPIPS-alex{v6}'
    assert metric_identifiers(metrics) and literal(metrics)
    assert not metric_identifiers('Method {v1}Accuracy {v2}')
