from babelko.validation import tracking_status
from babelko.storage import save


def test_lost_tracked_translation_is_reported_even_if_pdf_exists(tmp_path):
    p=tmp_path/'tracker.json';save(p,dict(page=[dict(paragraph=[dict(pdf_unicode='English source',input='English source',output=None)])]))
    assert tracking_status(p)['status']=='failed' and tracking_status(p)['units_with_no_output']==1


def test_preserved_formula_without_translation_input_is_not_missing(tmp_path):
    p=tmp_path/'tracker.json';save(p,dict(page=[dict(paragraph=[dict(pdf_unicode='Equation',input=None,output=None),dict(pdf_unicode='Source',input='Source',output='번역')])]))
    assert tracking_status(p)['status']=='passed' and tracking_status(p)['parsed_translation_units']==1
