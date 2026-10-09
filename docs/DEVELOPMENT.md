# 开发、测试与本地构建

支持环境：Windows x64、Python 3.12（含 Tk）。推荐使用独立虚拟环境。CPU 依赖锁见 `requirements-lock.txt`；GPU 依赖单列 `requirements-gpu.txt`，打包工具见 `requirements-dev.txt`。

## 准备

按 README 建立环境、安装依赖。只打开界面和运行不涉及数据集的测试，无须下载模型/词库。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tools -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s packaging -p "test_*.py"
.\.venv\Scripts\python.exe app.py --self-test-workspace workspace-self-test.json
```

部分词典集成测试在缺少 `dictionary/ecdict.sqlite3` 时会明确跳过；准备词库后再运行即会覆盖真实词条。Tk 测试需要交互桌面。没有配置自动云端构建、计费服务、缓存或付费 CI。

## 固定资源

`models-lock.json` 记录预期大小和 SHA-256，不接受只因文件存在就复用。small.en、Turbo 固定上游 revision；base/Argos 仍使用固定内容校验的上游 URL，上游替换内容时会失败，需要维护者审查后更新锁文件，不能跳过校验。Turbo 元数据按固定字节生成，与 `turbo_manifest.json` 一致。

```powershell
.\.venv\Scripts\python.exe download_models.py --verify-only
.\.venv\Scripts\python.exe download_models.py --with-turbo --verify-only
```

第一条只校验基础模型；第二条还校验 Turbo。`--models-dir` 和 `--cache-dir` 可以改变准备工具的位置，但应用默认从仓库 `models/` 读取，不会自动跟随准备工具自定义位置。

词库可从上游下载，或以 `tools/prepare_dictionary.py --csv 路径` 从已有 ECDICT CSV 离线构建。固定 Git blob 校验不匹配时停止。下载归档位于 `.cache/`，成功后可清理。

## 完整离线功能自检

先准备核心模型和词库，再运行：

```powershell
.\.venv\Scripts\python.exe app.py --self-test-offline runtime-self-test.json
```

此模式不录制系统声音；使用程序生成的 OCR 文字，验证双向翻译、VAD、词库和本地记忆。为了不随仓库分发来源不明的声音，ASR 样本默认缺省并明确标注跳过。要测 ASR，请自行提供有权使用的清晰英文 WAV，并设置：

```powershell
$env:SUIYI_TEST_AUDIO = (Resolve-Path .\my-test.wav).Path
$env:SUIYI_TEST_DEVICE = 'cpu' # cpu / cuda / auto
.\.venv\Scripts\python.exe app.py --self-test-offline runtime-self-test.json
```

未提供音频时自检通过不能当成“已经验证语音准确率”。CUDA 明确选择时必须真正使用 CUDA 才能通过；auto 允许回退。

## 本地打包（不是公开发行许可核验）

`Suiyi.spec` 和 `packaging/Setup.cs` 为打包源码。先阅读 [二进制发行状态](BINARY_RELEASE_STATUS.md) 与 [第三方替换说明](REDISTRIBUTION.md)。公开构建排除 PyAV/FFmpeg，并使用 `public_audio.py` 的 PCM 适配；源码依赖中的 PyAV 不会进入安装包。

1. 新建干净 Windows 构建环境，安装 `requirements-dev.txt`；需要 GPU 时另装 GPU 依赖。
2. 准备模型和词库，并运行 `python tools/prepare_ocr.py` 下载固定英文 OCR 权重，然后执行 `python -m PyInstaller --clean --noconfirm Suiyi.spec`，得到 `dist/Suiyi`。
3. 完整安装器使用 LZMA SDK 26.03 的 `bin/x64/7zr.exe` 和 `DOC/lzma-sdk.txt`。从 [7-Zip 官方 SDK 页](https://www.7-zip.org/sdk.html)取得对应版本，检查来源后解压到 `packaging/lzma-sdk/`；SDK 未随源码附带。电脑需有 Windows .NET Framework 4 的 x64 C# 编译器，脚本通过 `WINDIR` 寻找。
4. 执行 `python packaging/build_full_v05.py`。`Suiyi-v0.5-Public-Setup.exe` 写到本仓库 `release/`，同名已有产物会拒绝覆盖。完整包包含四个基础模型，Turbo 不进入核心包。构建会嵌入许可条款，并附带第三方许可、对应 LGPL 源码和可替换库。
5. 可选执行 `python packaging/build_turbo_addon.py`，生成经过 manifest 校验的本地 Turbo 扩展。

完整安装器可用 `python packaging/verify_public.py` 在隔离目录解压验证；设置 `SUIYI_TEST_AUDIO` 为获授权的 16 kHz PCM WAV，用于实际语音测试。结果写入被忽略的 `packaging/public-v05/`，不应把含本地路径的原始报告上传 Git。升级不是承诺原子回滚的事务；测试清单及实际结果见发行验证记录。
