# AIAgent4elang

基于 Playwright + DeepSeek 的阅读理解答题 Agent 脚手架（macOS 优化）。

## 快速开始
1. 安装依赖：
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
2. 配置密钥与参数：
   - 在 `.env` 中写入 `DEEPSEEK_API_KEY=你的key`，或直接导出环境变量。
   - 根据需要编辑 `config.yaml`（浏览器路径、userDataDir、截图/日志目录等）。
   - 如无需 OCR，`agent.enable_ocr_fallback` 默认已关闭；若有图片题再开启。
3. 运行：
   ```bash
   python main.py
   ```
   - 人工登录并打开题目页，按回车继续。
   - 默认流程：DOM 抽取题干 → DeepSeek 推理 → 文本定位点击 → 截图。

## 目录结构
- `main.py`: 入口。
- `executor.py`: 主流程编排，负责 DOM/模型/OCR/动作。
- `browser_controller.py`: Playwright 持久化上下文、动作 API。
- `nlp_agent.py`: DeepSeek 调用与答案解析。
- `selector_finder.py`: 选项文本到 locator 的多策略生成。
- `vision_ocr.py`: OCR 兜底，Swift Vision 或 HTTP 服务。
   - 若仅 DOM 可读，可保持 `enable_ocr_fallback=false`，无需启用 OCR。
- `utils/logger.py`: JSON 结构化日志。
- `scripts/vision_cli.swift`: 占位的 Swift Vision CLI，需后续实现。
- `data/`: 日志、截图存放。

## 后续补全
- 完善 `browser_controller.read_question_block`：根据页面结构抽取题干/选项/题型，支持 iframe/shadow DOM。
- 实现 Swift Vision OCR，或部署/连接 `rapidocr` 服务。
- 增加答题类型识别、多选/填空的解析与执行。
- 加入 CLI/前端控制（暂停/继续/重试）、错误回溯、更多日志字段。
