# AIAgent4elang

一个帮助自动阅读理解并答题的浏览器小助手，使用 DeepSeek 模型和 Playwright 驱动浏览器。

👉 面向完全新手的超简版教程：[点这里打开](docs/newbie-guide.md)（Windows / macOS 分步，一键脚本）。

## 快速上手（熟悉命令行的简版）
1) 准备：先申请 DeepSeek API Key（<https://platform.deepseek.com/api_keys>），再在本机修改 `config.yaml`，把 `deepseek.api_key` 改成你的密钥（如 `"sk-xxx"`）。此改动别提交或上传。
2) 依赖：
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows: `python -m venv .venv` 后 `.\.venv\Scripts\Activate.ps1`
   然后 `pip install -r requirements.txt`
   再 `python -m playwright install chromium`
3) 运行：`python main.py`。按提示打开题目页、回车继续。结束后按提示回车退出。

> 若不熟悉命令行，直接看 `docs/newbie-guide.md` 的一键脚本（里面也教你在本机 config.yaml 填密钥，且不上传）。

## 目录概览（了解即可，不必修改）
- `main.py`: 程序入口。
- `executor.py`: 主流程调度。
- `browser_controller.py`: 浏览器启动、题干/选项解析、点击/填充。
- `nlp_agent.py`: DeepSeek 调用与答案解析。
- `selector_finder.py`: 根据选项文本生成定位器。
- `vision_ocr.py`: OCR 兜底（默认关闭）。
- `utils/logger.py`: 结构化日志。
- `run.sh`: macOS 一键运行脚本。
- `data/`: 日志、截图存放（已在 .gitignore 中）。
