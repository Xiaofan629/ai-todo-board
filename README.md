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

### 2. AI 智能处理
- 首次收到消息时自动通过 Claude Code 处理
- 智能提取任务关键信息
- 自动分类和优先级建议

### 3. 对话式交互
- 在网页中针对特定会话继续提问
- 上下文关联，深入讨论任务细节
- AI 辅助任务拆解和规划

### 4. 可视化看板
- 清晰展示所有待办事项
- 实时显示任务堆积情况
- 团队成员可见，提高协作透明度

### 5. 周报回顾
- 自动汇总每周完成的任务
- 一目了然的工作成果展示
- 便于复盘和总结

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
npm run build
cd ..
```

5. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的企业微信机器人配置
```

6. 启动服务
```bash
./start.sh
```

## 使用方式

### 通过企业微信创建任务
直接在企业微信群中 @机器人 发送任务描述即可

### 通过网页管理
访问 `http://localhost:9526` 查看和管理所有任务

## 技术栈

- **后端**：Python + FastAPI
- **前端**：React + TypeScript
- **AI**：Claude API
- **集成**：企业微信机器人 API

## License

MIT
