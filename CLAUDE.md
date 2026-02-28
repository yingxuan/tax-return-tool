# Sub-folder Context
[继承全局指令："C:\Users\yxuan\workspace\CLAUDE.md"]

# Tax Return Tool 项目规范

## 📋 常用命令
- **安装依赖**: `pip install -r requirements.txt`
- **运行 Demo**: `python -m src.main --demo`
- **启动 Web UI**: `python -m src.ui_app` 或 `flask --app src.ui_app run`，浏览器打开 http://localhost:5000
- **执行测试**: `python test_tax_calculation.py`
- **格式化代码**: `ruff check . --fix`

## 🏗 项目逻辑索引 (Context)
- **核心数据模型**: `src/models.py` (包含 TaxReturn, W2, 1099 等类定义)
- **文档解析流程**: `document_parser.py` (OCR/PDF) -> `data_extractor.py` (Regex/Logic)
- **联邦税 (1040)**: `src/federal_tax.py`, `src/schedule_a.py` (逐项扣除), `src/schedule_e.py` (房产折旧)
- **加州税 (540)**: `src/california_tax.py` (注意：无 $10,000 SALT 限制)

## ⚖️ 税务逻辑准则
- **税年支持**: 当前支持 2024 和 2025 税年。
- **折旧计算**: 租赁房产使用 27.5 年直线折旧（Mid-month convention）。
- **精度要求**: 货币计算必须保持 2 位小数，使用 Python 的 `decimal` 或四舍五入。

## 🤖 交互约束 (节省 Token)
- 在修改复杂税务公式前，先口述逻辑获取用户确认。
- 严禁打印 PDF/图像的原始二进制流或长文本 OCR 结果。
- 优先使用 `grep` 或 `head` 查看大日志，不要直接 `cat`。