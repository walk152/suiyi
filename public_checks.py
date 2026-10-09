"""Read-only checks for the replaceable libraries of the public Windows bundle."""
from pathlib import Path
import os
import sys
from runtime_paths import BUNDLE_ROOT, FROZEN


def loaded_module_paths():
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    process=kernel.GetCurrentProcess()
    handles=(wintypes.HMODULE*4096)();needed=wintypes.DWORD()
    psapi.EnumProcessModules.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    psapi.EnumProcessModules.restype=wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes=[wintypes.HANDLE,wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
    psapi.GetModuleFileNameExW.restype=wintypes.DWORD
    if not psapi.EnumProcessModules(process,handles,ctypes.sizeof(handles),ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value>ctypes.sizeof(handles):raise RuntimeError('Too many runtime libraries')
    paths=[]
    for handle in handles[:needed.value//ctypes.sizeof(wintypes.HMODULE)]:
        name=ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process,handle,name,len(name)):paths.append(Path(name.value))
    return paths


def check_libraries():
    import pystray
    import shapely
    from shapely.geometry import Polygon
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    import public_audio
    assert decode_audio is public_audio.decode_audio
    assert not any(name=='av' or name.startswith('av.') for name in sys.modules)
    assert abs(Polygon([(0,0),(2,0),(2,2),(0,2)]).area-4)<1e-9
    tray_path=Path(pystray.__file__).resolve()
    shapely_path=Path(shapely.__file__).resolve()
    if FROZEN:
        assert tray_path.is_file() and tray_path.suffix=='.py'
        assert tray_path.is_relative_to(BUNDLE_ROOT.resolve())
        assert shapely_path.is_file() and shapely_path.suffix=='.py'
        assert list((BUNDLE_ROOT/'shapely.libs').glob('geos*.dll'))
    geos_paths=[path for path in loaded_module_paths() if path.name.lower().startswith('geos')]
    assert len(geos_paths)>=2
    if FROZEN:assert all(path.resolve().is_relative_to((BUNDLE_ROOT/'shapely.libs').resolve()) for path in geos_paths)
    replacement=getattr(pystray,'_suiyi_replacement_probe',None)
    expected=os.environ.get('SUIYI_REPLACEMENT_PROBE')
    if expected is not None:assert replacement==expected
    return dict(ok=True,pystray_external_source=str(tray_path),shapely_external_source=str(shapely_path),
                geos_version=shapely.geos_version_string,pcm_adapter=True,pyav_loaded=False,
                replacement_probe=replacement,geos_loaded_paths=list(map(str,geos_paths)),no_capture=True)
