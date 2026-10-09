"""Build a standalone offline v0.5 core installer from a fresh v0.5 runtime."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import os
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'dist/Suiyi'
WORK=ROOT/'packaging/public-v05'
RELEASE=ROOT/'release'
MODELS=('whisper-small.en','whisper-base','translate-en_zh-1_9','translate-zh_en-1_9')


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class LicenseHTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden and data.strip():self.parts.append(data.strip())


def prepare_terms():
    sections=[]
    for name in ['third_party/END_USER_TERMS.zh-CN.txt','LICENSE',
                 'third_party/intel/intel_openmp-2025.3.0.dist-info/LICENSE.txt',
                 'third_party/nvidia/CUDA-12.9.1-EULA.html',
                 'third_party/nvidia/cuDNN-9.27.0-EULA.html']:
        path=ROOT/name
        content=path.read_text(encoding='cp1252' if name.startswith('third_party/intel/') else 'utf-8')
        if path.suffix=='.html':
            parser=LicenseHTMLText();parser.feed(content);content='\n'.join(parser.parts)
        sections.append(name+'\n'+'='*60+'\n'+content)
    output=WORK/'public-license.txt'
    output.write_text('\n\n'.join(sections),encoding='utf-8')
    return output


def main():
    RELEASE.mkdir(exist_ok=True)
    if '--finalize' in sys.argv:
        rows=json.loads((WORK/'file-hashes.json').read_text(encoding='utf-8'))
        assert all(sha(STAGE/name)==row['sha256'] for name,row in rows.items())
        finalize(rows)
        return
    assert (STAGE/'Suiyi.exe').is_file(),'Build Suiyi.spec first'
    assert STAGE.resolve().is_relative_to(ROOT.resolve())
    manifest=json.loads((ROOT/'third_party/notice-manifest.json').read_text(encoding='utf-8'))
    assert not manifest.get('errors'),'Unresolved third-party material errors'
    for row in manifest['files']:
        path=(ROOT/'third_party'/row['file']).resolve()
        assert path.is_relative_to((ROOT/'third_party').resolve())
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['file']
    WORK.mkdir(exist_ok=True)
    terms=prepare_terms()
    for name in MODELS:
        shutil.copytree(ROOT/'models'/name,STAGE/'models'/name,dirs_exist_ok=True)
    assert {p.name for p in (STAGE/'models').iterdir()}==set(MODELS)
    for name in ('LICENSE','NOTICE.md','README.md'):
        shutil.copyfile(ROOT/name,STAGE/name)
    shutil.copytree(ROOT/'docs',STAGE/'docs',dirs_exist_ok=True)
    shutil.copytree(ROOT/'third_party',STAGE/'third_party',dirs_exist_ok=True)
    # Refresh notices collected before the final release audit completed.
    shutil.copytree(ROOT/'third_party',STAGE/'_internal/third_party',dirs_exist_ok=True)
    shutil.copytree(ROOT/'docs',STAGE/'_internal/docs',dirs_exist_ok=True)
    shutil.copyfile(terms,STAGE/'许可与第三方条款.txt')
    csc=str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    common=[csc,'/nologo','/target:winexe','/platform:x64','/optimize+',
        '/win32icon:'+str(ROOT/'packaging/suiyi.ico'),'/reference:System.Windows.Forms.dll',
        '/reference:System.Drawing.dll','/reference:System.IO.Compression.dll','/reference:Microsoft.CSharp.dll',
        '/resource:'+str(terms)+',PublicTerms']
    subprocess.run(common+['/out:'+str(STAGE/'Uninstall.exe'),str(ROOT/'packaging/Setup.cs')],check=True)
    files=sorted(p for p in STAGE.rglob('*') if p.is_file())
    rows={p.relative_to(STAGE).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files}
    (WORK/'file-hashes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (WORK/'files.txt').write_text('\n'.join(str(p.relative_to(STAGE)) for p in files)+'\n',encoding='utf-8')
    (WORK/'file-metadata.txt').write_text('\n'.join(str(p.stat().st_size)+'\t'+str(p.relative_to(STAGE)) for p in files)+'\n',encoding='utf-8')
    decoder=ROOT/'packaging/lzma-sdk/bin/x64/7zr.exe'
    archive=WORK/'payload.7z'
    assert not archive.exists(),'Refuse to append to an existing installer archive'
    with (WORK/'compression.log').open('w',encoding='utf-8') as log:
        subprocess.run([str(decoder),'a',str(archive),'@'+str(WORK/'files.txt'),'-scsUTF-8','-sccUTF-8',
            '-m0=lzma2','-mx=7','-mmt=4','-md=32m','-ms=256m','-bsp0'],cwd=STAGE,stdout=log,stderr=subprocess.STDOUT,check=True)
    finalize(rows)


def finalize(rows):
    archive=WORK/'payload.7z'
    decoder=ROOT/'packaging/lzma-sdk/bin/x64/7zr.exe'
    csc=str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    common=[csc,'/nologo','/target:winexe','/platform:x64','/optimize+',
        '/win32icon:'+str(ROOT/'packaging/suiyi.ico'),'/reference:System.Windows.Forms.dll',
        '/reference:System.Drawing.dll','/reference:System.IO.Compression.dll','/reference:Microsoft.CSharp.dll',
        '/resource:'+str(WORK/'public-license.txt')+',PublicTerms']
    print('Payload compressed; checking exact archive members',flush=True)
    listing=subprocess.check_output([str(decoder),'l',str(archive),'-slt','-sccUTF-8'],encoding='utf-8')
    listed=[]
    for block in listing.split('----------',1)[1].strip().split('\n\n'):
        fields=dict(line.split(' = ',1) for line in block.splitlines() if ' = ' in line)
        if 'Path' in fields and not fields.get('Attributes','').startswith('D'):
            listed.append(fields['Path'].replace('\\','/'))
    assert set(listed)==set(rows),(set(listed)-set(rows),set(rows)-set(listed))
    digest=bytes.fromhex(sha(archive))
    (WORK/'package-metadata.bin').write_bytes(struct.pack('<q',archive.stat().st_size)+digest)
    stub=WORK/'SetupStub.exe'
    subprocess.run(common+['/define:COMPACT','/out:'+str(stub),
        '/resource:'+str(WORK/'package-metadata.bin')+',PackageMetadata',
        '/resource:'+str(WORK/'file-metadata.txt')+',FileMetadata',
        '/resource:'+str(decoder)+',LocalDecoder',
        '/resource:'+str(ROOT/'packaging/lzma-sdk/DOC/lzma-sdk.txt')+',DecoderLicense',str(ROOT/'packaging/Setup.cs')],check=True)
    output=RELEASE/'Suiyi-v0.5-Public-Setup.exe'
    assert not output.exists(),'Refuse to overwrite a delivered installer'
    with output.open('xb') as stream:
        stream.write(stub.read_bytes())
        with archive.open('rb') as source:shutil.copyfileobj(source,stream,8*1024*1024)
    report=dict(file=output.name,version='0.5-public.1',bytes=output.stat().st_size,sha256=sha(output),
        installed_logical_bytes=sum(r['bytes'] for r in rows.values()),files=len(rows),
        core_models=list(MODELS),turbo_optional=True,standalone=True,requires_previous_install=False,
        new_archive_exact_members_verified=True,installation_verified=False)
    (WORK/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
