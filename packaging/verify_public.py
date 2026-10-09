"""Validate a public installer in a fresh workspace directory, without registering it.

Run with a permitted 16 kHz PCM WAV in SUIYI_TEST_AUDIO. SUIYI_TEST_DEVICE
selects cpu/cuda/auto (cuda by default). No live microphone or loopback capture
is opened. Build PyInstaller and the standalone installer before this check.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import traceback
import wave
import winreg


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'packaging/public-v05'
TARGET = ROOT / 'packaging/public-v05-validation'
INSTALLER = ROOT / 'release/Suiyi-v0.5-Public-Setup.exe'
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Suiyi'
IDENTITY = 'Suiyi-0.2-offline-20261002'
LICENSES = (
    'LICENSE', 'NOTICE.md', 'docs/THIRD_PARTY.md', 'docs/LICENSE_ZH.md',
    'third_party/END_USER_TERMS.zh-CN.txt', 'third_party/notice-manifest.json',
    'third_party/ecdict/ECDICT-LICENSE.txt',
    'third_party/faster-whisper/LICENSE', 'third_party/ctranslate2/LICENSE',
    'third_party/whisper/LICENSE', 'third_party/silero/LICENSE',
    'third_party/rapidocr/LICENSE', 'third_party/sentencepiece/LICENSE',
    'third_party/onnxruntime/LICENSE', 'third_party/onnxruntime/ThirdPartyNotices.txt',
    'third_party/pystray/COPYING', 'third_party/pystray/COPYING.LGPL',
    'third_party/shapely/LICENSE.txt', 'third_party/shapely/LICENSE_GEOS',
    'third_party/shapely/LICENSE_win32',
    'third_party/argos/translate-en_zh-1_9-README.md',
    'third_party/argos/translate-zh_en-1_9-README.md',
    'third_party/argos/CC-BY-4.0.txt',
    'third_party/nvidia/cuBLAS-wheel-License.txt',
    'third_party/nvidia/cuDNN-wheel-License.txt',
    'third_party/nvidia/NVRTC-wheel-License.txt',
    'third_party/nvidia/CUDA-12.9.1-EULA.html',
    'third_party/nvidia/cuDNN-9.27.0-EULA.html',
    'third_party/nvidia/cuDNN-9.27.0-Acknowledgements.html',
    'third_party/nvidia/dll-inventory.json',
    'third_party/pystray/source-verification.json',
    'third_party/sources/geos-3.13.1.tar.bz2',
)
LICENSE_GLOBS = (
    'third_party/sources/pystray-0.19.5.*',
    'third_party/sources/shapely-2.1.2.*',
    'third_party/python/LICENSE-3.12.*.txt',
    'third_party/tcl-tk/tcl-8.6.*-license.terms',
    'third_party/tcl-tk/tk-8.6.*-license.terms',
)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def safe_child(base, name):
    """Reject traversal and reparse points before touching validation files."""
    base = Path(base).resolve()
    path = base / name
    require(not Path(name).is_absolute() and ':' not in str(name), 'Absolute member path')
    resolved = path.resolve()
    require(resolved != base and resolved.is_relative_to(base), 'Path escapes validation directory')
    for item in (path, *path.parents):
        if item.exists():
            require(not item.is_symlink() and not (
                getattr(item.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ), 'Linked validation path: ' + str(item))
    return path


def registration():
    """Retain exact values/types in memory, including absent keys and subkeys."""
    def read_key(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            return None
        with key:
            child_count, value_count, _ = winreg.QueryInfoKey(key)
            values = sorted((winreg.EnumValue(key, i) for i in range(value_count)), key=lambda row: row[0])
            children = {
                child: read_key(path + '\\' + child)
                for child in sorted(winreg.EnumKey(key, i) for i in range(child_count))
            }
            return values, children
    return read_key(KEY)


def run(args, env=None, timeout=600):
    result = subprocess.run([str(arg) for arg in args], timeout=timeout,
                            env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, 'Command failed (' + str(result.returncode) + '): ' + str(args[0]))


def validate_audio():
    sample = os.environ.get('SUIYI_TEST_AUDIO')
    require(bool(sample), 'Set SUIYI_TEST_AUDIO to a permitted English PCM WAV before full validation')
    audio = Path(sample).resolve()
    require(audio.is_file(), 'SUIYI_TEST_AUDIO does not name a file')
    with wave.open(str(audio), 'rb') as stream:
        require(stream.getcomptype() == 'NONE' and stream.getframerate() == 16000,
                'Speech fixture must be uncompressed 16 kHz PCM WAV')
        require(stream.getnchannels() in (1, 2) and stream.getnframes() > 0,
                'Speech fixture must contain mono or stereo audio')
    return audio


def validate_payload(expected):
    files = [p for p in TARGET.rglob('*') if p.is_file()]
    actual = {p.relative_to(TARGET).as_posix() for p in files}
    generated = {'suiyi-install-manifest.txt', '安装后空间与更新说明.txt'}
    require(actual == set(expected) | generated,
            'Payload file list differs: missing=' + repr(sorted(set(expected) - actual)) +
            '; extra=' + repr(sorted(actual - set(expected) - generated)))
    for name, row in expected.items():
        path = safe_child(TARGET, name)
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Payload hash differs: ' + name)
    manifest = (TARGET / 'suiyi-install-manifest.txt').read_text(encoding='utf-8-sig').splitlines()
    require(manifest and manifest[0] == IDENTITY, 'Installer ownership marker differs')
    names = [name.replace('\\', '/') for name in manifest[1:]]
    require(set(names) == set(expected) | {'安装后空间与更新说明.txt'}, 'Ownership manifest differs')
    for name in names:
        require(safe_child(TARGET, name).is_file(), 'Owned file missing: ' + name)
    require(not (TARGET / 'models/whisper-turbo').exists(), 'Optional turbo was bundled')
    blocked = []
    for name in actual:
        parts = name.lower().split('/')
        filename = parts[-1]
        if any(part in ('av', 'av.libs') for part in parts):
            blocked.append(name)
        if Path(filename).suffix in ('.dll', '.pyd', '.exe') and any(
            word in filename for word in ('avcodec', 'avformat', 'avutil', 'swresample', 'ffmpeg', 'x264', 'x265')
        ):
            blocked.append(name)
        if Path(filename).suffix in ('.png', '.jpg', '.jpeg', '.webp') and any(
            word in filename for word in ('vertin', 'ryuko')
        ):
            blocked.append(name)
    require(not blocked, 'Unwanted public-package assets: ' + repr(blocked))
    for name in LICENSES:
        require((TARGET / name).is_file() and (TARGET / name).stat().st_size > 0,
                'Required license/source material missing: ' + name)
    matched_licenses = set(LICENSES)
    for pattern in LICENSE_GLOBS:
        matches = [p for p in TARGET.glob(pattern) if p.is_file() and p.stat().st_size > 0]
        require(bool(matches), 'Required license/source pattern missing: ' + pattern)
        matched_licenses.update(p.relative_to(TARGET).as_posix() for p in matches)
    notices = json.loads((TARGET / 'third_party/notice-manifest.json').read_text(encoding='utf-8'))
    require(bool(notices.get('files')), 'Third-party notice manifest has no file records')
    for row in notices['files']:
        path = safe_child(TARGET / 'third_party', row['file'])
        require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Third-party notice/source hash differs: ' + row['file'])
    for name in ('_internal/pystray/__init__.py', '_internal/pystray/_win32.py',
                 '_internal/shapely/__init__.py'):
        require((TARGET / name).is_file(), 'Replaceable library source missing: ' + name)
    require(bool(list((TARGET / '_internal/shapely.libs').glob('geos*.dll'))),
            'Replaceable GEOS library missing')
    require(not (TARGET / '_internal/ctranslate2/cudnn64_9.dll').exists(),
            'Old duplicate CTranslate2 cuDNN library was bundled')

    # Inspect the frozen module table too: a module hidden inside PYZ has no
    # separate on-disk filename. No importing or execution of bundled code.
    from PyInstaller.archive.readers import CArchiveReader
    executable = CArchiveReader(str(TARGET / 'Suiyi.exe'))
    pyz_names = [name for name, entry in executable.toc.items() if entry[-1] == 'z']
    require(bool(pyz_names), 'Frozen Python module table was not found')
    frozen_modules = set()
    for name in pyz_names:
        frozen_modules.update(executable.open_embedded_archive(name).toc)
    require(not any(name == 'av' or name.startswith('av.') for name in frozen_modules),
            'PyAV remains in the frozen module archive')
    require(not any(name == 'pystray' or name.startswith('pystray.') for name in frozen_modules),
            'pystray source replacement would be shadowed by frozen modules')
    return dict(files_sha256_verified=len(expected), license_materials_verified=len(matched_licenses),
                notice_manifest_hashes_verified=len(notices['files']),
                frozen_modules_inspected=len(frozen_modules), character_art_absent=True,
                pyav_ffmpeg_codecs_absent=True, turbo_optional=True)


def self_test(flag, name, env):
    output = WORK / (name + '-test.json')
    require(not output.exists(), 'Old test output exists: ' + str(output))
    run([TARGET / 'Suiyi.exe', flag, output], env=env)
    data = json.loads(output.read_text(encoding='utf-8'))
    require(data.get('ok') is True, 'Runtime test failed: ' + name)
    return data


def replacement_test(env):
    source = safe_child(TARGET, '_internal/pystray/__init__.py')
    original = source.read_bytes()
    expected_hash = sha(source)
    probe = 'public-library-check'
    probe_env = dict(env, SUIYI_REPLACEMENT_PROBE=probe)
    try:
        source.write_bytes(original + b"\n_suiyi_replacement_probe = 'public-library-check'\n")
        result = self_test('--self-test-libraries', 'replaceable-libraries', probe_env)
        require(result.get('replacement_probe') == probe, 'Replacement library was not loaded')
        require(result.get('pyav_loaded') is False and result.get('no_capture') is True,
                'Library check did not confirm capture-free PCM runtime')
        geos_paths = [Path(name).resolve() for name in result.get('geos_loaded_paths', [])]
        require(len(geos_paths) >= 2 and all(
            path.is_relative_to((TARGET / '_internal/shapely.libs').resolve()) for path in geos_paths
        ), 'GEOS did not load from the replaceable installed library directory')
    finally:
        source.write_bytes(original)
        require(sha(source) == expected_hash, 'Library source was not restored exactly')
    return result


def validate_offline_result(result, device):
    offline = result['checks']
    require(offline.get('loopback_not_captured') is True, 'Self-test did not confirm capture-free validation')
    require(offline.get('network_blocked') is True, 'Offline networking guard was not verified')
    require(offline.get('turbo', {}).get('installed') is False, 'Turbo was not confirmed optional')
    require('small.en' in offline and 'base' in offline, 'Speech tests were skipped')
    require(offline.get('wake_transcription_preserved') is True, 'Wake transcription was not preserved')
    if device != 'auto':
        require(all(offline[name]['device'] == device for name in ('small.en', 'base')),
                'Requested recognition device was not actually used: ' + device)
    for name in ('small.en', 'base'):
        if offline[name]['device'] == 'cuda':
            require(bool(offline[name].get('nvidia_libraries')),
                    'GPU library load verification was missing: ' + name)


def installer_unit_tests():
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    output = WORK / 'PublicInstallerTests.exe'
    run([compiler, '/nologo', '/target:exe', '/platform:x64', '/optimize+',
         '/main:PublicInstallerTests', '/out:' + str(output),
         '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
         '/reference:System.IO.Compression.dll', '/reference:Microsoft.CSharp.dll',
         ROOT / 'packaging/Setup.cs', ROOT / 'packaging/PublicInstallerTests.cs'])
    run([output])
    return True


def allocated_bytes():
    measure = ctypes.WinDLL('kernel32', use_last_error=True).GetCompressedFileSizeW
    measure.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    measure.restype = ctypes.c_uint32
    total = 0
    for path in TARGET.rglob('*'):
        if not path.is_file():
            continue
        high = ctypes.c_uint32()
        ctypes.set_last_error(0)
        low = measure(str(path), ctypes.byref(high))
        if low == 0xffffffff and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        total += (high.value << 32) | low
    return total


def main():
    require(os.name == 'nt', 'Public installer validation requires Windows')
    safe_child(ROOT, TARGET.relative_to(ROOT))
    require(not TARGET.exists(), 'Fresh validation requires a new directory; no existing installation is removed')
    require(INSTALLER.is_file(), 'Build the public installer first')
    require(WORK.is_dir(), 'Build metadata is missing')
    sample = validate_audio()
    device = os.environ.get('SUIYI_TEST_DEVICE', 'cuda')
    require(device in ('cpu', 'cuda', 'auto'), 'Unsupported SUIYI_TEST_DEVICE')
    expected = json.loads((WORK / 'file-hashes.json').read_text(encoding='utf-8'))
    package = json.loads((WORK / 'package.json').read_text(encoding='utf-8'))
    require(sha(INSTALLER) == package['sha256'] and INSTALLER.stat().st_size == package['bytes'],
            'Installer does not match build metadata')
    before = registration()
    preferences = Path(os.environ['LOCALAPPDATA']) / 'Suiyi/settings.json'
    preference_before = sha(preferences) if preferences.exists() else None
    report = dict(ok=False, standalone=True, checks={}, started_unix=time.time())
    try:
        report['installer_file_safety_tests'] = installer_unit_tests()
        # The installer uses its non-registering extraction path. Executable
        # self-tests also receive a separate per-user data directory.
        isolated_user = WORK / 'isolated-user-data'
        isolated_user.mkdir(exist_ok=True)
        env = dict(os.environ, LOCALAPPDATA=str(isolated_user),
                   SUIYI_TEST_AUDIO=str(sample), SUIYI_TEST_DEVICE=device)
        run([INSTALLER, '/quiet', '/verify-extract', '/dir=' + str(TARGET)], env=env, timeout=1200)
        report.update(validate_payload(expected))
        print('Fresh public payload verified; checking offline functions and replaceable libraries', flush=True)
        report['checks']['libraries'] = replacement_test(env)
        for flag, name in (('--self-test-workspace', 'workspace'),
                           ('--self-test-screen', 'screen'),
                           ('--self-test-reading', 'reading'),
                           ('--self-test-offline', 'offline')):
            report['checks'][name] = self_test(flag, name, env)
        validate_offline_result(report['checks']['offline'], device)
        print('Primary recognition path passed; checking explicit CPU recognition', flush=True)
        report['checks']['offline_cpu'] = self_test(
            '--self-test-offline', 'offline-cpu', dict(env, SUIYI_TEST_DEVICE='cpu'))
        validate_offline_result(report['checks']['offline_cpu'], 'cpu')
        report['cpu_checked'] = True
        report['fresh_install_on_disk_bytes'] = allocated_bytes()
        report['speech_device_requested'] = device
        report['ok'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
        raise
    finally:
        report['registration_unchanged'] = registration() == before
        report['settings_unchanged'] = (sha(preferences) if preferences.exists() else None) == preference_before
        report['ok'] = report['ok'] and report['registration_unchanged'] and report['settings_unchanged']
        report['finished_unix'] = time.time()
        (WORK / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        require(report['registration_unchanged'], 'Live installation registration changed')
        require(report['settings_unchanged'], 'Live preferences changed')
    package.update(installation_verified=True, fresh_install_on_disk_bytes=report['fresh_install_on_disk_bytes'],
                   public_assets_verified=True, replaceable_libraries_verified=True,
                   speech_device_verified=device, cpu_checked=report['cpu_checked'],
                   live_installation_unchanged=True)
    (WORK / 'package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'checks'}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
