from unittest.mock import patch
import pytest
import pymupdf as fitz
from babelko.storage import digest,read
from babelko.ocr import prepare,OCR_SHA


def test_primary_ocr_resumes_completed_pages_and_keeps_lossless_pixels(tmp_path):
    source=tmp_path/'source.pdf'
    with fitz.open() as doc:
        for n in range(3):doc.new_page(width=300,height=400).insert_text((30,80),'Research observations and study records.',fontsize=11)
        doc.save(source)
    calls=[];hash_checks=[]
    def ocr(pix,**kw):
        calls.append(1)
        with fitz.open() as doc:
            doc.new_page(width=300,height=400).insert_text((30,80),'Research observations and study records.',fontsize=11)
            return doc.tobytes()
    def hash_file(path):
        if str(path).endswith('eng.traineddata'):hash_checks.append(1);return OCR_SHA
        return digest(path)
    target=tmp_path/'resume'/'Input.pdf';target.parent.mkdir()
    with patch.object(fitz.Pixmap,'pdfocr_tobytes',ocr),patch('babelko.ocr.data_path',lambda:tmp_path),patch('babelko.ocr.digest',hash_file):
        with pytest.raises(InterruptedError):prepare(source,target,'force',lambda *_:None,lambda:len(calls)>=1)
        assert len(list((target.parent/'primary-ocr-pages').glob('*.json')))==1
        prepare(source,target,'force',lambda *_:None)
        assert len(calls)==3 and len(hash_checks)==2
        assert read(target.with_suffix('.transformations.json'))['ocr_cache']['hits']==1
        fresh=tmp_path/'fresh'/'Input.pdf';fresh.parent.mkdir();prepare(source,fresh,'force',lambda *_:None)
    with fitz.open(target) as a,fitz.open(fresh) as b:
        assert len(a)==len(b)==3
        for x,y in zip(a,b):
            assert x.get_text('words')==y.get_text('words')
            assert x.get_pixmap().samples==y.get_pixmap().samples


def test_unprofitable_parallel_reader_is_not_enabled_by_default():
    from babelko.scan_evidence import recognition_workers
    assert recognition_workers(8)==recognition_workers(32)==recognition_workers(313)==1


def test_cancelled_parallel_ocr_task_starts_no_reader(tmp_path):
    from babelko.scan_evidence import recognize_task
    marker=tmp_path/'cancel';marker.touch()
    with patch('babelko.scan_evidence.Reader',side_effect=AssertionError('reader started')):
        with pytest.raises(InterruptedError):recognize_task((str(tmp_path/'unused.pdf'),0,[],str(marker)))
