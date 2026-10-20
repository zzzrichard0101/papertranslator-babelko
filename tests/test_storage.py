import ctypes
import os
import threading
from unittest.mock import patch

import pytest

from babelko.storage import read,save


@pytest.mark.skipif(os.name!='nt',reason='Windows shared-reader file semantics')
def test_save_retries_while_gui_style_reader_denies_replace(tmp_path):
    path=tmp_path/'state.json';save(path,{'progress':1})
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    # FILE_SHARE_READ | FILE_SHARE_WRITE, deliberately no FILE_SHARE_DELETE.
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
    assert handle!=ctypes.c_void_p(-1).value
    with pytest.raises(PermissionError):os.replace(path,tmp_path/'denied.json')
    release=threading.Timer(.08,lambda:kernel.CloseHandle(handle));release.start()
    try:save(path,{'progress':2})
    finally:release.join()
    assert read(path)=={'progress':2}
    assert not list(tmp_path.glob('*.tmp'))


def test_permanent_write_failure_keeps_previous_state_and_cleans_temp(tmp_path):
    path=tmp_path/'state.json';save(path,{'progress':1})
    with patch('babelko.storage.os.replace',side_effect=PermissionError('permanent denial')):
        with pytest.raises(PermissionError):save(path,{'progress':2})
    assert read(path)=={'progress':1}
    assert not list(tmp_path.glob('*.tmp'))


def test_windows_retry_is_bounded(tmp_path):
    path=tmp_path/'state.json';save(path,{'progress':1})
    denied=PermissionError('persistent Windows denial');denied.winerror=5
    with patch('babelko.storage.os.replace',side_effect=denied),patch('babelko.storage.time.monotonic',side_effect=[0,3]):
        with pytest.raises(PermissionError):save(path,{'progress':2})
    assert read(path)=={'progress':1}
    assert not list(tmp_path.glob('*.tmp'))
