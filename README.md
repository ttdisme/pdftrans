# PDFTrans · PDF 论文翻译

[![Release](https://img.shields.io/github/v/release/ttdisme/pdftrans?color=blue)](https://github.com/ttdisme/pdftrans/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)

多标签 PDF 阅读 + 划词翻译的桌面工具（Windows）。左边读论文，选中英文就在右边出中文，
译文流式显示；翻译通道可以自由切换——免 key 的 Google / Bing，或者百度 / 有道 / DeepL 的官方
API，也可以接任意 **OpenAI 兼容**的大模型（DeepSeek、通义千问、Kimi、智谱、硅基流动、OpenRouter、
本地 Ollama…）。

![screenshot](docs/screenshot.png)

## 特性

- **多标签**：一个窗口同时开多篇文献，各自的页码、缩放、滚动位置、选区互不干扰；右侧翻译栏共享。
- **划词即译**：单击翻整句，拖动翻任意片段（可跨行跨页），双击翻整段；粒度可在设置里改。
- **整页翻译**：`Ctrl+Enter` 把当前页正文按段落拼好一次翻完。
- **流式输出**：AI 通道逐字返回，不用等整段生成。
- **六种通道**：Google / Bing（免 key，开箱可用）、百度、有道、DeepL、OpenAI 兼容大模型。
- **本地缓存**：SQLite 按「通道 + 语向 + 原文」哈希去重，重复段落不再请求。
- **三套主题**：默认 / 护眼 / 夜间。
- **拖放打开**：把 PDF 拖进窗口即可，支持一次拖多个。
- **学术翻译提示词**：内置「忠实、术语、公式与引用标记保原样、只输出译文」的约束，可自行改写。

## 安装

### 方式一：安装包（推荐，免 Python）

从 [Releases](https://github.com/ttdisme/pdftrans/releases/latest) 下载 **PDFTrans-Setup-1.0.0.exe**，双击运行：

- 装到 `%LOCALAPPDATA%\Programs\PDFTrans`，**不需要管理员权限**（不写 Program Files、不碰系统目录）
- 自动创建开始菜单与桌面快捷方式，卸载走「设置 → 应用」或安装目录里的 `unins000.exe`
- 首次运行若提示「无法验证发布者」，点「运行」即可——安装包没做代码签名

不想安装：下载同一 Release 里的 `PDFTrans-1.0.0-win64-portable.zip`，解压后直接跑 `PDFTrans.exe`。

### 方式二：从源码运行

需要 Python 3.10+。

```bat
git clone https://github.com/ttdisme/pdftrans.git
cd pdftrans
python -m pip install -r requirements.txt
python main.py
```

或者双击 `run.bat`（会自检依赖并自动安装）。也可以把 PDF 作为参数：

```bat
python main.py paper.pdf
```

### 首次运行被 Windows 拦下怎么办

程序**没有做代码签名**（开源项目没买证书），所以第一次运行时 Windows 11 的 SmartScreen 可能弹：

> Windows 已保护你的电脑
> Microsoft Defender SmartScreen 阻止了无法识别的应用启动
> 应用：PDFTrans.exe　发行者：发布者未知

这是系统对**未签名新程序**的信誉提示，不是病毒告警——程序本身既没有"来自网络"的标记，也没有被
任何黑名单收录。处理方式：

1. 点「更多信息」→「**仍要运行**」。同一份程序之后不会再提示（系统按文件记住了这个决定）。
2. 重新打包（exe 哈希变了）或换目录，会再提示一次，这属于正常现象。
3. 如果连这个提示都不想看到，只有两条路：给程序买**代码签名证书**（OV 约千元/年，EV 更贵但立刻有信誉），
   或者在「Windows 安全中心 → 应用和浏览器控制 → 基于声誉的保护」里关掉「检查应用和文件」
   （后者会削弱整机防护，不推荐）。

用 `cmd /c start PDFTrans.exe` 或某些启动器（不经 shell 的方式）不会触发这个检查，但那只是绕开提示，
不能改变程序未签名的事实。

## 打包成 exe

双击 `build.bat`：装 PyInstaller（如缺）→ 生成图标 → 打包。产物是目录模式的运行包：

```
dist\PDFTrans\
  PDFTrans.exe              主程序（带图标与中文版本信息）
  _internal\                运行时依赖，必须和 exe 放在一起
  创建桌面快捷方式.bat         双击在桌面生成带图标的快捷方式
```

手动等价命令：

```bat
python -m pip install pyinstaller
python tools\make_icon.py
python -m PyInstaller --noconfirm --clean pdftrans.spec
```

为什么是目录模式而不是单文件：单文件版启动时要把上百 MB 解压到 `%TEMP%`，在部分环境会被
安全策略拦掉（报 `Could not create temporary directory!`），并且冷启动要好几秒。目录模式不写
临时目录、启动 1–2 秒。想要单文件可自行把 spec 里的 `COLLECT(...)` 换成把 `a.binaries`/`a.datas`
塞回 `EXE(...)`。

### 打成安装包

需要 [Inno Setup 6](https://jrsoftware.org/isdl.php)（`ISCC.exe` 在 PATH 或写全路径）：

```bat
ISCC.exe pdftrans.iss
```

产物 `dist\PDFTrans-Setup-<版本>.exe`：

- 装到 `{autopf}\PDFTrans`，`PrivilegesRequired=lowest` 使其落到 `%LOCALAPPDATA%\Programs`，全程无 UAC
- 开始菜单 + 可选桌面快捷方式、卸载程序、卸载时清理程序旁的 `data\`
- 中文界面用 `tools/ChineseSimplified.isl`（取自 Inno Setup 官方仓库，随仓库一起管理，不依赖本机安装的语言包）
- `pdftrans.iss` 里 `#define AppVersion` 改版本号即可发新版

## 翻译通道怎么配

设置（`Ctrl+,`）分三页。

**在线引擎** —— 填厂商 key：

| 通道 | 需要什么 |
| --- | --- |
| 百度翻译 | APPID + 密钥（通用文本翻译 API） |
| 有道智云 | 应用 ID + 应用密钥 |
| DeepL | Auth Key（免费版端点 / 付费版 / 自建代理） |

**AI 大模型** —— 选服务商 →「套用预设」自动填 Base URL 和模型名，再填自己的 API Key：

| 预设 | Base URL | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |

- 「额外参数」透传给 `/chat/completions`，例如 `{"enable_thinking": false}`。
- 「系统提示词」就是学术翻译的约束，可自行改写。
- 「测试当前通道」会发一句英文试翻，直接看到返回或报错原因。

免 key 通道实现说明：
- **Google**：`translate_a/single`（POST，按 4500 字符分段）。
- **Bing**：网页版 `ttranslatev3`，先抓页面里的 `IG` / `IID` / `AbusePreventionHelper` 再提交。
这两个接口都不是官方 API，随时可能变更；厂商 key 或 AI 通道更稳。

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `Ctrl+O` | 打开 PDF（可多选，每个一个标签） |
| `Ctrl+W` | 关闭当前标签 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 切换标签 |
| `Ctrl+Shift+T` | 翻译选区 |
| `Ctrl+Enter` | 翻译当前整页 |
| `Ctrl+Shift+V` | 翻译剪贴板 |
| `Ctrl+滚轮` / `Ctrl+0` / `Ctrl+9` | 缩放 / 适应宽度 / 适应整页 |
| `PageUp` / `PageDown` | 翻页 |
| `Esc` | 清除选区 |
| `Ctrl+,` | 设置 |

## 数据与缓存

- 配置：`%APPDATA%\PDFTrans\config.json`
- 缓存：`%APPDATA%\PDFTrans\cache.sqlite3`
- 若 `%APPDATA%` 不可写，自动改用 exe 旁边的 `data\` 目录，再不行退到 `%TEMP%\PDFTrans`，
  可用环境变量 `PDFTRANS_DATA_DIR` 强制指定。

## 自检与排障

```bat
PDFTrans.exe --selftest examples\sample-paper.pdf --shot a.png --translate --drop
```

会起窗口开标签、真翻一句、模拟一次拖放、截图并写 `a.log`（`tabs=` / `pages=` / `data_dir=` /
`cache_error=` / `drop_pages=` / `translate=`），退出码 0 表示正常。崩溃日志写在数据目录下的
`startup-error.log`，缓存不可用时另记 `cache-error.log`。

## 项目结构

```
main.py                 入口（异常日志 + 应用图标 + 自检模式）
build.bat               一键打包
pdftrans.spec           PyInstaller 配置
run.bat                 从源码启动
assets/                 app.ico / app.png（图标，由脚本生成）
examples/               示例 PDF（由脚本生成，无真实内容）
docs/                   截图
tools/
  make_icon.py          矢量生成图标（QPainter）
  make_sample_pdf.py    生成示例 PDF
  version_info.txt      exe 版本信息
pdftrans/
  config.py             配置模型、AI 预设、导入导出
  cache.py              SQLite 翻译缓存
  engines.py            6 个通道实现（Google/Bing/百度/有道/DeepL/AI 流式）
  pdfdoc.py             字符级文本层：bbox、行列、区间取文、句/段扩展
  resources.py          资源路径（源码 / 打包两用）
  worker.py             TranslateWorker + TranslateTask(QThread)
  ui/
    mainwindow.py       多标签主窗口：菜单、工具栏、主题、最近文件
    pdfview.py          连续滚动阅读区、懒渲染、字符级拖选
    panel.py            右侧原文 / 译文面板
    settings.py         设置对话框（含通道自测）
    styles.py           三套配色
```

## 已知限制

- 加密 PDF 只尝试空密码；带 DRM 的不支持。
- 扫描版（无文字层）PDF 不 OCR，会明确提示。
- 多栏排版按 PDF 的 block 切段，个别期刊的跨栏 block 可能把两栏并成一段。
- AI 通道长文本按 3800 字符切块顺序翻译，保序拼接，不保证跨块指代一致。
- 仅测试了 Windows；Qt 部分理论上跨平台，但打包脚本是 Windows 的。

## License

MIT，见 [LICENSE](LICENSE)。
