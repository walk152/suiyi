# 公开版音频依赖说明

实时识别直接把系统音频采集得到的 16 kHz NumPy 数组交给 faster-whisper，回听使用标准 PCM。公开版不需要压缩音视频文件解码、视频转码或编码器，因此不分发 PyAV、FFmpeg、x264、x265。

`public_audio.py` 在导入 faster-whisper 前注册 `faster_whisper.audio` 兼容模块，提供特征补齐/裁剪及自检使用的 PCM WAV 读取。没有修改已安装的 faster-whisper 文件，其原有 MIT 许可及署名继续保留。源代码入口和 PyInstaller 启动钩子使用同一适配器。

此适配器只读取单声道或双声道的 8/16/24/32 位整数 PCM WAV，采样率必须与调用方要求一致。默认要求 16 kHz。不支持压缩 WAV、MP3、AAC、视频文件、编码或重采样；这些输入会明确报错，不会偷偷改变采样率或用占位结果代替识别。实时数组输入仍使用原模型、特征提取和识别流程。

构建时将 `tools/public_audio_hook.py` 加入 PyInstaller `runtime_hooks`，排除 `av` 模块及其动态库，并从最终收集结果排除 `opencv_videoio_ffmpeg*.dll`。RapidOCR 只使用 OpenCV 静态图像处理函数，不使用视频读取或写入。最终包仍需检查模块和动态库清单，并运行 OCR、数组识别和 WAV 自检。

维护时若升级 faster-whisper，须重新核对该版本对 `audio` 模块的接口要求，运行 `python -m unittest test_public_audio` 及完整离线自检。不能仅依赖启动成功判断识别正常。

上游实现：

- [faster-whisper v1.2.1 的音频模块](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/audio.py)
- [faster-whisper v1.2.1 的识别入口](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
- [OpenCV 4.11 的 FFmpeg 加载器](https://github.com/opencv/opencv/blob/4.11.0/modules/videoio/src/cap_ffmpeg.cpp)

这些依赖的各自许可见第三方说明；项目主许可证不改变其原有许可。
