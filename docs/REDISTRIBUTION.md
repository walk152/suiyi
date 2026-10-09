# 公开版再分发材料与库替换

核对日期：2026-10-08。适用于本目录构建的随译 v0.5 公开版，不代替任何第三方许可证原文。

## 授权范围

项目可授权代码适用根目录 `LICENSE` 的 PolyForm Noncommercial 1.0.0。第三方组件、模型和数据保持各自条款，项目非商业条件不覆盖其独立副本。安装器提供 [使用与第三方许可说明](../third_party/END_USER_TERMS.zh-CN.txt)，同时附带许可全文、来源与源码。

本版使用系统音频采集得到的 PCM 数据。PyAV、其 FFmpeg/x264/x265 编解码依赖及 OpenCV 的独立 FFmpeg 视频插件不进入公开发行包；原始 opencv-python 的完整许可文件仍保留，没有因插件剔除而删改许可内容。

## LGPL 库及可替换机制

程序使用 **pystray 0.19.5（LGPL-3.0）**，以及 **Shapely 2.1.2（BSD-3-Clause）** 动态链接的 **GEOS 3.13.1（LGPL-2.1）**。允许依各库许可证修改、重新编译和替换库，并允许为调试这类修改而进行必要的逆向工程，不受本项目非商业条件的额外限制。

安装目录中的位置：

- `_internal/pystray/`：未压入程序内部的 Python 库源码。
- `_internal/shapely/`：Shapely Python 模块和扩展模块。
- `_internal/shapely.libs/`：GEOS 和 GEOS C 接口 DLL；实际文件名以目录及发行清单为准。
- `_internal/third_party/sources/`：对应版本的完整上游源码压缩包。
- `_internal/third_party/pystray/`、`_internal/third_party/shapely/`：GPL/LGPL 和库许可原文。

替换步骤：退出随译，备份需替换的库目录；编辑 pystray 的 `.py` 文件，或使用下列来源重建与原接口兼容的 x64 GEOS DLL；将替代文件置于原路径并保持接口及文件名兼容，再启动程序。无需修改或重新签署主程序。修改库时应遵守该库的许可证，后续覆盖安装可能恢复发行版本，请另行保留修改。

GEOS 重建需 Visual Studio C++ 工具链和 CMake。在随附源码中使用 `BUILD_SHARED_LIBS=ON` 构建 x64 Release DLL；Shapely 需要 GEOS C 接口，两个 DLL 应来自同一版本/构建。上游完整源码中的构建文件与说明随包提供。若改变了 DLL 文件名或接口，则需相应重建 Shapely；直接替换采用接口兼容版本。

| 源码包 | 来源 | 版本依据 |
|---|---|---|
| `pystray-0.19.5.zip` | [moses-palmer/pystray v0.19.5](https://github.com/moses-palmer/pystray/tree/v0.19.5) | 已将 wheel 中 13 个 Python 文件与 tag 内 `lib/pystray` 文件逐个核对，仅归一化换行，一致；记录见 `third_party/pystray/source-verification.json`。 |
| `shapely-2.1.2.tar.gz` | [Shapely 2.1.2 on PyPI](https://pypi.org/project/shapely/2.1.2/) | 官方 sdist，SHA256 与 PyPI 元数据一致。 |
| `geos-3.13.1.tar.bz2` | [OSGeo GEOS 3.13.1](https://download.osgeo.org/geos/geos-3.13.1.tar.bz2) | Shapely wheel 使用 GEOS 3.13.1；包含构建文件、许可及原始源码。 |

源码包的字节数、下载地址及 SHA256 在 `third_party/notice-manifest.json` 中。源码包内的原始许可证与署名全部保留，不把这些包重新授权为项目非商业许可。

## GPU 运行库

cuBLAS `12.9.2.10`、NVRTC `12.9.86` 来自 NVIDIA 对应 PyPI wheel，采用 [CUDA 12.9.1 SDK 协议与附件 A](https://docs.nvidia.com/cuda/archive/12.9.1/eula/index.html)。附件列出 cuBLAS、cuBLASLt、nvBLAS、NVRTC 和 NVRTC-builtins DLL 及其版本化文件名变体。

cuDNN `9.27.0.42` 来自 NVIDIA 对应 PyPI wheel；[cuDNN 9.27.0 协议补充条款](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.27.0/reference/eula.html) 将运行时 `.dll` 列为可分发文件。wheel 内保留的许可证存在旧版本 DLL 文件名，故一并附上该精确文档版本的完整协议和 [Acknowledgements](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.27.0/reference/acknowledgements.html)，不删除 wheel 原文。

`third_party/nvidia/dll-inventory.json` 列出对应 wheel 的 DLL 名称、包版本、大小及 SHA256。最终是否进入安装包，以发行包文件清单为准。GPU DLL 为随译的本地语音识别提供加速，不作为独立 SDK 产品或系统级组件安装；它们不受本项目许可证重新授权。终端使用条件与随附 SDK 原文保持一致。

## CPU 运行库和 MPL 文件

CTranslate2 4.8.2 的 Windows 构建使用 Intel OpenMP 运行库和静态链接的 oneDNN 3.1.1，构建依据保存在 `third_party/ctranslate2/upstream-windows-build.sh`。本版 `libiomp5md.dll` 已与 [Intel 发布的 intel-openmp 2025.3.0 Windows wheel](https://pypi.org/project/intel-openmp/2025.3.0/) 逐字节比对，一致；wheel 的 SHA256、DLL 哈希及对应许可路径见 `third_party/intel/runtime-verification.json`。

- Intel wheel 的 Developer Tools EULA（2024 年 8 月版）及 `third-party-programs.txt` 完整保存在 `third_party/intel/`，不将此专有运行库重新授权为项目非商业许可。终端许可说明包含对该运行库的必要条件，并明确不限制其他开放组件原有权利。
- [oneDNN v3.1.1](https://github.com/uxlfoundation/oneDNN/tree/v3.1.1) 的 Apache 2.0 许可及完整 `THIRD-PARTY-PROGRAMS` 保存在 `third_party/onednn/`。
- certifi 2026.7.22、tqdm 4.70.1 对应的完整 PyPI 源码包保存在 `third_party/sources/`，下载哈希已与 PyPI 元数据核对。受 MPL 2.0 约束的文件按其原许可提供，未施加项目非商业限制；完整 MPL 原文位于 `third_party/mpl/MPL-2.0.txt`，各包的原始许可同时保留。

## 其余通知

- Python 3.12.10：`third_party/python/LICENSE-3.12.10.txt`，包含该 Windows Python 发行版附带的完整许可与额外声明。
- Tcl/Tk 8.6.15：`third_party/tcl-tk/`，使用对应上游 tag 的完整 `license.terms`。
- ONNX Runtime：`third_party/onnxruntime/`，包含包内 LICENSE 与 ThirdPartyNotices。
- Wheel 许可：`third_party/wheels/` 与运行包 `licenses/`。完整保留 NumPy、Pillow、OpenCV 等二进制发行包随附的附加声明。
- CTranslate2、RapidOCR、SentencePiece、Whisper、Silero、FlatBuffers、Tokenizers 的完整许可分别位于同名目录。
- 两个 Argos 翻译模型保留 OPUS 作者 Jörg Tiedemann、Santhosh Thottingal 的署名及模型 README，采用 CC BY 4.0；完整许可为 `third_party/argos/CC-BY-4.0.txt`。本项目使用 Argos 转换权重并在运行时量化推理，未重新训练。
- ECDICT 保留原 MIT 许可、版权人和 CSV blob 记录；SQLite 只是本地格式转换。

`third_party/notice-manifest.json` 是许可与源码材料的校验清单；安装包最终文件哈希由构建流程另外生成。第三方文本可能包含上游作者、网址和原始商标，保留它们不代表上游为随译背书。
