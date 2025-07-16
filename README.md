# GitHub Trending Feishu MCP

一个基于 MCP (Model Context Protocol) 的 GitHub Trending 监控工具，可以自动抓取 GitHub 热门仓库，使用 AI 分析并筛选出 AI 相关项目，最后推送到飞书群。

## 功能特性

- 📊 **GitHub Trending 监控**: 自动抓取 GitHub 周热门仓库
- 🤖 **AI 智能筛选**: 使用通义千问 AI 分析项目是否与 AI 相关
- 📝 **README 自动摘要**: 自动生成项目描述摘要
- 🚀 **飞书推送**: 自动推送格式化的消息卡片到飞书群
- 🔄 **MCP 协议支持**: 基于 Model Context Protocol 构建

## 系统要求

- Python 3.11+
- uv 包管理器
- 通义千问 API 密钥

## 安装和配置

1. 克隆项目：
```bash
git clone <repository-url>
cd github_trending-feishu-mcp
```

2. 安装依赖：
```bash
uv sync
```

3. 配置通义千问 API：
   - 确保 TROP_MODULE_PATH 指向正确的通义千问模块路径
   - 配置相关 API 密钥

4. 配置飞书 Webhook：
   - 在 `main.py` 中修改 `FEISHU_WEB_HOOK` 为你的飞书机器人 Webhook 地址
   - 确保模板 ID 和版本号正确

## 使用方法

### 作为 MCP 服务器运行

在 cline 或其他 MCP 客户端中配置：

```json
{
  "mcpServers": {
    "demo": {
      "disabled": false,
      "timeout": 180,
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/github_trending-feishu-mcp",
        "run",
        "main.py"
      ],
      "autoApprove": [
        "polish_trending_repos"
      ]
    }
  }
}
```

### 可用的 MCP 工具

1. **polish_trending_repos()**: 
   - 抓取 GitHub Trending 仓库
   - 使用 AI 分析和筛选 AI 相关项目
   - 生成项目描述摘要
   - 保存结果到 `filtered_trendings/trendings_YYYY-MM-DD.json`

2. **send_to_feishu()**: 
   - 生成飞书卡片格式的消息
   - 推送到配置的飞书群

### 独立运行

```bash
uv run main.py
```

## 核心功能

### 1. GitHub Trending 抓取

- 从 GitHub Trending 页面抓取周热门仓库
- 提取仓库名称、URL、star 数量、今日增长等信息
- 支持重试机制和错误处理

### 2. AI 智能筛选

- 使用通义千问 AI 分析项目的 README 内容
- 判断项目是否与 AI 相关
- 生成 100-150 字的项目描述摘要
- 支持多重错误处理和格式转换

### 3. 飞书推送

- 生成符合飞书卡片规范的消息格式
- 支持多种颜色标签和富文本格式
- 自动推送到指定的飞书群

## 输出格式

### 筛选结果 (trendings_YYYY-MM-DD.json)
```json
{
  "repo-name": {
    "url": "https://github.com/owner/repo",
    "stars": "1,234",
    "today_stars": "56",
    "description": "AI 生成的项目描述摘要..."
  }
}
```

### 飞书卡片格式 (template_YYYY-MM-DD.json)
```json
{
  "summary": "本周 AI 相关趋势总结...",
  "repos": [
    {
      "description": "[项目名](链接) ⭐Total Star:1234 ⭐Today's Star:56\n项目描述...\n<text_tag color='red'>AI</text_tag><text_tag color='blue'>机器学习</text_tag>"
    }
  ]
}
```

## 目录结构

```
github_trending-feishu-mcp/
├── main.py                 # 主程序文件
├── pyproject.toml          # 项目配置
├── README.md              # 项目文档
├── filtered_trendings/    # 筛选结果目录
│   ├── trendings_YYYY-MM-DD.json    # 筛选后的仓库数据
│   └── template_YYYY-MM-DD.json     # 飞书卡片模板数据
├── trendings_YYYY-MM-DD.json       # 原始抓取数据
└── test.ipynb             # 测试笔记本
```

## 注意事项

1. 确保网络连接正常，能够访问 GitHub API
2. 配置正确的通义千问 API 密钥和路径
3. 飞书 Webhook 地址和模板 ID 需要正确配置
4. 建议定期清理旧的数据文件
5. 如果遇到 API 限制，可以适当增加重试间隔
