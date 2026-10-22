import hashlib
import zipfile

import httpx
import pytest

from babelko import model_setup


def asset(name,data):
    return dict(name=name,size=len(data),sha256=hashlib.sha256(data).hexdigest(),url='https://example.test/'+name)


def test_interrupted_model_download_resumes_at_verified_byte(tmp_path):
    data=b'abcdef';spec=asset('model.gguf',data)
    (tmp_path/'model.gguf.part').write_bytes(data[:3])
    def handler(request):
        assert request.headers['Range']=='bytes=3-'
        return httpx.Response(206,headers={'Content-Range':'bytes 3-5/6'},content=data[3:])
    path=model_setup.download(spec,tmp_path,httpx.MockTransport(handler))
    assert path.read_bytes()==data
    assert not (tmp_path/'model.gguf.part').exists()


def test_model_download_rejects_wrong_resume_range(tmp_path,monkeypatch):
    data=b'abcdef';spec=asset('model.gguf',data)
    (tmp_path/'model.gguf.part').write_bytes(data[:3])
    monkeypatch.setattr(model_setup.time,'sleep',lambda _:None)
    def handler(request):
        return httpx.Response(206,headers={'Content-Range':'bytes 2-5/6'},content=data[3:])
    with pytest.raises(RuntimeError,match='범위'):
        model_setup.download(spec,tmp_path,httpx.MockTransport(handler))
    assert not (tmp_path/'model.gguf').exists()


def test_runtime_zip_cannot_escape_install_directory(tmp_path):
    archive=tmp_path/'runtime.zip'
    with zipfile.ZipFile(archive,'w') as writer:writer.writestr('../outside.exe',b'bad')
    with pytest.raises(ValueError,match='안전하지 않은'):
        model_setup.unpack_runtime([archive],tmp_path/'runtime')
    assert not (tmp_path/'outside.exe').exists()


def test_qwen_only_installer_registers_verified_local_files(tmp_path,monkeypatch):
    runtime_zip=tmp_path/'runtime.zip'
    with zipfile.ZipFile(runtime_zip,'w') as writer:writer.writestr('llama-server.exe',b'fake')
    runtime_bytes=runtime_zip.read_bytes();runtime_spec=asset('runtime.zip',runtime_bytes)
    model_bytes=b'fake-gguf';model_spec={**model_setup.MODEL_ASSETS['qwen38'],**asset('qwen.gguf',model_bytes)}
    monkeypatch.setattr(model_setup,'RUNTIME_ASSETS',(runtime_spec,))
    monkeypatch.setitem(model_setup.MODEL_ASSETS,'qwen38',model_spec)
    def handler(request):
        return httpx.Response(200,content=runtime_bytes if request.url.path.endswith('runtime.zip') else model_bytes)
    original=model_setup.download
    monkeypatch.setattr(model_setup,'download',lambda spec,directory:original(spec,directory,httpx.MockTransport(handler)))
    result=model_setup.install('qwen',home=tmp_path/'home')
    assert result['runtime_release']=='b11718'
    assert set(result['models'])=={'qwen38'}
    assert result['models']['qwen38']['options']['enable_thinking'] is False
    assert (tmp_path/'home/local_models.json').is_file()
    assert model_setup.install('qwen',verify_only=True,home=tmp_path/'home')['models']==result['models']
