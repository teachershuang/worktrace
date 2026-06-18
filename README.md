# WorkTrace

WorkTrace 是一个本地运行的日报生成助手 MVP。它通过截图、OCR 和 OpenAI-compatible 大模型服务识别有效工作事件，沉淀时间轴，并生成日报和周报。

当前版本优先实现 API/CLI 主流程，不依赖云端系统。

## 快速开始

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
python main.py --help
```

## 目录

- `worktrace/config`: 配置读取和校验
- `worktrace/capture`: 截图与活跃窗口信息
- `worktrace/ocr`: OCR HTTP 服务调用
- `worktrace/llm`: OpenAI-compatible 大模型调用
- `worktrace/classifier`: 屏幕内容工作事件识别
- `worktrace/timeline`: 事件存储与时间轴合并
- `worktrace/report`: 日报和周报生成
- `worktrace/runtime`: 单次记录与后台循环
- `worktrace/ui`: CLI 和本地控制台入口
- `prompts`: 所有 LLM Prompt

## 状态

MVP 正在实现中。
