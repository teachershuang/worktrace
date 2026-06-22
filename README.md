# WorkTrace

[![Version](https://img.shields.io/badge/version-0.2.0-2d2b2b)](https://github.com/teachershuang/worktrace)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](https://www.microsoft.com/windows)
[![GitHub stars](https://img.shields.io/github/stars/teachershuang/worktrace?style=social)](https://github.com/teachershuang/worktrace/stargazers)

WorkTrace 是一个本地运行的日报生成助手。它在后台定时采集主屏截图，调用局域网或本地 OCR 服务提取文字，再用 OpenAI-compatible 大模型做内容级工作识别，最终沉淀为时间轴、待确认队列、日报和周报。

第一版目标不是复杂平台化，而是先把个人/内部可用的闭环跑通：

- 本地运行，不依赖云端 Web 系统
- 不按应用名粗暴判断工作，而是结合 OCR 文本、窗口标题和上下文判断
- 高置信度事件进入有效时间轴
- 低置信度事件进入待确认队列，不强行编造日报
- 日报和周报只基于真实时间轴生成

## Screenshots

![Console Overview](docs/images/console-overview.png)

## Features

- `Windows 桌面运行`
  支持 `python main.py desktop`、系统托盘模式、PyInstaller `exe` 打包。
- `本地控制台`
  提供 FastAPI + 静态控制台，可执行开始记录、暂停、恢复、立即记录、报告生成、待确认处理、诊断查看。
- `内容级工作识别`
  结合 `应用名 + 窗口标题 + OCR 文本 + 最近上下文 + 已识别项目列表` 做工作判断。
- `待确认工作流`
  支持单条确认、批量标记工作/非工作、按日期回看、搜索筛选。
- `日报/周报生成`
  仅基于有效时间轴生成 Markdown 报告，并支持本地二次编辑。
- `发布诊断`
  提供 `doctor` 命令检查配置、依赖、目录权限、OCR/LLM 连通性、Windows 活跃窗口依赖和开机自启状态。

## Project Layout

```text
worktrace/
├─ worktrace/
│  ├─ capture/
│  ├─ classifier/
│  ├─ config/
│  ├─ llm/
│  ├─ ocr/
│  ├─ report/
│  ├─ runtime/
│  ├─ timeline/
│  └─ ui/
├─ prompts/
├─ tests/
├─ docs/
├─ scripts/
├─ config.example.yaml
├─ config.lan.example.yaml
├─ requirements.txt
├─ worktrace.spec
└─ main.py
```

## Quick Start

### 1. 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

### 2. 填写配置

```yaml
llm:
  base_url: "http://127.0.0.1:8000/v1"
  api_key: "replace-with-your-api-key"
  model: "qwen3.6-35b-a3b"
  timeout_seconds: 60
  trust_env: false

ocr:
  url: "http://192.168.8.30:9000/ocr"
  timeout_seconds: 30
  protocol: "multipart"
  trust_env: false

recording:
  work_periods:
    - "09:00-12:00"
    - "13:30-18:00"
  screenshot_interval_seconds: 300
  idle_skip_minutes: 10
  enable_tray: false

storage:
  data_dir: "data"
  report_output_dir: "data/reports"
  log_dir: "logs"
```

### 3. 先跑诊断

```powershell
python main.py doctor
python main.py test-ocr
python main.py test-llm
```

### 4. 启动桌面端

```powershell
python main.py desktop
```

如果需要单独启动控制台或托盘：

```powershell
python main.py console
python main.py tray
```

## Common Commands

```powershell
python main.py config-show
python main.py doctor --skip-services
python main.py record-once
python main.py start
python main.py pause
python main.py resume
python main.py stop
python main.py today-timeline
python main.py review-list
python main.py review-mark-work <event-id-prefix>
python main.py review-mark-nonwork <event-id-prefix>
python main.py daily-report
python main.py weekly-report
python -m unittest discover -s tests
```

## Windows Packaging

仓库已提供 PyInstaller `onedir` 打包配置：

```powershell
.\scripts\build_windows.ps1 -Clean
```

产物位于：

```text
dist/WorkTrace/
├─ WorkTrace.exe
├─ WorkTrace-cli.exe
├─ config.example.yaml
└─ config.lan.example.yaml
```

说明：

- `WorkTrace.exe` 为桌面入口，无参数时优先从可执行文件同目录查找 `config.yaml`
- `WorkTrace-cli.exe` 为命令行入口，适合诊断、测试和脚本调用
- 发布目录内相对路径会解析到发布目录自身，因此默认数据、报告和日志都会落在 `dist/WorkTrace/`

## OCR / LLM Integration

### OpenAI-compatible LLM

```text
POST {base_url}/chat/completions
Authorization: Bearer {api_key}
```

### Multipart OCR

```text
POST {ocr.url}
file=screenshot.png
```

### Paddle OCR JSON

```yaml
ocr:
  url: "http://192.168.8.29:8866/ocr"
  timeout_seconds: 60
  protocol: "paddle_json"
```

`paddle_json` 模式会发送 `documents[].pages[].image_base64`，并使用 `/health` 做联通性测试。

## Data Files

- `data/events/YYYY-MM-DD.raw.jsonl`
  原始分析记录
- `data/events/YYYY-MM-DD.effective.jsonl`
  有效时间轴事件
- `data/events/YYYY-MM-DD.review.jsonl`
  待确认事件
- `data/reports/`
  日报与周报 Markdown
- `data/runtime_state.json`
  运行状态
- `logs/worktrace.log`
  本地日志

## UI & Assets

- 控制台前端位于 `worktrace/ui/static/`
- 本地素材包位于 `worktrace/ui/static/assets/`
- 桌面图标位于 `worktrace.ico`
- README 截图位于 `docs/images/`

当前主题保持“Q 版任务助手 + 小猫”方向，不依赖外部 CDN。

## Current Scope

当前版本已经覆盖 MVP 主闭环，但仍有明确边界：

- 默认只截主屏
- 时间轴合并仍以规则为主，不是更强的语义级聚合
- 报告支持本地编辑，但还不是完整文档工作台
- 还没有安装器、自动升级、签名和绿色包发布说明
- 多屏截图、区域裁剪、脱敏策略仍未实现

## License

当前仓库默认未附加开源许可证。如需正式开源，请补充 `LICENSE` 文件并确认第三方依赖、素材和模型接入方式的分发边界。
