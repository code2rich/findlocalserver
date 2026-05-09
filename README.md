# FindLocalServer

本地服务发现工具 —— 自动扫描本机所有监听端口和 Docker 容器，识别服务类型，提供 Web UI 进行管理。

## 功能特性

- **端口扫描** — 自动发现本机所有监听端口，支持 macOS / Linux / Windows
- **Docker 容器识别** — 自动发现运行中的容器及端口映射，从镜像名推断服务类型
- **HTTP 探测** — 异步探测 Web 服务标题、Server 头、页面类型（网页/API）
- **Banner 抓取** — TCP 协议指纹识别（MySQL、Redis、RabbitMQ、SSH 等）
- **服务管理** — 收藏、分组、健康检查
- **书签导出** — 一键导出为浏览器书签文件
- **零配置** — 开箱即用，可选 `config.yaml` 自定义

## 快速开始

### 环境要求

- Python 3.9+
- Docker（可选，用于容器发现）

### 安装与启动

```bash
# 克隆仓库
git clone https://github.com/code2rich/findlocalserver.git
cd findlocalserver

# 方式一：使用启动脚本（自动检查依赖）
./start.sh

# 方式二：手动安装
pip install -r requirements.txt
python main.py
```

启动后访问 http://localhost:9999

### 自定义配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 配置手动服务、忽略端口等
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python + FastAPI + Uvicorn |
| 端口扫描 | psutil / lsof / netstat / ss（自动回退） |
| HTTP 客户端 | httpx（异步） |
| Docker 集成 | docker-py |
| 前端 | Vue 3 + Tailwind CSS（CDN，零构建） |

## 项目结构

```
├── main.py              # FastAPI 应用入口，路由定义
├── app/
│   ├── scanner.py       # 端口扫描、HTTP/Banner 探测
│   ├── docker_scanner.py # Docker 容器发现
│   ├── models.py        # 数据模型（Service, ServiceType）
│   ├── config.py        # 配置加载
│   └── health.py        # 健康检查
├── static/              # 前端 SPA
├── data/                # 运行时数据（偏好设置）
├── config.example.yaml  # 配置模板
├── start.sh             # macOS/Linux 启动脚本
└── start.bat            # Windows 启动脚本
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/services` | 获取已发现的服务列表 |
| POST | `/api/services/refresh` | 重新扫描 |
| GET | `/api/services/{id}/health` | 单个服务健康检查 |
| POST | `/api/services/refresh-health` | 批量健康检查 |
| PUT | `/api/favorites/{id}` | 切换收藏 |
| PUT | `/api/services/{id}/group` | 设置分组 |
| GET | `/api/ips` | 获取本机 IP 列表 |
| GET | `/api/export/bookmarks` | 导出浏览器书签 |

## License

[MIT](LICENSE)
