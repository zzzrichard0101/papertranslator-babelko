import os,shutil
from pathlib import Path
from babelko.upstream import assets
from babelko.storage import root,read,save,digest
if __name__=='__main__':
    previous=Path(os.environ['LOCALAPPDATA'])/'PaperTranslator/model_registry.json'
    if previous.exists() and not (root()/'local_models.json').exists():save(root()/'local_models.json',read(previous))
    from babelko.ocr import data_path,OCR_SHA
    data=data_path()
    if data and digest(data/'eng.traineddata')==OCR_SHA:
        target=root()/'assets/ocr';target.mkdir(parents=True,exist_ok=True)
        if data.resolve()!=target.resolve():shutil.copyfile(data/'eng.traineddata',target/'eng.traineddata')
    target=root()/'assets/ocr';target.mkdir(parents=True,exist_ok=True)
    if not (target/'eng.traineddata').exists():
        import httpx
        url='https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e12c65a915945e4c28e237a9b52bc4a8f39a0cec/eng.traineddata'
        temporary=target/'eng.traineddata.downloading'
        try:
            with httpx.stream('GET',url,timeout=60,follow_redirects=False,trust_env=False) as response:
                response.raise_for_status();size=0
                with temporary.open('wb') as stream:
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>15400601:raise ValueError('Unexpected OCR model size')
                        stream.write(chunk)
            if temporary.stat().st_size!=15400601 or digest(temporary)!=OCR_SHA:raise ValueError('OCR checksum mismatch')
            temporary.replace(target/'eng.traineddata')
        finally:temporary.unlink(missing_ok=True)
    print(assets())
