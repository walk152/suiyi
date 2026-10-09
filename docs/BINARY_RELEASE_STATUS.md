# v0.5 公开完整安装版

更新：2026-10-08。公开安装器为 **Suiyi-v0.5-Public-Setup.exe**，内部版本 `0.5-public.1`。可独立安装，包含基础模型、词库、CPU/GPU 运行支持；Turbo 继续选装。

## 此版处理

- 界面移除角色插画，保留雨幕、赤色配色与文本、词典、回听分区。
- 系统声音直接使用 PCM 数组；不打包 PyAV、FFmpeg、x264/x265 和 OpenCV 的独立视频解码插件。
- pystray 与 Shapely 的 Python 库文件、GEOS DLL 保持外置；附对应源码与替换说明。
- 附 NVIDIA、Intel、Python/Tcl/Tk、运行库、模型及词库的许可与署名；材料清单为 `third_party/notice-manifest.json`。
- 安装器显示许可并要求接受，保留 NTFS 无损压缩和按所有权清单清理废弃程序文件的功能。
- 画面翻译支持自动窗口、鼠标停留 1.5 秒、手动区域；保留文字坐标，按完整句子翻译。疑难英文行使用约 7.7 MB 的轻量英文识别权重复核。

项目可授权部分使用 PolyForm Noncommercial 1.0.0。第三方部分保留各自条款，见 [第三方索引](THIRD_PARTY.md) 与 [源码及库替换](REDISTRIBUTION.md)。

## 验收与下载核对

`packaging/verify_public.py` 使用安装器本身的隔离解压路径，逐文件核对哈希，再检查界面、阅读保护、词典、翻译、CPU/CUDA 语音与可替换库。具体结果记录在发行附件 `release-validation.json`，其中 EXE 哈希应与下载文件一致。检查边界见 [VALIDATION.md](VALIDATION.md)。

旧私人版 `Core-Setup.exe` 和增量 `Update.exe` 不是此次公开产物。请下载带 **Public** 的完整 EXE。没有自动远程上传或联网更新。
