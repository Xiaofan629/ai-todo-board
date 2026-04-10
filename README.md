# AI Todo Board

[![GitHub](https://img.shields.io/badge/GitHub-Xiaofan629%2Fai--todo--board-blue?logo=github)](https://github.com/Xiaofan629/ai-todo-board)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 项目简介

一个智能待办事项管理系统，专为工作场景设计，解决多人协作中的任务遗忘问题。支持企业微信和飞书双平台机器人接入。

## 解决的痛点

在日常工作中，我们经常面临这些问题：
- **消息遗忘**：各种渠道的留言和任务容易被遗忘
- **任务不透明**：团队成员无法清晰了解你的工作负载
- **操作繁琐**：需要打开网页才能新增或编辑待办事项
- **回顾困难**：难以追溯每周完成了哪些工作

## 核心功能

### 1. 多平台机器人集成
- **企业微信**：通过 WebSocket 长连接接收消息，流式回复
- **飞书**：通过 WebSocket 长连接接收消息，REST API 回复
- 通过 `.env` 中的 `BOT_TYPE` 切换平台
- 引用回复自动识别并继续对应会话（企微按内容匹配，飞书按消息 ID 精确匹配）
- 无需打开网页，随时随地快速记录

### 2. AI 智能处理
- 收到消息后自动通过 LLM（Claude/GLM 等）分析处理
- 智能提取任务关键信息
- 支持多轮对话继续追问
- 首次创建时 AI 总结标题

### 3. 串行任务队列
- 一次只处理一个任务（doing 状态），其余排队等待
- 完成后自动提升下一个待处理任务
- 支持拖拽排序调整优先级
- 插队时需填写原因，记录在任务卡片上

### 4. 可视化看板
- 清晰展示所有待办事项，含序号和状态标签
- 多维筛选：按状态、时间范围（近7天/近30天/全部）、关键词搜索
- 卡片展示任务标题、内容预览、发送人、创建时间
- 拖拽排序：拖拽待处理任务调整优先级，拖到首位自动切换为进行中

### 5. 甘特图视图
- 点击甘特图按钮弹窗查看时间线
- 按时间范围筛选的任务自动渲染为甘特图
- 颜色编码：蓝色=进行中、绿色=已完成、黄色菱形=待处理、橙色菱形=插入
- 左侧标题列可拖拽调整宽度
- 支持导出为 PNG 图片
- 今日标记线（红色虚线脉冲动画）

## 截图

<!-- 截图预留位 -->

## 机器人对话

| 企业微信 | 飞书 |
|:---:|:---:|
| ![企业微信对话](https://xiaofan-image.oss-cn-beijing.aliyuncs.com/notion/790c3f974d6d9872c11756c8239028cf.jpg) | ![飞书对话](https://xiaofan-image.oss-cn-beijing.aliyuncs.com/notion/1775840432101.png) |

### 主界面 - 任务列表

![任务列表](https://xiaofan-image.oss-cn-beijing.aliyuncs.com/notion/0bb4fe12b61e969ddcd825f8f6731324.png)

### 甘特图

![甘特图](https://xiaofan-image.oss-cn-beijing.aliyuncs.com/notion/21ad34f01fef294ee4d1f6d53c324d88.png)


### todo 总结

![todo总结](https://xiaofan-image.oss-cn-beijing.aliyuncs.com/notion/043c7a7ad1088b5498c069f97896e271.png)


<!-- 截图预留位结束 -->

## 快速开始

### 环境要求
- Python 3.12
- Node.js v23.11.1

### 安装步骤

1. 克隆项目
```bash
git clone https://github.com/Xiaofan629/ai-todo-board.git
cd ai-todo-board
```

2. 创建并激活虚拟环境

**方法 A：使用 venv（推荐，macOS/有权限的 Linux）**
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

**方法 B：使用 virtualenv（Linux 服务器无 root 权限）**
```bash
# 安装 virtualenv
pip3 install --user virtualenv

# 创建虚拟环境
python3 -m virtualenv venv
# 或
virtualenv venv

# 激活
source venv/bin/activate
```

3. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

4. 安装前端依赖并构建
```bash
cd frontend
npm install
# 如果部署在子路径下（如 /xiaofantodo/），需要指定 VITE_BASE_PATH
VITE_BASE_PATH=/xiaofantodo/ npm run build
# 如果部署在根路径，直接运行
# npm run build
cd ..
```

5. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

6. 配置 MCP 工具（可选）
```bash
cp mcp_config.json.example mcp_config.json
# 编辑 mcp_config.json，配置你的 MCP 服务（stdio 或 sse 类型）
# 此文件包含密钥，已被 .gitignore 忽略
```

**主要配置项：**
- `BOT_TYPE` - 机器人类型：`wecom`（企业微信）或 `feishu`（飞书）
- `WECOM_BOT_ID` / `WECOM_BOT_SECRET` - 企业微信机器人凭证
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` - 飞书应用凭证
- `SERVER_PORT` - 服务端口（默认 9526）
- `ROOT_PATH` - 部署路径前缀（如 `/xiaofantodo`，根路径留空）
- `OWNER_NAME` - 所有者名称
- `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` - LLM 配置
- `PROJECT_BASE_DIR` - 项目根目录
- `MCP_CONFIG_PATH` - MCP 配置文件路径（默认 `./mcp_config.json`）

7. 启动服务
```bash
./start.sh
```

## 机器人配置

根据 `BOT_TYPE` 选择对应平台的配置，只需配置一个即可。

### 企业微信 AI 助手

1. 登录 企业微信
2. 进入「通讯录」→ 创建 智能机器人
3. 编辑 -> API配置中选择「使用长链接」
4. 在 `.env` 中配置：
   ```
   BOT_TYPE=wecom
   WECOM_BOT_ID=你的BotID
   WECOM_BOT_SECRET=你的BotSecret
   ```

**工作原理**：通过 WebSocket 长连接（`wss://openws.work.weixin.qq.com`）接收用户消息，使用 `aibot_subscribe` 订阅，通过 `aibot_respond_msg` 流式回复。

### 飞书机器人

1. 登录 [飞书开放平台](https://open.feishu.cn/app) → 创建应用
2. 开启「机器人」能力
3. 在「事件与回调」中开启 **WebSocket 长连接**模式
4. 添加以下权限并开通：

| 权限 | 权限标识 | 用途 |
|------|---------|------|
| 获取通讯录基本信息 | `contact:contact.base:readonly` | 基础通讯录访问 |
| 获取用户基本信息 | `contact:user.base:readonly` | 解析发送人姓名 |
| 获取与更新群组信息 | `im:chat` | 群组管理 |
| 查看群信息 | `im:chat:read` | 读取群信息 |
| 获取群组中用户@机器人消息 | `im:message.group_at_msg:readonly` | 接收群聊 @消息 |
| 读取用户发给机器人的单聊消息 | `im:message.p2p_msg:readonly` | 接收单聊消息 |
| 以应用的身份发消息 | `im:message:send_as_bot` | 发送回复消息 |
| 获取与上传图片或文件资源 | `im:resource` | 图片/文件处理 |

5. 发布应用版本，在「版本管理与发布」中提交审核
6. 在 `.env` 中配置：
   ```
   BOT_TYPE=feishu
   FEISHU_APP_ID=你的AppID
   FEISHU_APP_SECRET=你的AppSecret
   ```

**工作原理**：通过 WebSocket 长连接接收消息事件（`im.message.receive_v1`），通过 `lark-oapi` SDK 的 REST API 发送回复。

## 使用方式

### 通过机器人创建任务

**企业微信**：在对话中发送消息即可，系统会：
1. 用消息内容第一行作为初始标题
2. 调用 AI 分析处理
3. 处理完成后自动总结内容更新标题（仅首次）
4. 将分析结果流式回复到企业微信

**飞书**：在对话中发送消息即可，行为同上。

**引用回复**：引用 bot 的某条回复消息，可继续该任务的多轮对话，系统会自动匹配到对应的 Todo。

### 通过网页管理
- 本地部署：访问 `http://localhost:9526`
- 子路径部署：访问 `http://your-domain.com/your-path/`（需配置 `ROOT_PATH` 和 `VITE_BASE_PATH`）
- 点击标题可手动编辑
- 点击甘特图按钮查看任务时间线
- 拖拽待处理任务调整优先级

### 后台运行
```bash
nohup ./start.sh > output.log 2>&1 &
# 查看日志
tail -f output.log
# 停止服务
lsof -ti:9526 | xargs kill -9
```

## 技术栈

- **后端**：Python + FastAPI + SQLite (aiosqlite)
- **前端**：React 18 + TypeScript + Tailwind CSS 3 + Vite 6
- **甘特图导出**：html2canvas
- **机器人集成**：企业微信 AI 助手 WebSocket API、飞书 WebSocket + lark-oapi SDK

## AI Agent 架构

系统内置了一个基于 LangChain 的 AI Agent，用于智能分析处理用户消息，支持工具调用和多轮对话。

### 框架与模型

- **Agent 框架**：LangChain (`langchain` + `langchain-anthropic`)，使用 `create_agent` 构建 ReAct Agent
- **LLM 模型**：通过 `langchain-anthropic.ChatAnthropic` 接入，兼容 Claude / GLM 等模型（通过 `LLM_BASE_URL` 切换）
- **MCP 集成**：`langchain-mcp-adapters` 的 `MultiServerMCPClient` 动态加载外部 MCP 工具服务
- **流式输出**：通过 `agent.astream_events` 实现流式响应，实时推送到企微/飞书

### 内置工具

Agent 内置了以下 4 个基础工具：

| 工具 | 说明 |
|------|------|
| `bash_read` | 执行只读 shell 命令（白名单机制，仅允许 `cat`/`ls`/`grep`/`git log` 等只读命令，拦截 `rm`/`sed -i`/`curl -X POST` 等写入操作） |
| `project_summary` | 获取项目目录结构（`tree` 或 `find`），支持指定子目录，最多 3 层深度 |
| `reply_to_user` | 回复用户消息（Agent 每次对话必须调用此工具，否则用户收不到回复） |
| `investigate` | 启动结构化排查流程（查数据库 → 查日志 → 查指标 → 汇总结论），引导 Agent 按步骤排查问题 |

### MCP 扩展工具

通过 `mcp_config.json` 配置外部 MCP 服务，支持两种传输协议：

- **stdio**：本地启动子进程（如数据库查询 CLI、自定义脚本）
- **sse**：连接远程 MCP 服务（如数据库查询服务、监控指标服务等）

配置示例见 `mcp_config.json.example`。Agent 启动时自动加载所有 MCP 工具，与内置工具一起提供给 LLM 使用。

### Agent 工作流程

```
用户消息 → Bot（企微/飞书）→ main.py → langchain_agent.py
                                                  │
                                          create_agent (ReAct)
                                                  │
                                    ┌─────────────┼─────────────┐
                                    │             │             │
                              内置 Tools     MCP Tools    ChatAnthropic
                              (bash_read,   (数据库查询,    (Claude/GLM)
                               project_     日志服务...)
                               summary,
                               reply_to_user,
                               investigate)
                                    │
                              reply_to_user → 流式回复 → 企微/飞书
```

### 安全机制

- **命令白名单**：`bash_read` 仅允许预定义的只读命令（`cat`/`head`/`tail`/`ls`/`find`/`grep`/`rg`/`git` 只读子命令等）
- **写入拦截**：屏蔽 `rm`/`mv`/`pip install`/`curl -X POST` 等危险操作
- **Git 只读**：仅允许 `git log`/`git diff`/`git status` 等只读子命令，禁止 `git push`/`git commit` 等
- **输出截断**：单次工具输出超过 10000 字符自动截断
- **超时控制**：工具执行超时 30 秒自动终止

## 项目结构

```
├── main.py              # FastAPI 主服务，REST API + 消息处理
├── database.py          # SQLite 数据库操作层
├── config.py            # 环境变量配置
├── langchain_agent.py   # LangChain Agent 调用封装
├── agent_bridge.py      # Agent 桥接层
├── bot_base.py          # Bot 抽象基类
├── wecom_ws.py          # 企业微信 WebSocket 客户端
├── feishu_ws.py         # 飞书 WebSocket 客户端
├── frontend/            # React 前端
│   └── src/
│       ├── App.tsx      # 主应用组件
│       ├── api.ts       # API 客户端
│       ├── types.ts     # TypeScript 类型定义
│       └── components/  # UI 组件
├── mcp_config.json      # MCP 工具配置（需自行创建，已 gitignore）
├── .env                 # 环境变量（已 gitignore）
└── requirements.txt     # Python 依赖
```

## License

MIT
