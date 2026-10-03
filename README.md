# AI Interview System（学生面试管理与智能评估系统）

一个用于校园组织 / 学生组织面试管理的 **AI 辅助面试系统**：本地运行、浏览器操作、数据完全留在自己电脑上。围绕「简历预览 → 多维打分 → AI 总结 → 联评汇总」的完整面试闭环设计，支持多面试官、多设备（局域网）协同面试。

> 纯前端 + 本地后端架构，无需注册、无需上传数据到任何第三方；AI 能力可选接入 DeepSeek，不配置 Key 时内置 mock Provider 同样功能完整。

---

## 核心功能（均已实现）

- **候选人信息管理**：按面试顺序 Excel 一键导入（「同步名单」），支持姓名 / 学号 / 专业 / 岗位搜索、只看未面试
- **简历原件预览**：面试页内直接预览 **PDF / DOCX / DOC / TXT / MD**（Word 经本机 Word/WPS 转 PDF，与原件排版一致），支持大窗预览与下载；简历全程只读
- **四维度六星等级打分**：性格沟通 / 工作能力 / 发展潜力 / 综合评分（放大显示），加权总分实时计算
- **面试官管理**：下拉选择历史面试官 + 自由输入 + **锁定开关**（一位面试官连面一批候选人不用重填）
- **多轮面试**：同一候选人可多轮独立记录与得分；同一轮重复提交只更新一条记录
- **联评综合评分**：多面试官自动合并（每人先归一再平均，等权防刷分），支持**人工设定面试官权重**，附分歧度 σ 提示
- **权重设置**：维度权重 / 面试官权重人工设定，存后端数据库，所有设备共用，一键恢复默认
- **结果汇总**：按顺序 / 得分 / 联评综合分 / 自定义加权分 / 轮次 / 姓名排序，**按单个维度**、**按某位面试官**排序，行展开查看明细，统计卡片与等级分布
- **AI 总结与智能评估**：简历信息抽取（姓名 / 学号 / 专业 / 技能等）、面试总结、优势短板与建议，失败自动降级不影响流程
- **候选人详情页**：基本信息、轮次记录、维度明细、联评卡片、AI 结果
- **多端访问**：局域网模式，面试官用手机 / 平板 / 笔记本同时面试

## 技术栈

| 层 | 技术 |
|---|---|
| Frontend | React 18 + Vite 5 + Ant Design 5 + React Router 6 |
| Backend | Python 3.10+（开发环境 3.13）+ FastAPI + Uvicorn |
| Database | SQLite（Python 标准库 `sqlite3`，零额外依赖） |
| Excel / PDF | openpyxl（面试顺序表）、pypdf |
| AI | Provider 抽象层：`mock`（默认，零依赖）/ `deepseek`（OpenAI 兼容接口） |

## 项目结构

```
AI-Interview-System-OpenSource/
├─ config/
│  ├─ settings.py             # ★ 唯一配置源：路径 / 端口 / AI / 评分维度
│  └─ settings.example.json   # 可选覆盖配置示例（复制为 settings.json 使用）
├─ backend/
│  └─ app/
│     ├─ main.py              # FastAPI 入口 + 全局异常兜底（异常不崩服务）
│     ├─ db.py                # SQLite 数据访问层
│     ├─ ai/
│     │  ├─ provider.py       # ★ AI Provider 抽象（mock / deepseek，自动降级）
│     │  └─ prompts.py        # Prompt 模板集中管理
│     ├─ api/
│     │  ├─ candidates.py     # 候选人 / 简历 / 轮次记录
│     │  ├─ interview.py      # 面试流程（当前 / 下一位 / 上一位 / 提交）
│     │  ├─ results.py        # 结果汇总 / 多种排序 / 统计
│     │  ├─ weights.py        # 权重人工设定 API
│     │  └─ ai_routes.py      # AI 状态 / 单独立评估
│     └─ services/
│        ├─ resume_service.py          # 简历定位与文本抽取（只读）
│        ├─ interview_order_service.py # 面试顺序 Excel 读取
│        ├─ joint_service.py           # 联评综合评分（多面试官合并）
│        ├─ weights_service.py         # 权重持久化
│        └─ scoring_service.py         # 加权总分与等级
├─ frontend/
│  ├─ src/
│  │  ├─ api.js               # 前端唯一 API 出口（相对路径 /api）
│  │  ├─ App.jsx              # 布局与路由（5 个页面）
│  │  ├─ components/
│  │  └─ pages/               # 首页 / 面试页 / 候选人 / 结果汇总 / 详情
│  ├─ index.html
│  ├─ package.json
│  └─ vite.config.js          # /api 代理到后端，改端口只改这一处
├─ scripts/
│  ├─ start_all.bat           # 一键启动（本机模式）
│  ├─ start_all_lan.bat       # 一键启动（局域网模式）
│  ├─ start_backend*.bat      # 分别启动后端
│  ├─ start_frontend*.bat     # 分别启动前端
│  ├─ firewall_allow_lan.bat  # 局域网首次使用放行防火墙端口（一次性）
│  └─ make_test_data.py       # ★ 生成 5 名虚构候选人 + 简历 + 顺序 Excel
├─ tests/
│  ├─ run_all.py              # 一键跑全部测试
│  └─ test_*.py               # API / 流程 / 权重 / 浏览器 / 数据安全等套件
├─ .gitignore
├─ LICENSE
└─ README.md
```

## 环境要求

- **Python ≥ 3.10**（后端依赖：`fastapi`、`uvicorn`、`openpyxl`、`pypdf`）
- **Node.js ≥ 18** + npm（前端构建 / 开发服务器）
- 可选：本机安装 **Microsoft Word 或 WPS**（.doc / .docx 简历转 PDF 预览用；没有也能用，自动降级）
- 可选：**DeepSeek API Key**（不配置则使用内置 mock Provider）
- 可选：Playwright（仅运行浏览器自动化测试时需要）

## 安装方法

```bash
git clone https://github.com/<your-name>/AI-Interview-System.git
cd AI-Interview-System

# 后端依赖
pip install fastapi uvicorn openpyxl pypdf

# 前端依赖
cd frontend
npm install
```

Windows 用户也可以直接双击 `scripts\start_all.bat`（前端脚本会在 `node_modules` 缺失时自动 `npm install`）。

## 配置说明（重要）

本项目的配置集中在 `config/settings.py`（默认值），可选通过 `config/settings.json` 覆盖。

**切换 AI 到 DeepSeek 有两种方式（任选其一）：**

方式一：环境变量（推荐，优先级更高）

```bat
:: Windows (CMD)
set DEEPSEEK_API_KEY=sk-xxxxxxxx
set INTERVIEW_AI_PROVIDER=deepseek

:: Linux / macOS
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export INTERVIEW_AI_PROVIDER=deepseek
```

方式二：配置文件

```bash
# 1. 复制示例配置
cp config/settings.example.json config/settings.json   # Windows 用 copy
# 2. 编辑 config/settings.json：
#    "ai_provider": "deepseek"
#    "deepseek_api_key": "你的 Key"
# 3. 重启后端生效
```

> ⚠️ **不要将 `config/settings.json` 或 `.env` 上传到 GitHub** —— 它可能包含你的 API Key 与本机路径。它们已写入 `.gitignore`。仓库中只保留 `settings.example.json` 示例。

不配置任何 Key 时系统自动使用 mock Provider：抽取 / 总结 / 评估基于规则计算，功能完整可跑通，方便先行体验。

## 启动方法

```bash
# 方式一（Windows 一键启动）
scripts\start_all.bat

# 方式二（手动分别启动）
# 后端：
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 前端（新开终端）：
cd frontend
npm run dev
```

| 服务 | 地址 |
|---|---|
| 前端页面 | http://127.0.0.1:5173 |
| 后端 API 文档（Swagger） | http://127.0.0.1:8000/docs |
| 健康检查（含配置快照，不含密钥） | http://127.0.0.1:8000/api/health |

局域网模式（手机 / 平板 / 其他电脑访问）：`scripts\start_all_lan.bat`，首次使用先以管理员身份运行一次 `scripts\firewall_allow_lan.bat` 放行端口。

## 快速体验（生成 Demo 数据）

系统不带任何真实候选人数据。首次运行可生成 5 名**完全虚构**的候选人（张明 / 李雪 / 王强 等，学号 202201xx，电话为 138 开头测试号段）及其简历文本和面试顺序 Excel：

```bash
python scripts/make_test_data.py          # 只新增缺失文件，不覆盖已有数据
python scripts/make_test_data.py --force  # 强制重建（覆盖前自动备份为 .bak）
```

数据默认存放在数据目录（可用 `config/settings.json` 的 `e_root` / `resume_dir` / `db_path` 自定义，默认 `D:\InterviewSystem`，Windows 下也可按惯例配置为任意磁盘位置）。

## 使用说明

1. **启动系统**：运行后端 + 前端，浏览器打开 http://127.0.0.1:5173
2. **导入候选人**：把面试顺序 Excel 放入数据目录 → 候选人页点「同步名单」一键导入（或先用 `make_test_data.py` 生成演示数据）
3. **进入面试页**：显示当前候选人，左栏预览简历原件（PDF / Word / 文本）
4. **打分与评价**：四个维度六星评级 → 选择 / 锁定面试官 → 填写评价 → 保存（自动算加权总分，生成 AI 总结与智能评估）
5. **切换候选人**：「下一位 / 上一位」按面试顺序移动，进度持久化（刷新不丢）
6. **查看结果**：结果汇总页按各种口径排序、设定维度 / 面试官权重、查看统计与等级分布
7. **查看详情**：候选人详情页看轮次记录、联评明细、AI 评估
8. **多轮 / 联评**：需要多位面试官评同一人时各自「开新一轮」打分，系统自动合成联评综合分

## 测试

```bash
# 后端启动后运行
python tests/run_all.py            # 全部套件
python tests/run_all.py api        # 仅 API 测试
```

包含 API 正确性、业务闭环、评分权重、联评、数据安全（防重复 / 防覆盖）等套件；`test_browser.py` 需额外安装 Playwright（`pip install playwright && playwright install chromium`）。运行产生的报告与截图（可能含候选人信息）已由 `.gitignore` 排除。

## 安全与隐私设计

- 所有数据（候选人、评分、简历）只存在本机，不上传任何第三方
- 简历原件全程只读，转换预览缓存与源文件修改时间绑定自动失效
- 健康检查接口输出配置快照但**不含密钥明文**
- AI Key 支持环境变量注入，可完全不落盘

## 开源说明

本项目基于 [MIT License](./LICENSE) 开源。数据安全说明：仓库不含任何真实候选人数据；`tests/*_report.json` 与 `tests/screenshots/` 为运行时产物，已被 `.gitignore` 排除。
