# AIAgent4elang 新手超简版

适合不熟悉命令行的用户。分 Windows 和 macOS 两部分，尽量用“一键脚本”。

## 你需要准备
- 一个 DeepSeek API Key（复制好）。
- 能上网的电脑。

## Windows（PowerShell）
1) 下载或解压项目，进入项目文件夹。
2) 在 `config.yaml` 里，把 `deepseek.api_key` 改成你的真实密钥（如 `"sk-xxx"`）。此文件只在本机使用，别上传到任何代码仓库。
3) 在项目文件夹，右键“以管理员身份”打开 PowerShell。
4) 允许脚本只在本次会话运行：
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```
5) 运行一键脚本：
   ```powershell
   powershell -ExecutionPolicy Bypass -File run.ps1
   ```
6) 脚本会自动：建虚拟环境 → 安装依赖 → 下载浏览器 → 启动程序。
   - 按提示在浏览器里登录并打开题目页，回车继续。
   - 程序完成后按提示回车退出。

若脚本失败，可改用手动：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

## macOS（终端）
1) 下载或解压项目，进入项目文件夹。
2) 打开 `config.yaml`，把 `deepseek.api_key` 改成你的真实密钥（如 `"sk-xxx"`）。仅本机使用，不要上传仓库。
3) 直接运行一键脚本（无需改权限也行）：
   ```bash
   bash run.sh
   ```
   若愿意，也可先赋权再跑：`chmod +x run.sh && ./run.sh`
4) 脚本会自动：建虚拟环境 → 安装依赖 → 下载浏览器 → 启动程序。
   - 按提示在浏览器里登录并打开题目页，回车继续。
   - 程序完成后按提示回车退出。

若脚本失败，可改用手动：
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

## 常见问题（精简版）
- 密钥无效：检查 `.env` 拼写，重新运行。
- 题干/选项没抓到：文件 `data/logs/page_dump.html` 里有页面结构，找出选项的 class 或 data-* 提供给我们调整。
- Windows 提示执行策略：务必先运行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`。
