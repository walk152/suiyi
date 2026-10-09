# 第三方组件、模型与数据

核对日期：2026-10-08。第三方库、模型、数据及其许可不受项目非商业条款重新授权。这里是材料索引；适用条件以随附完整许可证为准。

| 组件 | 许可与随附位置 |
|---|---|
| faster-whisper 1.2.1 / CTranslate2 4.8.2 | MIT；`third_party/faster-whisper/`、`ctranslate2/` |
| RapidOCR 1.4.4 / PaddleOCR 转换权重 | Apache-2.0；`third_party/rapidocr/`，英文模型来源和哈希见 `english-model.json` |
| ONNX Runtime 1.30.0 | MIT 及 ThirdPartyNotices；`third_party/onnxruntime/` |
| SentencePiece 0.2.2 | Apache-2.0；`third_party/sentencepiece/` |
| SoundCard 0.4.6 / MSS 10.2.0 | BSD-3-Clause / MIT；`third_party/wheels/` |
| pystray 0.19.5 | LGPL-3.0；完整许可、对应源码及外置库替换说明 |
| Shapely 2.1.2 / GEOS 3.13.1 | BSD-3-Clause / LGPL-2.1；完整源码与可替换 DLL |
| OpenCV Python 4.11.0.86 | 保留 wheel 完整 LICENSE 与第三方声明；独立 FFmpeg 插件未打包 |
| NumPy 1.26.4 / Pillow 12.3.0 | BSD-3-Clause / MIT-CMU 及 wheel 附加声明 |
| Python 3.12.10 / Tcl-Tk 8.6.15 | Windows Python 完整 LICENSE 及 Tcl/Tk 对应 tag 的 license.terms |
| NVIDIA cuBLAS / NVRTC / cuDNN | 12.9.2.10 / 12.9.86 / 9.27.0.42；版本对应的 SDK 条款、DLL 清单位于 `third_party/nvidia/` |
| Intel OpenMP 2025.3.0 / oneDNN 3.1.1 | Intel 条款及 Apache-2.0/附加声明；`third_party/intel/`、`onednn/` |
| certifi / tqdm | 原许可、MPL 文本及对应源码包，见 `third_party/mpl/` 与 `sources/` |
| PyInstaller | 原 GPL 许可加程序分发例外；分发例外不代替其他依赖的条件 |

其他依赖的原许可证也保留在 `third_party/wheels/` 及运行包 `licenses/`。`third_party/notice-manifest.json` 记录来源和 SHA-256；详细来源、版本对应和库替换步骤见 [REDISTRIBUTION.md](REDISTRIBUTION.md)。PyAV 和其编解码依赖不进入此公开二进制。

## 模型

[OpenAI Whisper](https://github.com/openai/whisper) 原始代码与权重采用 MIT，保留原许可。本项目使用 Systran 转换的 base、small.en；small.en revision 为 `d1d751a5f8271d482d14ca55d9e2deeebbae577f`。可选 Turbo 源自 mobiuslabsgmbh（现 dropbox-dash）转换仓库，revision 为 `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`。所有文件按 `models-lock.json` 校验。Silero VAD 保留其 MIT 许可。

Argos 的 `translate-en_zh-1_9`、`translate-zh_en-1_9` 使用 OPUS-MT，署名 **Jörg Tiedemann、Santhosh Thottingal**：*OPUS-MT — Building open translation services for the World*, EAMT 2020, Lisbon, Portugal。采用 CC BY 4.0，两个原始模型 README 与完整许可位于 `third_party/argos/`。本项目使用 Argos 转换权重，在运行时量化推理，未重新训练。

轻量英文 OCR 模型来自 [RapidAI 官方模型配置](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)，按固定 v3.9.2 下载地址及上游 SHA-256 校验，保留 PaddleOCR/RapidOCR 的 Apache-2.0 署名。权重在安装器中提供，不在源码 ZIP 中提供。

## 词典与验证数据

[ECDICT](https://github.com/skywind3000/ECDICT) 采用 MIT，原文为 `Copyright (c) 2025 Linwei`。CSV blob 为 `c4ade63ea08cf39d9c3475e96929036d64d94c94`，本地转换为带词形索引的 SQLite；许可与来源在 `third_party/ecdict/`。安装器含词库，源码 ZIP 不含数据库。

语音检查使用 PolyAI/minds14 的 en-GB `PAY_BILL/60268fc4dc3604f481bcb89c.wav`，来源标示 CC BY 4.0，转换为 16 kHz PCM 仅用于测试。该音频不随安装器或源码分发。

公开版不含角色插画、完整游戏剧情或游戏配音。`names1999.json` 仅整理名称与别名辅助辨音，保留来源；不主张对名称事实的排他权，本项目不是官方或获授权产品。
