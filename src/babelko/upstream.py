"""Pinned source-client bridge. No changes to upstream source or the prior app."""
import os,sys
from pathlib import Path
from .storage import project,root


def prepare():
    source=project()/'upstream/PDFMathTranslate-next'
    if not (source/'pdf2zh_next/__init__.py').is_file():raise RuntimeError('먼저 scripts/setup.ps1로 상위 프로젝트를 준비하세요.')
    if str(source) not in sys.path:sys.path.insert(0,str(source))
    import babeldoc.const as const
    cache=root()/'assets';cache.mkdir(exist_ok=True)
    const.CACHE_FOLDER=cache
    const.TIKTOKEN_CACHE_FOLDER=cache/'tiktoken';const.TIKTOKEN_CACHE_FOLDER.mkdir(exist_ok=True)
    os.environ['TIKTOKEN_CACHE_DIR']=str(const.TIKTOKEN_CACHE_FOLDER)
    from babeldoc.assets import assets as asset_api
    if not getattr(asset_api.get_font_family,'_babelko',False):
        original=asset_api.get_font_family
        def korean_family(code):return original('KR' if code.lower() in {'ko','ko-kr'} else code)
        korean_family._babelko=True;asset_api.get_font_family=korean_family
    # The pinned typesetter recognizes KR but omits the ISO language code KO.
    # Keep the public language code while selecting its existing CJK spacing.
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    if not getattr(Typesetting.__init__,'_babelko',False):
        original_init=Typesetting.__init__
        def korean_typesetter(self,translation_config):
            original_init(self,translation_config)
            if translation_config.lang_out.lower() in {'ko','ko-kr'}:self.is_cjk=True
        korean_typesetter._babelko=True;Typesetting.__init__=korean_typesetter


def assets(progress=print):
    prepare()
    from babeldoc.assets import assets as a
    from babeldoc.assets.embedding_assets_metadata import CMAP_METADATA
    from tiktoken import encoding_for_model
    progress('배치 인식 모델 준비')
    a.get_doclayout_onnx_model_path()
    names=list(dict.fromkeys(n for group in a.get_font_family('ko').values() for n in group))
    for i,name in enumerate(names):
        progress(f'한국어 글꼴 준비 {i+1}/{len(names)}: {name}');a.get_font_and_metadata(name)
    for name in CMAP_METADATA:a.run_coro(a.get_cmap_file_path_async(name))
    encoding_for_model('gpt-4o')
    return dict(fonts=names,cmaps=len(CMAP_METADATA))
