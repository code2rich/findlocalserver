#!/bin/bash
# FindLocalServer 启动脚本 (macOS / Linux)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"
HOST="0.0.0.0"
PORT="9999"

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    -p|--port)
      PORT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --install)
      echo "安装依赖..."
      $PYTHON -m pip install -r requirements.txt
      echo "安装完成"
      exit 0
      ;;
    *)
      echo "FindLocalServer - 本地服务发现工具"
      echo ""
      echo "用法: $0 [选项]"
      echo ""
      echo "选项:"
      echo "  -p, --port PORT    指定端口 (默认: 9999)"
      echo "  --host HOST        指定监听地址 (默认: 0.0.0.0)"
      echo "  --install          安装 Python 依赖"
      echo ""
      echo "环境变量:"
      echo "  PYTHON             指定 Python 解释器路径 (默认: python3)"
      echo ""
      echo "示例:"
      echo "  $0                 # 启动服务 http://localhost:9999"
      echo "  $0 -p 8080         # 使用 8080 端口启动"
      echo "  PYTHON=python3.11 $0  # 指定 Python 版本"
      echo "  $0 --install       # 安装依赖"
      exit 0
      ;;
  esac
done

# 检查 Python 可用性
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "错误: 找不到 Python ($PYTHON)"
  echo "请安装 Python 3.9+ 或通过 PYTHON 环境变量指定路径"
  exit 1
fi

# 检查依赖
if ! $PYTHON -c "import fastapi" 2>/dev/null; then
  echo "依赖未安装，正在安装..."
  $PYTHON -m pip install -r requirements.txt
fi

# 按平台检查端口占用
OS="$(uname -s 2>/dev/null || echo unknown)"
case "$OS" in
  Darwin)
    if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      PID=$(lsof -ti ":$PORT")
      if [ -n "$PID" ]; then
        echo "端口 $PORT 已被占用 (PID: $PID)，尝试释放..."
        kill "$PID" 2>/dev/null
        sleep 1
      fi
    fi
    ;;
  Linux)
    if command -v ss >/dev/null 2>&1; then
      PID=$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K\d+' | head -1)
    elif command -v lsof >/dev/null 2>&1; then
      PID=$(lsof -ti ":$PORT" 2>/dev/null)
    fi
    if [ -n "$PID" ]; then
      echo "端口 $PORT 已被占用 (PID: $PID)，尝试释放..."
      kill "$PID" 2>/dev/null
      sleep 1
    fi
    ;;
esac

echo "====================================="
echo "  FindLocalServer 启动中..."
echo "  系统: $OS"
echo "  地址: http://localhost:$PORT"
echo "  按 Ctrl+C 停止"
echo "====================================="

$PYTHON -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
