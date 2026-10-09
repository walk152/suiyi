# GitHub 发布步骤

普通使用者下载完整安装器；仓库中放源码供学习和修改。本地工具不会登录或自动上传 GitHub。

## 源码仓库

1. 在自己的 GitHub 账号新建仓库，可命名 `suiyi`。简介建议：`本地字幕与听力学习工具，源码公开，非商业使用免费。`
2. 保留现有 PolyForm Noncommercial 1.0.0、NOTICE 及第三方材料，不要在向导中另选 MIT/GPL。
3. 解压 `Suiyi-v0.5-Public-Source.zip`，把里面 `suiyi` 文件夹中的文件作为仓库内容，包括隐藏文件。不是只上传一个 ZIP。
4. 可使用 GitHub Desktop 添加这个解压目录，核对 Changes 后提交、Publish repository，确认账号和 Public 可见性。

源码副本不含模型、数据库、虚拟环境、运行 DLL、个人设置、录音或日志。第三方源码归档与许可需要保留。普通 Git 超过 100 MiB 的文件会被拒绝，模型和安装器放 Releases：[官方说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。

## 可安装版本

在仓库右侧 **Releases → Create a new release** 创建标签 `v0.5-public.1`，标题可用「随译 v0.5 公开版」。附件：

- **Suiyi-v0.5-Public-Setup.exe**：普通用户只需这个，完整离线安装，无需 Python 或旧版。
- **Suiyi-v0.5-Public-Source.zip**：对应源码与第三方材料快照。
- **SHA256SUMS.txt**：下载校验值。
- **release-validation.json**：匹配此 EXE 的验证与占用记录。
- 可选 **Suiyi-Turbo-v1.suiyimodel**：增强模型，不属于运行必需项。

每个 Release 附件须小于 2 GiB：[官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。上传前确认验证记录通过且哈希匹配。

说明 Windows x64、免费非商业、本地运行、Turbo 选装和已知限制。安装器没有购买签名证书，Windows 可能显示未知发布者；提供校验值帮助核对，不要求关闭系统防护。旧私人版 Core 或增量 Update 包不作为此次公开附件。

构建步骤见 [DEVELOPMENT.md](DEVELOPMENT.md)。更新时标签、源码、安装器要对应同一版本。安装器按所有权清单清理废弃程序文件并保留设置和选装模型，没有自动联网更新。
