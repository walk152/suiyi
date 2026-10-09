"""Export a small, reviewed source tree; never publish or collect parent directories."""
from pathlib import Path
import hashlib
import json
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOP_NAMES={'LICENSE','NOTICE.md','README.md','CHANGELOG.md','CONTRIBUTING.md',
           '.gitignore','.gitattributes','Suiyi.spec','names1999.json',
           'turbo_manifest.json','models-lock.json'}
DIRS={'docs','third_party','.github','tools','packaging','dictionary'}
TEXT_EXT={'.py','.md','.txt','.json','.cs','.spec','.yml','.yaml','.html','.terms','.sh'}
SAFE_EXT=TEXT_EXT|{'.png','.ico'}
LICENSE_NAMES={'LICENSE','LICENCE','NOTICE','COPYING','COPYING.LESSER','COPYING.LGPL','THIRD-PARTY-PROGRAMS'}
SKIP_DIRS={'__pycache__','core-v05','public-v05','public-v05-validation','lzma-sdk'}


def files():
    result=[]
    for p in sorted(ROOT.rglob('*')):
        relative=p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):continue
        if len(relative.parts)==1:
            selected=p.name in TOP_NAMES or p.suffix=='.py' or (p.name.startswith('requirements') and p.suffix=='.txt')
        else:
            selected=relative.parts[0] in DIRS and (p.suffix.lower() in SAFE_EXT or p.name in LICENSE_NAMES
                     or p.name.upper().startswith(('LICENSE','LICENCE')))
            if relative.parts[:2]==('third_party','sources') and p.suffix.lower() in ('.zip','.gz','.bz2'):
                selected=True
        if not selected or not p.is_file():continue
        if p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400:
            raise ValueError('No linked files may enter the source export: '+str(relative))
        if p.stat().st_size>10*1024*1024:raise ValueError('Unexpected large source file: '+str(relative))
        if p.suffix in TEXT_EXT or p.name in LICENSE_NAMES|{'.gitignore','.gitattributes'} or p.name.upper().startswith(('LICENSE','LICENCE')):
            body=p.read_text(encoding='cp1252' if relative.parts[:2]==('third_party','intel') else 'utf-8-sig')
            if re.search(r'[A-Za-z]:[\\/]Users[\\/](?!Public\b)',body):
                raise ValueError('Personal absolute path in '+str(relative))
            if re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}',body):
                raise ValueError('Possible secret in '+str(relative))
        result.append(p)
    required=TOP_NAMES-{'Suiyi.spec'}
    if not required.issubset({p.name for p in result}):raise ValueError('Required source metadata missing')
    selected={p.relative_to(ROOT).as_posix() for p in result}
    manifest=json.loads((ROOT/'third_party/notice-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('errors'):raise ValueError('Unresolved third-party material errors')
    for row in manifest['files']:
        name='third_party/'+row['file']
        if name not in selected:raise ValueError('Required third-party material omitted: '+name)
        path=ROOT/name
        if path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Third-party material differs from manifest: '+name)
    return result


def main():
    members=files()
    release=ROOT/'release';release.mkdir(exist_ok=True)
    output=release/'Suiyi-v0.5-Public-Source.zip'
    temporary=output.with_suffix('.zip.part')
    rows={p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in members}
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for p in members:archive.write(p,'suiyi/'+p.relative_to(ROOT).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('Corrupt source archive')
            if len(archive.namelist())!=len(rows):raise ValueError('Unexpected member count')
            for name,row in rows.items():
                if hashlib.sha256(archive.read('suiyi/'+name)).hexdigest()!=row['sha256']:
                    raise ValueError('Archive differs from source: '+name)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    sha=hashlib.sha256(output.read_bytes()).hexdigest()
    (release/'SHA256SUMS.txt').write_text(sha+'  '+output.name+'\n',encoding='ascii')
    (release/'source-manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'file':output.name,'files':len(rows),'bytes':output.stat().st_size,'sha256':sha,'uploaded':False}))


if __name__=='__main__':main()
