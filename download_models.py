"""Prepare fixed, hash-verified local models. Runtime inference never uses this downloader.

Small/base/translation models are the default; --with-turbo opts into the larger
model. Some upstream URLs (base and Argos) are mutable: if their bytes change,
this tool fails closed instead of accepting a different model. Review and update
models-lock.json deliberately when adopting new weights.
"""
from pathlib import Path, PurePosixPath
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
CHUNK = 1024 * 1024


def check_expected(expected):
    if not isinstance(expected.get('bytes'), int) or expected['bytes'] < 0:
        raise ValueError('Expected byte length is missing or invalid')
    if not re.fullmatch(r'[0-9a-f]{64}', expected.get('sha256', '')):
        raise ValueError('Expected SHA-256 is missing or invalid')


def reject_links(path):
    """Check existing ancestors without following a Windows junction or symlink."""
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Links/reparse points are not allowed: {part}')


def safe_path(root, relative):
    """Accept portable relative POSIX names; reject Windows aliases and traversal."""
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError(f'Unsafe relative path: {relative!r}')
    parts = relative.split('/')
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in parts):
        raise ValueError(f'Unsafe relative path: {relative!r}')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1, 10)),
                *('LPT'+str(n) for n in range(1, 10))}
    if any(part.split('.')[0].upper() in reserved for part in parts):
        raise ValueError(f'Reserved Windows path: {relative!r}')
    if PurePosixPath(relative).is_absolute():
        raise ValueError(f'Absolute path is not allowed: {relative!r}')
    root = Path(root).absolute()
    target = root.joinpath(*parts)
    reject_links(target)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes resource directory: {relative!r}')
    return target


def verify_file(path, expected):
    check_expected(expected)
    path = Path(path)
    reject_links(path)
    if not path.is_file() or path.stat().st_size != expected['bytes']:
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == expected['sha256']


def atomic_stream(source, destination, expected):
    """Preserve an existing destination until every incoming byte is verified."""
    check_expected(expected)
    destination = Path(destination).absolute()
    reject_links(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.'+destination.name+'-', suffix='.part',
                                         dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            size, digest = 0, hashlib.sha256()
            while block := source.read(CHUNK):
                size += len(block)
                if size > expected['bytes']:
                    raise ValueError(f'Download is larger than the locked size: {destination.name}')
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if size != expected['bytes'] or digest.hexdigest() != expected['sha256']:
            raise ValueError(f'Locked size/SHA-256 mismatch: {destination.name}; upstream may have changed')
        reject_links(destination)
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def download_verified(url, destination, expected, opener=None):
    """Reuse a correct cache; a merely non-empty file never counts as verified."""
    if verify_file(destination, expected):
        return False
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Resource downloads require an HTTPS URL without credentials')
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={'User-Agent': 'Suiyi-resource-setup/0.5'})
    with opener(request, timeout=60) as response:
        # urllib follows redirects. Keep transport protection on the final URL too.
        final_url = response.geturl() if hasattr(response, 'geturl') else url
        if urllib.parse.urlsplit(final_url).scheme != 'https':
            raise ValueError('Resource download redirected to a non-HTTPS URL')
        atomic_stream(response, destination, expected)
    return True


def extract_verified(archive_path, output_root, expected_files):
    """Extract an exact allowlist into a fresh staging directory, never extractall()."""
    expected_folded = set()
    for name, expected in expected_files.items():
        safe_path(output_root, name)
        check_expected(expected)
        if name.casefold() in expected_folded:
            raise ValueError('Duplicate case-insensitive locked archive path')
        expected_folded.add(name.casefold())
    with zipfile.ZipFile(archive_path) as archive:
        entries, seen = {}, set()
        for item in archive.infolist():
            name = item.filename.rstrip('/') if item.is_dir() else item.filename
            safe_path(output_root, name)
            if name.casefold() in seen:
                raise ValueError(f'Duplicate archive path: {name}')
            seen.add(name.casefold())
            kind = stat.S_IFMT(item.external_attr >> 16)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f'Archive links/special files are not allowed: {name}')
            if item.flag_bits & 1:
                raise ValueError('Encrypted model archives are not supported')
            if item.is_dir():
                if not any(key.startswith(name+'/') for key in expected_files):
                    raise ValueError(f'Unexpected archive directory: {name}')
                continue
            if name not in expected_files:
                raise ValueError(f'Unexpected archive member: {name}')
            if item.file_size != expected_files[name]['bytes']:
                raise ValueError(f'Archive member size differs from lock: {name}')
            entries[name] = item
        if set(entries) != set(expected_files):
            raise ValueError('Archive is missing locked files')
        for name, item in entries.items():
            with archive.open(item) as source:
                atomic_stream(source, safe_path(output_root, name), expected_files[name])


def load_lock(path):
    lock = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if lock.get('format') != 1 or not isinstance(lock.get('models'), dict):
        raise ValueError('Unsupported models-lock.json format')
    return lock


def prepare_models(lock, models_dir, cache_dir, with_turbo=False, verify_only=False, opener=None):
    import io
    models_dir, cache_dir = Path(models_dir).absolute(), Path(cache_dir).absolute()
    reject_links(models_dir)
    reject_links(cache_dir)
    results = {}
    for name, spec in lock['models'].items():
        if spec.get('optional') and not with_turbo:
            continue
        folder = safe_path(models_dir, name)
        files = spec['files']
        if not files:
            raise ValueError(f'No locked files for {name}')
        correct = {relative: verify_file(safe_path(folder, relative), row)
                   for relative, row in files.items()}
        if all(correct.values()):
            print(f'{name}: verified cache', flush=True)
            results[name] = 'verified'
            continue
        if verify_only:
            missing = ', '.join(relative for relative, valid in correct.items() if not valid)
            raise ValueError(f'{name}: missing or damaged locked files: {missing}')
        print(f'{name}: preparing verified files', flush=True)
        if spec['kind'] == 'archive':
            package = spec['archive']
            cached = safe_path(cache_dir, name+'.argosmodel')
            download_verified(package['url'], cached, package, opener=opener)
            models_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.suiyi-model-', dir=models_dir) as staging:
                expected = {name+'/'+relative: row for relative, row in files.items()}
                extract_verified(cached, staging, expected)
                for relative, row in files.items():
                    if correct[relative]:
                        continue
                    with safe_path(staging, name+'/'+relative).open('rb') as source:
                        atomic_stream(source, safe_path(folder, relative), row)
        elif spec['kind'] == 'files':
            for relative, row in files.items():
                if correct[relative]:
                    continue
                target = safe_path(folder, relative)
                if 'inline_base64' in row:
                    payload = base64.b64decode(row['inline_base64'], validate=True)
                    atomic_stream(io.BytesIO(payload), target, row)
                else:
                    download_verified(row['url'], target, row, opener=opener)
        else:
            raise ValueError(f'Unknown resource kind for {name}')
        if not all(verify_file(safe_path(folder, relative), row) for relative, row in files.items()):
            raise ValueError(f'Model verification failed after preparation: {name}')
        results[name] = 'prepared'
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-turbo', action='store_true', help='Also prepare the optional locked turbo model')
    parser.add_argument('--verify-only', action='store_true', help='Check local files only; no downloads or writes')
    parser.add_argument('--models-dir', type=Path, default=ROOT/'models')
    parser.add_argument('--cache-dir', type=Path, default=ROOT/'.cache/resource-downloads')
    parser.add_argument('--lock', type=Path, default=ROOT/'models-lock.json')
    args = parser.parse_args()
    prepare_models(load_lock(args.lock), args.models_dir, args.cache_dir,
                   with_turbo=args.with_turbo, verify_only=args.verify_only)
    print('All requested local models match models-lock.json.', flush=True)


if __name__ == '__main__':
    main()
