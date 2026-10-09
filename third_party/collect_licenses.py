"""Collect redistributed component notices and matching LGPL source archives.

Run only when preparing a distribution. Network requests fetch public files.
No credentials or paid services are used.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import zipfile
from io import BytesIO
import base64
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent


def fetch(url: str) -> bytes:
    if url.startswith("https://raw.githubusercontent.com/"):
        owner, repo, revision, path = url.split("raw.githubusercontent.com/", 1)[1].split("/", 3)
        api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={urllib.parse.quote(revision)}"
        meta = json.loads(fetch(api))
        data = base64.b64decode(meta["content"])
        blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if blob != meta["sha"]:
            raise RuntimeError("GitHub blob checksum mismatch")
        return data
    request = urllib.request.Request(url, headers={"User-Agent": "Suiyi-release-notices/0.5"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def save(name: str, url: str) -> dict:
    data = fetch(url)
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"file": name, "source": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def local_copy(name: str, path: Path, source: str) -> dict:
    data = path.read_bytes()
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"file": name, "source": source, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def verify_mpl_sources(site: Path) -> None:
    records = {}
    for package, version in [("certifi", "2026.7.22"), ("tqdm", "4.70.1")]:
        verified = []
        with tarfile.open(ROOT / "sources" / f"{package}-{version}.tar.gz") as archive:
            for path in sorted((site / package).rglob("*")):
                if not path.is_file() or path.suffix not in (".py", ".pem"):
                    continue
                relative = path.relative_to(site / package).as_posix()
                member = archive.extractfile(f"{package}-{version}/{package}/{relative}")
                if member is None or member.read().replace(b"\r\n", b"\n") != path.read_bytes().replace(b"\r\n", b"\n"):
                    raise RuntimeError("MPL source differs: " + package + "/" + relative)
                verified.append(relative)
        records[package] = {"version": version, "verified_files": verified, "normalization": "CRLF to LF only", "unmodified": True}
    (ROOT / "mpl/source-verification.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--python-root", type=Path, default=Path(sys.base_prefix))
    args = parser.parse_args()
    rows = []
    local = {
        "onnxruntime/LICENSE": "onnxruntime/LICENSE",
        "onnxruntime/ThirdPartyNotices.txt": "onnxruntime/ThirdPartyNotices.txt",
        "pystray/COPYING": "pystray-0.19.5.dist-info/COPYING",
        "pystray/COPYING.LGPL": "pystray-0.19.5.dist-info/COPYING.LGPL",
        "shapely/LICENSE_GEOS": "shapely-2.1.2.dist-info/licenses/LICENSE_GEOS",
        "shapely/LICENSE.txt": "shapely-2.1.2.dist-info/licenses/LICENSE.txt",
        "shapely/LICENSE_win32": "shapely-2.1.2.dist-info/licenses/LICENSE_win32",
        "faster-whisper/LICENSE": "faster_whisper-1.2.1.dist-info/LICENSE",
        "nvidia/cuBLAS-wheel-License.txt": "nvidia_cublas_cu12-12.9.2.10.dist-info/licenses/License.txt",
        "nvidia/NVRTC-wheel-License.txt": "nvidia_cuda_nvrtc_cu12-12.9.86.dist-info/licenses/License.txt",
        "nvidia/cuDNN-wheel-License.txt": "nvidia_cudnn_cu12-9.27.0.42.dist-info/licenses/License.txt",
    }
    for name, source in local.items():
        data = (args.site / source).read_bytes()
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({"file": name, "source": "installed-wheel:" + source, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    urls = {
        "nvidia/CUDA-12.9.1-EULA.html": "https://docs.nvidia.com/cuda/archive/12.9.1/eula/index.html",
        "nvidia/cuDNN-9.27.0-EULA.html": "https://docs.nvidia.com/deeplearning/cudnn/backend/v9.27.0/reference/eula.html",
        "nvidia/cuDNN-9.27.0-Acknowledgements.html": "https://docs.nvidia.com/deeplearning/cudnn/backend/v9.27.0/reference/acknowledgements.html",
        "ctranslate2/LICENSE": "https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.2/LICENSE",
        "sentencepiece/LICENSE": "https://raw.githubusercontent.com/google/sentencepiece/v0.2.2/LICENSE",
        "rapidocr/LICENSE": "https://raw.githubusercontent.com/RapidAI/RapidOCR/v1.4.4/LICENSE",
        "whisper/LICENSE": "https://raw.githubusercontent.com/openai/whisper/v20250625/LICENSE",
        "silero/LICENSE": "https://raw.githubusercontent.com/snakers4/silero-vad/v5.1/LICENSE",
        "sources/geos-3.13.1.tar.bz2": "https://download.osgeo.org/geos/geos-3.13.1.tar.bz2",
        "sources/pystray-0.19.5.zip": "https://codeload.github.com/moses-palmer/pystray/zip/refs/tags/v0.19.5",
        "tcl-tk/tcl-8.6.15-license.terms": "https://raw.githubusercontent.com/tcltk/tcl/core-8-6-15/license.terms",
        "tcl-tk/tk-8.6.15-license.terms": "https://raw.githubusercontent.com/tcltk/tk/core-8-6-15/license.terms",
        "flatbuffers/LICENSE": "https://raw.githubusercontent.com/google/flatbuffers/v25.12.19/LICENSE",
        "tokenizers/LICENSE": "https://raw.githubusercontent.com/huggingface/tokenizers/v0.23.2/LICENSE",
        "tqdm/LICENCE": "https://raw.githubusercontent.com/tqdm/tqdm/v4.70.1/LICENCE",
        "argos/CC-BY-4.0.txt": "https://creativecommons.org/licenses/by/4.0/legalcode.txt",
        "mpl/MPL-2.0.txt": "https://www.mozilla.org/media/MPL/2.0/index.f75d2927d3c1.txt",
        "ctranslate2/upstream-windows-build.sh": "https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.2/python/tools/prepare_build_environment_windows.sh",
        "onednn/LICENSE": "https://raw.githubusercontent.com/oneapi-src/oneDNN/v3.1.1/LICENSE",
        "onednn/THIRD-PARTY-PROGRAMS": "https://raw.githubusercontent.com/oneapi-src/oneDNN/v3.1.1/THIRD-PARTY-PROGRAMS",
    }
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(save, name, url): name for name, url in urls.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                row = future.result()
                rows.append(row)
                print("OK", name, row["bytes"], flush=True)
            except Exception as exc:
                errors.append({"file": name, "error": str(exc)})
                print("FAIL", name, type(exc).__name__, flush=True)
    for package, version in [("shapely", "2.1.2"), ("tqdm", "4.70.1"), ("certifi", "2026.7.22")]:
        metadata = json.loads(fetch(f"https://pypi.org/pypi/{package}/{version}/json"))
        artifact = next(item for item in metadata["urls"] if item["packagetype"] == "sdist")
        row = save("sources/" + artifact["filename"], artifact["url"])
        if row["sha256"] != artifact["digests"]["sha256"]:
            raise RuntimeError("Source archive hash mismatch: " + package)
        row["pypi_sha256"] = artifact["digests"]["sha256"]
        rows.append(row)
        print("OK", row["file"], row["bytes"], flush=True)
    metadata = json.loads(fetch("https://pypi.org/pypi/intel-openmp/2025.3.0/json"))
    artifact = next(item for item in metadata["urls"] if "win_amd64" in item["filename"])
    wheel_bytes = fetch(artifact["url"])
    if hashlib.sha256(wheel_bytes).hexdigest() != artifact["digests"]["sha256"]:
        raise RuntimeError("Intel OpenMP wheel checksum mismatch")
    with zipfile.ZipFile(BytesIO(wheel_bytes)) as wheel:
        dll_name = next(name for name in wheel.namelist() if name.endswith("/libiomp5md.dll"))
        matching = wheel.read(dll_name) == (args.site / "ctranslate2/libiomp5md.dll").read_bytes()
        if not matching:
            raise RuntimeError("Intel OpenMP runtime differs from CTranslate2")
        notices = []
        for name in wheel.namelist():
            if not name.endswith("/") and any(term in Path(name).name.lower() for term in ("license", "third-party", "third_party", "notice")):
                target = ROOT / "intel" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                data = wheel.read(name)
                target.write_bytes(data)
                notices.append(target.relative_to(ROOT).as_posix())
                rows.append({"file": target.relative_to(ROOT).as_posix(), "source": artifact["url"] + "#" + name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (ROOT / "intel/runtime-verification.json").write_text(json.dumps({"package": artifact["filename"], "source": artifact["url"], "wheel_sha256": artifact["digests"]["sha256"], "ctranslate2_libiomp5md_dll_sha256": hashlib.sha256((args.site / "ctranslate2/libiomp5md.dll").read_bytes()).hexdigest(), "byte_identical": matching, "notices": notices}, indent=2) + "\n", encoding="utf-8")
    rows.append(local_copy("python/LICENSE-3.12.10.txt", args.python_root / "LICENSE.txt", "Python-3.12.10-installed:LICENSE.txt"))
    for info in sorted(args.site.glob("*.dist-info")):
        if info.name.startswith(("av-", "pip-", "setuptools-")):
            continue
        for source in sorted(info.rglob("*")):
            if source.is_file() and source.suffix != ".pyc" and any(word in source.name.lower() for word in ("license", "licence", "copying", "notice", "copyright")):
                relative = source.relative_to(info)
                rows.append(local_copy("wheels/" + info.name + "/" + relative.as_posix(), source, "installed-wheel:" + info.name + "/" + relative.as_posix()))
    archive = ROOT / "sources/pystray-0.19.5.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as package:
            verified = []
            for path in sorted((args.site / "pystray").rglob("*.py")):
                relative = path.relative_to(args.site / "pystray").as_posix()
                archived = package.read("pystray-0.19.5/lib/pystray/" + relative)
                if archived.replace(b"\r\n", b"\n") != path.read_bytes().replace(b"\r\n", b"\n"):
                    raise RuntimeError("pystray source differs: " + relative)
                verified.append(relative)
        (ROOT / "pystray/source-verification.json").write_text(json.dumps({"version": "0.19.5", "archive": "../sources/pystray-0.19.5.zip", "verified_python_files": verified, "normalization": "CRLF to LF only", "unmodified": True}, indent=2) + "\n", encoding="utf-8")
    dlls = []
    for component, version in [("cublas", "12.9.2.10"), ("cuda_nvrtc", "12.9.86"), ("cudnn", "9.27.0.42")]:
        for path in sorted((args.site / "nvidia" / component / "bin").glob("*.dll")):
            dlls.append({"component": component, "package_version": version, "file": path.name,
                         "bytes": path.stat().st_size, "sha256": hashlib.file_digest(path.open("rb"), "sha256").hexdigest()})
    (ROOT / "nvidia" / "dll-inventory.json").write_text(json.dumps(dlls, indent=2) + "\n", encoding="utf-8")
    verify_mpl_sources(args.site)
    if (ROOT / 'rapidocr/english-model.json').is_file():
        rows.append(local_copy('rapidocr/english-model.json', ROOT / 'rapidocr/english-model.json',
                               'verification:fixed-upstream-English-OCR-model'))
    for name, source in [
        ("intel/runtime-verification.json", "verification:official-intel-wheel-versus-installed-ctranslate2"),
        ("mpl/source-verification.json", "verification:PyPI-source-versus-installed-files"),
        ("pystray/source-verification.json", "verification:upstream-tag-versus-installed-wheel"),
    ]:
        rows.append(local_copy(name, ROOT / name, source))
    (ROOT / "notice-manifest.json").write_text(json.dumps({"checked": "2026-10-08", "github_transport": "Official GitHub contents API with Git blob SHA1 verification for raw.githubusercontent.com sources", "files": sorted(rows, key=lambda row: row["file"]), "errors": errors}, indent=2) + "\n", encoding="utf-8")
    print("RESULT", len(rows), "files,", len(errors), "errors", flush=True)


if __name__ == "__main__":
    main()
