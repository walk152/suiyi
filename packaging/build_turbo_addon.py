"""Build the optional data pack from current local models, without old installers."""
from pathlib import Path
import hashlib,json,zipfile


def verify_pack(output, expected):
    with zipfile.ZipFile(output) as archive:
        assert sorted(archive.namelist())==sorted(expected),'Unexpected or duplicate model entries'
        for name,row in expected.items():
            assert archive.getinfo(name).file_size==row['bytes'],name
            with archive.open(name) as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'],name


def build(root, output, expected):
    root=Path(root).resolve();output=Path(output)
    if output.exists():
        verify_pack(output,expected)
        return False
    # Validate every source before creating a new artifact.
    for name,row in expected.items():
        path=(root/name).resolve()
        assert path.is_relative_to(root/'models/whisper-turbo'),name
        assert path.stat().st_size==row['bytes'],name
        with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'],name
    temporary=output.with_suffix(output.suffix+'.building')
    assert not temporary.exists(),'An unfinished model build exists'
    try:
        with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
            for name in expected:archive.write(root/name,name)
        verify_pack(temporary,expected)
        # Windows rename refuses an existing destination; never overwrite a user's pack.
        temporary.rename(output)
    finally:
        if temporary.exists():temporary.unlink()
    return True


def main():
    root=Path(__file__).resolve().parents[1]
    release=root/'release';release.mkdir(exist_ok=True)
    output=release/'Suiyi-Turbo-v1.suiyimodel'
    expected=json.loads((root/'turbo_manifest.json').read_text(encoding='utf-8'))['files']
    created=build(root,output,expected)
    with output.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    report=dict(file=output.name,bytes=output.stat().st_size,sha256=sha,files_verified=len(expected),
        installed_bytes=sum(r['bytes'] for r in expected.values()),data_only=True,network_required=False,reused_existing=not created)
    (release/'turbo扩展包信息.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
