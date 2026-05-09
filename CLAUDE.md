# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

FindLocalServer — 本地服务发现工具。自动扫描本机监听端口和 Docker 容器，通过 HTTP 探测和 banner 抓取识别服务类型，提供 Web UI 进行管理（收藏、分组、健康检查、书签导出）。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt
# 或通过启动脚本
./start.sh --install

# 启动服务（默认 http://localhost:9999）
./start.sh                    # macOS/Linux
start.bat                     # Windows
python main.py                # 直接运行
python -m uvicorn main:app --port 9999  # uvicorn 方式

# 指定端口
./start.sh -p 8080
```

无测试框架、无构建步骤、无 lint 配置。

## 架构概览

**技术栈**: Python 3.9+ / FastAPI + Uvicorn / Vue 3 (CDN) + Tailwind CSS (CDN)

后端为单体 FastAPI 应用，前端为无构建步骤的 SPA。

### 核心扫描流水线 (`do_scan` in main.py)

1. `scanner.scan_ports()` — 端口扫描，优先 psutil，按平台回退到 lsof/netstat/ss
2. `docker_scanner.scan_docker_containers()` — Docker 容器发现，与端口扫描结果合并去重
3. `scanner.probe_http()` — 异步 HTTP 探测（标题、Server 头、页面类型判断）
4. `scanner.probe_banners()` — TCP banner 抓取（MySQL/Redis/RabbitMQ 等协议识别）
5. 与 `config.yaml` 手动服务定义合并 → 去重 → 应用用户偏好 → 排序返回

### 模块职责

- **`main.py`** — FastAPI 路由定义、启动初始化、缓存管理、偏好持久化（`data/preferences.json`）
- **`app/scanner.py`** — 跨平台端口扫描（4种后端）、HTTP 探测、banner 探测、已知端口映射表 `KNOWN_PORTS`
- **`app/docker_scanner.py`** — 通过 Docker SDK 发现容器端口映射，从镜像名推断服务类型
- **`app/models.py`** — `Service` dataclass（通过 host:port:protocol 的 MD5 生成 id）和 `ServiceType` 枚举
- **`app/config.py`** — YAML 配置加载（`config.yaml`，不存在则用默认值），深度合并
- **`app/health.py`** — HTTP/TCP 健康检查，支持批量并发

### 前端

- `static/index.html` — Vue 3 组件模板 + 页面结构
- `static/app.js` — Vue 3 应用逻辑（Composition API）
- `static/style.css` — 自定义样式
- 通过 CDN 加载 Vue 3 和 Tailwind CSS，无 npm/webpack

### 配置

复制 `config.example.yaml` 为 `config.yaml` 进行配置。支持手动服务定义、端口/进程忽略、HTTP 探测开关、刷新间隔、服务监听地址。
