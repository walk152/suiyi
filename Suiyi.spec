from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata
import sys

root=Path(SPECPATH)
site=Path(sys.prefix)/'Lib'/'site-packages'
datas=[(str(root/'turbo_manifest.json'),'.')]
datas += [(str(root/name),'.') for name in ['LICENSE','NOTICE.md']]
datas += [(str(p),'docs') for p in (root/'docs').glob('*.md')]
datas += [(str(p),str(p.parent.relative_to(root))) for p in (root/'third_party').rglob('*') if p.is_file()]
datas.append((str(root/'names1999.json'),'.'))
datas += [(str(p),'ocr_models') for p in (root/'ocr_models').glob('*.onnx')]
datas += [(str(p),'dictionary') for p in (root/'dictionary').iterdir() if p.is_file()]
binaries=[]
hidden=['pystray._win32','soundcard.mediafoundation','_cffi_backend']
for package in ['rapidocr_onnxruntime','faster_whisper','soundcard']:
    datas+=collect_data_files(package)
for package in ['ctranslate2','onnxruntime']:
    binaries+=collect_dynamic_libs(package)
hidden+=collect_submodules('rapidocr_onnxruntime')
for package in ['faster-whisper','ctranslate2','soundcard','huggingface-hub','tokenizers']:
    datas+=copy_metadata(package)
# GPU DLLs are loaded dynamically and must retain their package-relative locations.
for item in (site/'nvidia').rglob('*.dll'):
    binaries.append((str(item),str(item.parent.relative_to(site))))
for info in site.glob('*.dist-info'):
    for item in info.rglob('*'):
        if item.is_file() and any(word in str(item.relative_to(info)).lower() for word in ['license','copying','notice']):
            datas.append((str(item),str(Path('licenses')/info.name/item.parent.relative_to(info))))
# Some wheels store notices in the package rather than dist-info.
for package in ['onnxruntime','ctranslate2','rapidocr_onnxruntime','sentencepiece']:
    for item in (site/package).rglob('*'):
        if item.is_file() and any(word in item.name.lower() for word in ['license','copying','notice']):
            datas.append((str(item),str(Path('licenses')/package/item.parent.relative_to(site/package))))
a=Analysis(['app.py'],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hidden,
           runtime_hooks=[str(root/'tools/public_audio_hook.py')],
           module_collection_mode={'pystray':'py','shapely':'py'},
           excludes=['av','pytest','IPython','matplotlib','torch','tensorflow'],noarchive=False)
# OCR uses OpenCV image operations only. Its optional video plugin is not loaded.
# PyAV and its hard-linked codec dependencies are excluded as an entire package.
a.binaries=[row for row in a.binaries if 'opencv_videoio_ffmpeg' not in row[0].lower()
            and row[0].replace('\\','/').lower()!='ctranslate2/cudnn64_9.dll']
for name,source,kind in a.binaries:
    if any(word in name.lower() for word in ['avcodec','avformat','avutil','swresample','x264','x265','ffmpeg','av.libs']):
        raise RuntimeError('Unexpected codec in public build: '+name)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Suiyi',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,disable_windowed_traceback=False,icon=str(root/'packaging'/'suiyi.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Suiyi')
