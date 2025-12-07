一份可落地的项目框架（偏工程化，便于团队开工）。默认目标：macOS 上，用嵌入/附着浏览器，人工先登录和打开题目，脚本接管答题。

---

## 一、整体架构
- **UI/控制层**：CLI 或极简前端（启动/暂停/切题/重试），展示当前题面、模型答案、执行结果。
- **浏览器控制层**：Playwright（Python/Node 二选一）持久化 userDataDir 或 attach CDP，提供 DOM 获取、点击/输入、截图能力。
- **感知层**：  
  - DOM 提取：优先用 Playwright 读题干、选项文本。  
  - OCR 兜底：对图片/Canvas 题或拿不到 DOM 时截屏 → OCR（macOS Vision/Swift CLI 或 Python OCR 服务）。  
- **理解/决策层**：调用 DeepSeek API，输入题面+选项+题型，输出结构化答案（选项 key/文本或填空内容）。
- **动作执行层**：根据答案映射到元素选择器，`click()`/`fill()`，必要时坐标兜底。
- **日志与回溯**：题面文本、OCR 结果、模型输入输出、执行动作、截图；便于调试/回放。

---

## 二、模块划分
1) **browser_controller**
   - 启动/attach 浏览器；管理页面上下文。
   - DOM 抽取：题干、选项、题型，支持 iframe/shadow DOM。
   - 动作 API：click/fill/press，带重试与随机延时。
   - 截图 API：全屏/元素级。

2) **vision_ocr**
   - 接口：`ocr_image(image_bytes) -> {text, boxes, conf}`。
   - 实现：Swift+Vision CLI（首选，零依赖）或 Python `rapidocr-multilingual` 服务（备用）。
   - 召回策略：先 DOM，失败时调用。

3) **nlp_agent**
   - DeepSeek 调用封装：prompt 模板、温度、max tokens。
   - 答案解析：正则/JSON schema，输出结构化结果：`{"type":"single|multi|fill","answer":["A"] or ["A","C"] or "text"}`。
   - 安全：截断过长上下文；异常时回退“人工确认”。

4) **selector_finder**
   - 根据选项文本生成多策略 locator：text/label/aria/placeholder，兜底 XPath，最后坐标。
   - 去重与模糊匹配（避免相似选项误点）。

5) **executor**
   - 主流程：获取题面 → 组装上下文 → 调模型 → 解析 → 执行动作 → 校验（可选再截图+比对）。
   - 失败处理：重试、改用 OCR、改用坐标点击，最终人工提示。

6) **config & secrets**
   - DeepSeek API key、模型参数、浏览器路径、userDataDir、延时/重试次数。
   - 环境：macOS 权限（辅助功能、屏幕录制）。

7) **logging & review**
   - 结构化日志（JSON），带时间、URL、题号、决策、动作。
   - 本地存档截图，便于复现和人工审核。

---

## 三、技术选型建议
- **语言**：Python（生态成熟，Playwright/PyObjC/OCR 方便）或 Node（团队前端背景）。  
- **浏览器**：Playwright Chromium 持久化 profile；或 attach Chrome 远程调试端口。  
- **OCR**：优先 macOS Vision（Swift CLI，小巧高精），备选 Python `rapidocr-multilingual`。  
- **并发**：单机单会话为主；若多会话，Python asyncio 或 Node Promise 并发，但注意浏览器实例隔离。

---

## 四、最小可行路径（MVP）
1) Playwright 持久化用户目录，人工登录并打开题目，按回车继续。
2) DOM 抓题干/选项 → DeepSeek 推理 → 直接用文本定位点击/填空。
3) 失败时截图 + OCR，重新推理。
4) 基础日志/截图存档。

---

## 五、迭代路线
- **v0.1**：单题循环，单页 DOM 获取，单选题，日志。
- **v0.2**：多选/填空，OCR 兜底，随机延时和重试。
- **v0.3**：Shadow DOM/iframe 支持，多策略 locator，答题后校验截图。
- **v0.4**：小前端/热键控制（暂停/继续/重试），错误提示。
- **v1.0**：并发会话（可选）、配置化策略、异常报警。

---

## 六、关键设计细节
- **上下文构造**：题干+选项+题型+特殊说明（多选/填空），控制 token；过长时截断或分段提要再问答。
- **解析稳健性**：要求模型返回 JSON，带字段校验；解析失败重试或回退人工。
- **定位稳健性**：文字匹配→aria/label→XPath→坐标；每步带相似度阈值和超时。
- **权限**：Terminal/IDE 获得“辅助功能”和“屏幕录制”权限，否则无法点击/截图。

---

## 七、风险与对策
- **反自动化**：使用真实浏览器，加入人类节奏（随机延时、滚动），少用明显脚本痕迹。
- **OCR 误差**：优先 DOM；OCR 加置信度过滤和模糊匹配。
- **页面异步加载/iframe**：等待选择器、处理 iframe；必要时滚动唤醒懒加载。
- **登录失效**：持久化 profile，检测 401/跳转后提示人工重新登录。


---

## 八、目录示例（Python 版）
```
project/
  config.yaml
  main.py                # 入口，CLI/循环
  browser_controller.py  # Playwright 控制、DOM 抽取、动作
  vision_ocr.py          # OCR 封装
  nlp_agent.py           # DeepSeek 调用与解析
  selector_finder.py     # 定位策略
  executor.py            # 主流程编排
  utils/logger.py
  scripts/vision_cli.swift  # 可选：Swift OCR CLI
  data/logs/
  data/screenshots/
  user_data/             # 浏览器用户目录
```
