"""Install a pinned, data-only turbo extension from a local archive, never a service."""
from pathlib import Path
import errno,hashlib,json,os,shutil,tempfile,zipfile
from runtime_paths import APP_ROOT,BUNDLE_ROOT,atomic_text

PREFIX='models/whisper-turbo/'
IDENTITY='Suiyi-0.2-offline-20261002'

def trusted_files():
    return json.loads((BUNDLE_ROOT/'turbo_manifest.json').read_text(encoding='utf-8'))['files']

def turbo_ready(root=None,expected=None):
    root=Path(root) if root is not None else APP_ROOT
    expected=expected if expected is not None else trusted_files()
    return all((root/name).is_file() and (root/name).stat().st_size==row['bytes'] for name,row in expected.items())

def install_pack(package,progress=lambda p:None,root=None,expected=None):
    root=Path(root) if root is not None else APP_ROOT
    expected=expected if expected is not None else trusted_files()
    if not expected or any(not name.startswith(PREFIX) or '/' in name[len(PREFIX):] or '\\' in name or ':' in name or '..' in name for name in expected):
        raise ValueError('扩展清单无效。')
    # Trust only the bundled manifest, never a manifest supplied inside an archive.
    with zipfile.ZipFile(package) as archive:
        entries=archive.infolist()
        if len(entries)!=len(expected) or {item.filename for item in entries}!=set(expected):
            raise ValueError('不是受支持的 turbo 扩展包，或文件清单不完整。')
        for item in entries:
            if item.is_dir() or item.file_size!=expected[item.filename]['bytes'] or item.flag_bits&1:
                raise ValueError('扩展包文件大小不匹配或已加密。')
        models=root/'models'
        for path in [root,models,models/'whisper-turbo',*(root/name for name in expected)]:
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('模型目录包含链接，已取消安装。')
        uninstall=root/'suiyi-install-manifest.txt'
        registered=None
        if uninstall.exists():
            lines=uninstall.read_text(encoding='utf-8-sig').splitlines()
            if not lines or lines[0]!=IDENTITY:raise ValueError('程序卸载清单无效。')
            registered=list(dict.fromkeys(lines[1:]+[name.replace('/','\\') for name in expected]))
        if turbo_ready(root,expected):
            if registered is not None:atomic_text(uninstall,IDENTITY+'\n'+'\n'.join(registered)+'\n')
            progress(100);return False
        models.mkdir(parents=True,exist_ok=True)
        total=sum(row['bytes'] for row in expected.values())
        if shutil.disk_usage(models).free<total*2+32*1024*1024:
            raise OSError('安装 turbo 扩展暂需约 3.3 GB 空闲空间，完成后新增约 1.62 GB。')
        done=0
        with tempfile.TemporaryDirectory(prefix='.turbo-import-',dir=models) as temp:
            stage=Path(temp)
            for item in entries:
                output=stage/Path(item.filename).name;digest=hashlib.sha256()
                with archive.open(item) as source,output.open('wb') as destination:
                    while block:=source.read(4*1024*1024):
                        digest.update(block);destination.write(block);done+=len(block)
                        progress(min(95,int(done*95/total)))
                if digest.hexdigest()!=expected[item.filename]['sha256']:
                    raise ValueError('扩展包校验失败，未安装；请重新取得完整文件。')
            target=models/'whisper-turbo';target.mkdir(exist_ok=True)
            if registered is not None:atomic_text(uninstall,IDENTITY+'\n'+'\n'.join(registered)+'\n')
            for name in expected:
                source=stage/Path(name).name;dest=root/name
                try:source.replace(dest)
                except OSError as exc:
                    if exc.errno!=errno.EXDEV and getattr(exc,'winerror',None)!=17:raise
                    with source.open('rb') as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
    progress(100);return True
