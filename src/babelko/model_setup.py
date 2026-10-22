"""Download pinned, independently hashed local inference assets for Windows."""
import argparse
import hashlib
import json
import shutil
import stat
import time
import zipfile
from pathlib import Path

import httpx

from .storage import read,root,save


RUNTIME_RELEASE='b11718'
RUNTIME_ASSETS=(
    dict(name='llama-b11718-bin-win-cuda-12.4-x64.zip',size=267470642,
         url='https://github.com/ggml-org/llama.cpp/releases/download/b11718/llama-b11718-bin-win-cuda-12.4-x64.zip',
         sha256='c13fda0ef74f47cd2bccda1eea2a62980c12a5778d39b39bedadb525b4e81aff'),
    dict(name='cudart-llama-bin-win-cuda-12.4-x64.zip',size=391443627,
         url='https://github.com/ggml-org/llama.cpp/releases/download/b11718/cudart-llama-bin-win-cuda-12.4-x64.zip',
         sha256='8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'),
)
MODEL_ASSETS={
    'hy30b':dict(name='Hy-MT2-30B-A3B-Q4_K_M.gguf',size=18236702880,
        url='https://huggingface.co/tencent/Hy-MT2-30B-A3B-GGUF/resolve/fd3dcbb6b31e9e03923ef4f9f42500f74c3851c3/Hy-MT2-30B-A3B-Q4_K_M.gguf',
        sha256='bb44b11bb0f7cd3d1321645b41e911cd3de2e473731227fc6bf37aa18b543f88',
        id='tencent/Hy-MT2-30B-A3B-GGUF:Q4_K_M',adapter='hy',revision='fd3dcbb6b31e9e03923ef4f9f42500f74c3851c3',
        source_url='https://huggingface.co/tencent/Hy-MT2-30B-A3B-GGUF',license='Apache-2.0',
        options=dict(context=4096,temperature=.7,top_p=1.,top_k=-1,min_p=0.,repeat_penalty=1.,seed=42)),
    'qwen38':dict(name='Qwen3.8-27B-Q4_K_M.gguf',size=16810714464,
        url='https://registry.ollama.ai/v2/library/qwen3.8/blobs/sha256:f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d',
        sha256='f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d',
        id='qwen3.8:27b',adapter='qwen',revision='ollama-manifest-sha256:aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813',
        source_url='https://ollama.com/library/qwen3.8:27b',license='Apache-2.0',
        options=dict(context=4096,temperature=.7,top_p=.8,top_k=20,min_p=0.,repeat_penalty=1.,seed=42,enable_thinking=False)),
}


def sha256(path):
    with Path(path).open('rb') as stream:
        value=hashlib.sha256()
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def verified(path,asset):
    path=Path(path)
    return path.is_file() and path.stat().st_size==asset['size'] and sha256(path)==asset['sha256']


def download(asset,directory,transport=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    target=directory/asset['name'];partial=directory/(asset['name']+'.part')
    if verified(target,asset):
        print(f"이미 확인됨: {asset['name']}",flush=True);return target
    if target.exists():raise RuntimeError(f"기존 파일의 크기 또는 SHA256이 다릅니다: {target}")
    if partial.exists() and partial.stat().st_size>asset['size']:
        raise RuntimeError(f"부분 다운로드 파일이 예상보다 큽니다: {partial}")
    if not asset['url'].startswith('https://'):raise ValueError('HTTPS 자산 주소가 필요합니다.')
    for attempt in range(4):
        offset=partial.stat().st_size if partial.exists() else 0
        remaining=asset['size']-offset
        if shutil.disk_usage(directory).free<remaining+512*1024*1024:
            raise RuntimeError(f"저장 공간이 부족합니다: {directory}")
        if remaining==0:
            if verified(partial,asset):partial.replace(target);return target
            partial.unlink();offset=0
        headers={'Range':f'bytes={offset}-'} if offset else {}
        try:
            with httpx.Client(follow_redirects=True,timeout=90,transport=transport) as client:
                with client.stream('GET',asset['url'],headers=headers) as response:
                    response.raise_for_status()
                    if response.url.scheme!='https':raise RuntimeError('비보안 주소로 이동한 다운로드를 거부했습니다.')
                    if offset and response.status_code==206:
                        expected=f'bytes {offset}-{asset["size"]-1}/{asset["size"]}'
                        if response.headers.get('Content-Range')!=expected:
                            raise RuntimeError('다운로드 재개 범위가 원본과 맞지 않습니다.')
                    elif response.status_code==200:
                        offset=0
                    else:raise RuntimeError('예상하지 못한 다운로드 응답입니다.')
                    written=offset;last=time.monotonic();started=last
                    with partial.open('ab' if offset else 'wb') as output:
                        for chunk in response.iter_bytes(4*1024*1024):
                            written+=len(chunk)
                            if written>asset['size']:raise RuntimeError('예상 크기를 넘는 다운로드를 거부했습니다.')
                            output.write(chunk)
                            now=time.monotonic()
                            if now-last>=3:
                                speed=(written-offset)/max(now-started,.001)
                                print(f"{asset['name']}: {written/1e9:.2f}/{asset['size']/1e9:.2f} GB, {speed/1e6:.1f} MB/s",flush=True)
                                last=now
            if verified(partial,asset):partial.replace(target);return target
            if partial.stat().st_size==asset['size']:
                partial.unlink();raise RuntimeError(f"SHA256이 다릅니다: {asset['name']}")
            raise RuntimeError(f"다운로드가 중간에 끊겼습니다: {asset['name']}")
        except (httpx.HTTPError,OSError,RuntimeError):
            if attempt==3:raise
            time.sleep(min(2**attempt,8))
    raise AssertionError('unreachable')


def unpack_runtime(archives,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            for item in archive.infolist():
                name=item.filename
                if (name.startswith(('/', '\\')) or ':' in name or '..' in Path(name).parts
                        or stat.S_ISLNK(item.external_attr>>16)):
                    raise ValueError(f'안전하지 않은 실행 엔진 압축 경로: {name}')
                if not (directory/name).resolve().is_relative_to(directory.resolve()):
                    raise ValueError(f'안전하지 않은 실행 엔진 압축 경로: {name}')
            archive.extractall(directory)
    if not next(directory.rglob('llama-server.exe'),None):
        raise RuntimeError('압축을 풀었지만 llama-server.exe를 찾지 못했습니다.')
    save(directory/'babelko-verified.json',dict(release=RUNTIME_RELEASE,sha256=[a['sha256'] for a in RUNTIME_ASSETS]))


def runtime_valid(directory,registry):
    directory=Path(directory)
    if not directory.is_dir() or not next(directory.rglob('llama-server.exe'),None):return False
    marker=directory/'babelko-verified.json'
    if marker.is_file():
        value=read(marker)
        return value.get('release')==RUNTIME_RELEASE and value.get('sha256')==[a['sha256'] for a in RUNTIME_ASSETS]
    old={item.get('name'):item.get('sha256') for item in registry.get('assets',[]) if isinstance(item,dict)}
    return registry.get('runtime_release')==RUNTIME_RELEASE and all(old.get(a['name'])==a['sha256'] for a in RUNTIME_ASSETS)


def model_entry(key,asset,path):
    return dict(id=asset['id'],key=key,adapter=asset['adapter'],path=str(path),sha256=asset['sha256'],
                revision=asset['revision'],source_url=asset['source_url'],license=asset['license'],
                options=asset['options'],asset={name:asset[name] for name in ('name','size','url','sha256')} | {'kind':'model'})


def install(mode='hybrid',verify_only=False,home=None):
    if mode not in {'hybrid','qwen'}:raise ValueError('설치 모드 오류')
    home=Path(home) if home is not None else root();home.mkdir(parents=True,exist_ok=True)
    registry_path=home/'local_models.json'
    existing=read(registry_path) if registry_path.is_file() else {}
    keys=['qwen38'] if mode=='qwen' else ['hy30b','qwen38']
    runtime=Path(existing['runtime_dir']) if existing.get('runtime_dir') else home/'runtimes'/('llama-'+RUNTIME_RELEASE+'-cuda12')
    if not runtime_valid(runtime,existing):
        if verify_only:raise RuntimeError('CUDA 실행 엔진이 설치되지 않았거나 검증되지 않았습니다.')
        runtime=home/'runtimes'/('llama-'+RUNTIME_RELEASE+'-cuda12')
        archives=[download(asset,home/'downloads') for asset in RUNTIME_ASSETS]
        unpack_runtime(archives,runtime)
    models=dict(existing.get('models',{}))
    for key in keys:
        asset=MODEL_ASSETS[key];current=models.get(key,{})
        path=Path(current['path']) if current.get('path') else home/'models'/asset['name']
        if not verified(path,asset):
            if verify_only:raise RuntimeError(f'{key} 모델이 설치되지 않았거나 SHA256이 다릅니다.')
            path=download(asset,home/'models')
        models[key]=model_entry(key,asset,path)
    result={**existing,'schema':2,'runtime_release':RUNTIME_RELEASE,'runtime_dir':str(runtime),'models':models}
    if not verify_only:save(registry_path,result)
    print(json.dumps(dict(status='verified',mode=mode,models=keys,runtime_release=RUNTIME_RELEASE,
                          registry=str(registry_path)),ensure_ascii=False),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description='Download and verify local CUDA runtime and GGUF models')
    parser.add_argument('--mode',choices=['hybrid','qwen'],default='hybrid')
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args();install(args.mode,args.verify_only)
