# fixsub

[English](README.md)

[![CI](https://github.com/IronJKZ/fixsub/actions/workflows/ci.yml/badge.svg)](https://github.com/IronJKZ/fixsub/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/IronJKZ/fixsub)](https://github.com/IronJKZ/fixsub/releases/latest)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`fixsub` 是一款优先支持 macOS 的命令行工具，用于为本地电影搜索、验证、同步并应用中文字幕。

> 状态：`0.1.0` 是早期公开版本。对重要媒体库操作前，请先使用 `--dry-run`。

## 功能

- 为当前文件夹中的视频从 ASSRT 和 SubHD 搜索中文字幕候选项。
- 下载并解压受支持的字幕文件，然后将其规范化为 UTF-8。
- 使用 `ffprobe` 选择参考音轨，然后通过 `ffsubsync` 根据电影音频自动校准每个合格的候选字幕；低质量同步结果会被拒绝。
- 支持使用 `fixsub adjust --seconds` 手动整体提前或延后字幕，并自动备份原字幕、记录调整元数据。
- 对候选项排序，在替换前保留已有的最终字幕，并在视频旁写入兼容 Infuse 的中文字幕。
- 将运行产物和诊断信息记录在 `.fixsub/` 下，便于事后检查。

## 工作流程

请在包含目标电影的文件夹中运行 `fixsub`。工具会检测受支持的本地视频、生成搜索词、向启用的字幕源请求结果、对结果排序、探测并选择参考音轨，然后下载、解压并规范化字幕文件。随后它会排除非中文字幕候选项。默认情况下，它会通过 `ffsubsync` 根据电影音频校准每个合格的候选字幕；`--no-sync` 会明确跳过这一步。工具会对决策排序、备份之前的最终字幕，并在找到合适结果时写入 `<video_stem>.zh.<ext>`。

这是一个单电影文件夹工作流程。若文件夹中包含多个受支持的视频，将选择最大的文件；若这不是目标电影，请使用单独的文件夹。

## 系统要求

- macOS 和 Python 3.11 或更高版本。
- 用于媒体探测和压缩包解压的 Homebrew 工具：

  ```bash
  brew install ffmpeg unar
  ```

- 可选的音频同步支持：

  ```bash
  python3 -m pip install ffsubsync
  ```

`ffprobe` 由 `ffmpeg` 提供。`unar` 用于处理 `.rar` 和 `.7z` 压缩包；`.zip` 解压为内置能力。`fixsub` 优先支持 macOS，不保证在非 macOS 系统上的兼容性。

## 支持的格式

| 类型 | 格式 |
| --- | --- |
| 视频 | `.mkv`、`.mp4`、`.m4v`、`.avi`、`.mov` |
| 字幕 | `.srt`、`.ass`、`.ssa` |
| 下载/压缩包 | 直接字幕文件、`.zip`、`.rar`、`.7z` |

直接下载的字幕和 `.zip` 解压不需要 `unar`；解压 `.rar` 和 `.7z` 需要 `unar`。

## 安装

### 普通用户安装

克隆仓库，并在虚拟环境中安装 `fixsub`：

```bash
git clone https://github.com/IronJKZ/fixsub.git
cd fixsub
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
python3 -m pip install ffsubsync
```

最后一条命令会安装默认音频同步流程使用的 `ffs` 可执行文件。项目尚未发布 PyPI 包，因此当前需要从源码检出目录安装。

### 贡献者安装

如需运行测试和本地构建包，请使用可编辑的开发环境安装：

```bash
python3 -m pip install -e ".[dev]"
```

贡献流程请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 身份验证

ASSRT 使用令牌。请通过以下命令将其存入 macOS 钥匙串：

```bash
fixsub auth set
```

通过以下命令查看配置来源或删除已存储的钥匙串令牌：

```bash
fixsub auth status
fixsub auth delete
```

macOS 钥匙串是首选的持久化存储方式。临时的 `ASSRT_TOKEN` 环境变量会覆盖钥匙串中的值，适用于单个 shell 或自动化任务。不要让令牌进入 shell 历史、问题报告、日志或已提交文件。若没有可用令牌且同时启用 SubHD，ASSRT 会被跳过；而 `fixsub --providers assrt` 会停止并要求配置凭据。

## 使用方式

在包含电影的文件夹中运行：

```bash
fixsub
```

默认字幕源是 ASSRT 加 SubHD。只要至少存在一个可用的中文字幕候选项，`fixsub` 就会写入排名最高的候选项，并在控制台和元数据中记录其置信度和选择结果。

### 安全预览

```bash
fixsub --dry-run
```

`--dry-run` 会执行搜索、探测、下载、解压、验证和同步，并写入 `.fixsub/` 运行产物，但不会在视频旁写入或替换最终字幕。这是处理重要媒体库时推荐的首个命令；仍会发生字幕源请求并生成本地运行文件。

### 字幕源选择

```bash
fixsub --providers subhd
fixsub --providers assrt,subhd
```

使用 `fixsub --providers subhd` 可避免使用 ASSRT 凭据。使用 `fixsub --providers assrt,subhd` 可显式选择两个字幕源（也是默认值）。SubHD 下载会先走其准备下载流程，再获取最终文件。字幕源的搜索或下载失败会被记录，运行可继续使用其他可用字幕源；但字幕源故障可能导致没有可用候选项。

### 音轨与同步

```bash
fixsub --audio a:0
fixsub --no-sync
```

默认情况下，`fixsub` 会通过 `ffprobe` 探测音轨、选择参考流，并对每个候选项尝试 `ffsubsync`。`fixsub --audio a:0` 会强制传给 `ffsubsync` 的流。`fixsub --no-sync` 会跳过音频同步，仅对原始候选项排序；仅应在必要时使用，因为结构化时间戳检查无法证明对白或音频对齐。

`fixsub` 会先要求 `ffsubsync` 跳过低质量对齐；如果保守同步明确拒绝该对齐，则自动以强制模式重试一次。只要至少存在一个可用的中文字幕候选项，即使置信度仍然较低，也会写入排名最高的候选项；控制台和元数据会明确标记强制同步或原字幕回退。只有在没有候选项能够下载、解压、解析或通过中文内容检查时才会停止且不写入字幕。

### 候选数量与语言标签

```bash
fixsub --max-candidates 5
fixsub --lang zh-Hans
```

`--max-candidates` 会限制从排序后的字幕源结果中选取用于下载的项目（默认值为 `5`），从而控制运行时间和对字幕源的请求量。一个下载的压缩包可能包含多个字幕文件，因此解压出的候选项数量可能超过该值。`--lang` 控制最终字幕后缀；默认 `zh` 会生成 `<video_stem>.zh.<ext>`，当媒体库需要该标签时可使用 `zh-Hans`。

### 手动微调时间轴

```bash
fixsub adjust --seconds 1.0
fixsub adjust --seconds -1.0
```

`adjust` 会移动检测到的最终字幕时间轴，不会再次搜索或运行同步。正秒数会延后字幕，负秒数会提前字幕。该命令会将被替换的最终字幕备份到 `.fixsub/original/`，并将调整记录到 `.fixsub/metadata/adjustment.json`；在保留更改前请先在播放器中验证结果。

### 诊断信息

```bash
fixsub --debug
```

`--debug` 可被接受，并会作为运行选项记录在 `.fixsub/metadata/results.json` 中。在这个早期版本中，它不会额外输出详细的控制台信息，因此请检查该元数据文件和 `.fixsub/logs/fixsub.log` 获取诊断信息。在分享前，请将二者视为私有运行数据。

## 输出与备份

应用后的字幕会写入检测到的视频旁，命名为：

```text
<video_stem>.zh.<ext>
```

每次运行都会创建或复用以下本地工作路径：

- `.fixsub/downloads/` 保存从字幕源下载的文件。
- `.fixsub/candidates/` 保存已解压并规范化为 UTF-8 的字幕候选项。
- `.fixsub/synced/` 保存同步成功后生成的字幕文件。
- `.fixsub/original/` 保存最终字幕被替换前的带时间戳备份，包括 `adjust` 造成的替换。
- `.fixsub/logs/fixsub.log` 记录字幕源和运行诊断信息。
- `.fixsub/metadata/results.json` 记录视频、选项、搜索词、下载项、候选项、决策、选中音轨、输出路径和结果消息。

## 隐私与安全

请使用 `fixsub auth set`，不要将 ASSRT 令牌放入项目文件。临时使用时支持 `ASSRT_TOKEN`，且它会优先于钥匙串；但它仍然是机密信息。日志写入器会从消息中遮蔽当前令牌，但日志和元数据仍可能包含电影文件名、字幕源数据和本地路径。

在创建问题前，请移除 `.fixsub/logs/fixsub.log`、`.fixsub/metadata/results.json`、下载的数据以及所有令牌或私有路径，除非相关信息确有必要且已被仔细脱敏。绝不要在问题、命令记录或截图中粘贴凭据。

## 故障排查

- **找不到 `ffprobe`：** 使用 `brew install ffmpeg` 安装，然后确认 Homebrew 的二进制目录位于 `PATH` 中。
- **无法解压 `.rar` 或 `.7z` 压缩包：** 使用 `brew install unar` 安装解压支持后重试。`.zip` 文件不需要 `unar`。
- **ASSRT 提示缺少凭据：** 运行 `fixsub auth set`，检查 `fixsub auth status`，或设置临时 `ASSRT_TOKEN`。若不打算使用 ASSRT，请使用 `fixsub --providers subhd`。
- **字幕源不可用或找不到候选项：** 请稍后重试、选择其他字幕源，并检查 `.fixsub/logs/fixsub.log`；字幕源结果和下载状态会独立于工具发生变化。
- **已应用低置信度字幕：** 检查 `.fixsub/candidates/`、`.fixsub/synced/` 和 `.fixsub/metadata/results.json`。控制台和元数据会标记它使用的是强制同步还是原字幕回退。
- **同步失败：** 安装 `ffsubsync`，确认 `ffprobe` 能读取视频，使用 `fixsub --audio a:0` 选择正确的流，并检查日志。若原字幕仍是排名最高的可用候选项，`fixsub` 会将其作为回退写入。

## 开发

使用以下命令运行测试套件：

```bash
.venv/bin/python -m pytest -q
```

在本地构建分发产物：

```bash
python -m build
```

贡献者工作流程、测试和隐私要求请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。本地构建不会发布包。

## 当前限制

尚未实现交互模式、媒体库扫描、Whisper 字幕生成、翻译和 Web UI。不保证非 macOS 系统的兼容性，也不提供 PyPI 分发。候选项排序和同步能降低风险，但未实现也不保证自动完美匹配对白。

## 贡献与安全报告

贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题应通过 [SECURITY.md](SECURITY.md) 报告，而非公开问题。发布历史见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

本项目使用 [MIT License](LICENSE) 授权。
