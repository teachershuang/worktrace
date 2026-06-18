# WorkTrace

WorkTrace 是一个本地运行的日报生成助手 MVP。它在工作时间内定时截取主屏幕，调用局域网 OCR 服务识别文字，再调用 OpenAI-compatible 大模型判断当前屏幕是否形成有效工作事件，最终沉淀时间轴并生成日报、周报。

第一版优先保证主流程可跑通，采用 CLI、本地 FastAPI 控制台、系统托盘入口和 JSONL 本地存储。

## 安装

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
llm:
  base_url: "http://127.0.0.1:8000/v1"
  api_key: "replace-with-your-api-key"
  model: "qwen3.6-35b-a3b"
  timeout_seconds: 60

ocr:
  url: "http://192.168.8.30:9000/ocr"
  timeout_seconds: 30
  protocol: "multipart"
```

## 外部服务要求

LLM 服务需要兼容 OpenAI Chat Completions：

```text
POST {base_url}/chat/completions
Authorization: Bearer {api_key}
```

OCR 服务需要支持 multipart 文件上传：

```text
POST {ocr.url}
file=screenshot.png
```

如果使用远端 PaddleOCR JSON 服务，可以把协议切到 `paddle_json`：

```yaml
ocr:
  url: "http://192.168.8.29:8866/ocr"
  timeout_seconds: 60
  protocol: "paddle_json"
```

`paddle_json` 会发送 `documents[].pages[].image_base64`，并使用 `/health` 做连通性测试。OCR 返回可以是纯文本，也可以是 JSON。JSON 中优先读取 `text`、`content`、`result`、`ocr_text`、`full_text`，也兼容 `documents[].full_text`、`pages[].texts`、`lines[].text` 和 `boxes[].text`。

仓库提供 `config.lan.example.yaml`，用于连接局域网示例服务。复制为 `config.yaml` 后需要自行填入有效的大模型 API Key，不要把真实密钥提交到仓库。

当前局域网示例已验证：

- 模型网关：`http://192.168.8.29:4000/v1`
- 模型名称：`Qwen3.6-35B-A3B-GGUF`
- OCR 服务：`http://192.168.8.29:8866/ocr`

## 常用命令

查看配置：

```powershell
python main.py config-show
```

测试服务：

```powershell
python main.py test-llm
python main.py test-ocr
```

立即记录一次：

```powershell
python main.py record-once
```

启动前台后台循环：

```powershell
python main.py start
```

启动记录会清除上一次运行留下的暂停和停止标记。

启动本地控制台：

```powershell
python main.py console
```

默认地址是 `http://127.0.0.1:8765`。控制台支持开始记录、暂停、恢复、停止、立即记录、查看今日时间轴、处理待确认事件、生成日报和周报。

控制台前端是本地静态页面，入口在 `worktrace/ui/static/index.html`，样式和交互分别在 `worktrace/ui/static/styles.css`、`worktrace/ui/static/app.js`。第一版素材包位于 `worktrace/ui/static/assets/`，包含参考图裁切出的助手、猫咪和托盘图标资源，运行时不依赖外部 CDN。

启动系统托盘：

```powershell
python main.py tray
```

托盘菜单包括开始记录、暂停记录、恢复记录、立即记录一次、生成日报、打开控制台和退出。托盘启动后不会自动开始记录，需要从菜单选择“开始记录”。

暂停、恢复、停止循环：

```powershell
python main.py pause
python main.py resume
python main.py stop
```

查看今日时间轴和待确认事件：

```powershell
python main.py today-timeline
python main.py review-list
```

确认待确认事件：

```powershell
python main.py review-mark-work <event-id-prefix>
python main.py review-mark-nonwork <event-id-prefix>
```

生成报告：

```powershell
python main.py daily-report
python main.py weekly-report
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## 数据位置

- 原始事件：`data/events/YYYY-MM-DD.raw.jsonl`
- 有效时间轴事件：`data/events/YYYY-MM-DD.effective.jsonl`
- 待确认事件：`data/events/YYYY-MM-DD.review.jsonl`
- 日报和周报：`data/reports/`
- 运行状态：`data/runtime_state.json`
- 日志：`logs/worktrace.log`

## 空闲跳过

`recording.idle_skip_minutes` 用于控制空闲跳过。Windows 下 WorkTrace 会读取系统最后输入时间，如果鼠标键盘空闲时长超过配置值，本轮记录会自动跳过并写入日志。其他平台暂时降级为不跳过。

## 工作识别逻辑

WorkTrace 不按应用名简单判断是否工作。每次记录会把当前时间、应用名、窗口标题、OCR 文本、上一条有效工作事件、最近 30 分钟摘要和今日项目列表发送给大模型。

大模型必须返回严格 JSON。高置信度工作内容进入有效时间轴；低置信度内容进入待确认队列；高置信度非工作内容只保留在原始事件中，不参与日报。

## 项目结构

- `worktrace/config`: 配置读取、校验和日志初始化
- `worktrace/capture`: 主屏截图与活跃窗口信息
- `worktrace/ocr`: OCR HTTP 服务调用
- `worktrace/llm`: OpenAI-compatible 大模型调用
- `worktrace/classifier`: 屏幕内容工作事件识别
- `worktrace/timeline`: 事件存储、待确认处理和时间轴合并
- `worktrace/report`: 日报和周报生成
- `worktrace/runtime`: 单次记录、状态文件和定时循环
- `worktrace/ui`: CLI、本地控制台 API、静态控制台页面和系统托盘入口
- `worktrace/ui/static/assets`: 本地 UI 素材包
- `prompts`: 分类、合并、日报、周报 Prompt

## 当前限制

- 第一版默认只截主屏幕。
- 托盘菜单已实现基础控制，暂未做原生桌面窗口和安装包。
- 时间轴合并使用本地确定性规则，后续可切换为 LLM 语义合并。
