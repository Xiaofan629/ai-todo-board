# AI Todo Board

[![GitHub](https://img.shields.io/badge/GitHub-Xiaofan629%2Fai--todo--board-blue?logo=github)](https://github.com/Xiaofan629/ai-todo-board)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 项目简介

一个智能待办事项管理系统，专为工作场景设计，解决多人协作中的任务遗忘问题。

## 解决的痛点

在日常工作中，我们经常面临这些问题：
- **消息遗忘**：各种渠道的留言和任务容易被遗忘
- **任务不透明**：团队成员无法清晰了解你的工作负载
- **操作繁琐**：需要打开网页才能新增或编辑待办事项
- **回顾困难**：难以追溯每周完成了哪些工作

## 核心功能

### 1. 企业微信机器人集成
- 直接通过企业微信发送消息创建待办事项
- 无需打开网页，随时随地快速记录
- 消息自动同步到 Todo Board
- 自动调用 Claude Code 总结内容生成标题

### 2. AI 智能处理
- 收到消息后自动通过 Claude Code 分析处理
- 智能提取任务关键信息
- Plan-only 模式：只分析不修改文件，输出项目改动建议
- 支持多轮对话继续追问

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

## 企业微信对话

![企业微信对话](https://raw.githubusercontent.com/Xiaofan629/my-image-host/refs/heads/main/a666bf9822e1bf3cc881f95c0e67ec76.jpg)

### 主界面 - 任务列表

![任务列表](https://raw.githubusercontent.com/Xiaofan629/my-image-host/refs/heads/main/1d1849b7601bc1362a9f7b1ee960b15d.png)

### 甘特图

![甘特图](https://raw.githubusercontent.com/Xiaofan629/my-image-host/refs/heads/main/f29efd7c189532f769ac0ab7ac2cd45d.png)


### 甘特图下载图片

![甘特图下载图片](https://raw.githubusercontent.com/Xiaofan629/my-image-host/refs/heads/main/7bf82ae14e2315ff8f24103d89918dd2.png)

<!-- 截图预留位结束 -->

## 快速开始

### 环境要求
- Python 3.8+
- Node.js 16+

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

**主要配置项：**
- `WECOM_BOT_ID` - 企业微信机器人 ID
- `WECOM_BOT_SECRET` - 企业微信机器人密钥
- `SERVER_PORT` - 服务端口（默认 9526）
- `ROOT_PATH` - 部署路径前缀（如 `/xiaofantodo`，根路径留空）
- `OWNER_NAME` - 所有者名称
- `CLAUDE_BIN` - Claude CLI 路径（默认 `claude`）
- `PROJECT_BASE_DIR` - 项目根目录（默认 `/home/sunxiaofan/zhihu`）

6. 启动服务
```bash
./start.sh
```

## 使用方式

### 通过企业微信创建任务
直接在企业微信群中 @机器人 发送任务描述即可，系统会：
1. 用消息内容第一行作为初始标题
2. 调用 Claude Code 分析处理
3. 处理完成后自动总结内容更新标题
4. 将分析结果回复到企业微信

### 通过网页管理
- 本地部署：访问 `http://localhost:9526`
- 子路径部署：访问 `http://your-domain.com/your-path/`（需配置 `ROOT_PATH` 和 `VITE_BASE_PATH`）
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
- **AI**：Claude Code CLI (stream-json)
- **甘特图导出**：html2canvas
- **集成**：企业微信机器人 WebSocket API

## License

MIT
