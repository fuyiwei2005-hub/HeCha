#!/usr/bin/env bash
# PestGuard 一键部署脚本（公网服务器）
#
# 用法（在一台全新的 Ubuntu 22.04 / Debian 12 云主机上）：
#
#   curl -fsSL <你的仓库地址>/deploy/setup.sh -o setup.sh
#   bash setup.sh
#
# 或者把整个项目上传到服务器后：
#
#   cd pestguard && bash deploy/setup.sh
#
# 脚本会做：装 Docker → 生成强密钥 .env → 构建镜像 → 启动全部服务 → 等健康检查 → 自检
# 脚本不会做：买服务器、解析域名、申请 SSL（这三步见 deploy/README.md）

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[info]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }

# ---------- 0. 定位项目根目录 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
info "项目目录：$ROOT"

# ---------- 1. 检查必需文件 ----------
for f in docker-compose.yml model_weights/best.pt backend/Dockerfile; do
    if [[ ! -f "$f" ]]; then
        err "缺少 $f —— 请确认整个项目已完整上传（注意 model_weights/best.pt 必须存在）"
        exit 1
    fi
done

# 运行时必需的数据文件。它们不是构建产物、也不是密钥，必须随代码分发；
# 曾经因为 .gitignore 里整体忽略了 backend/data/，用 git clone 部署时
# 这些文件缺失，表现为「检测能用，但防治建议没有引用溯源」
# （RAG 静默降级），而健康检查完全看不出来。所以这里显式拦住。
for f in backend/data/host_prior.json \
         backend/data/knowledge/pests_cereal.json \
         backend/data/knowledge/pests_fruit.json \
         backend/data/knowledge/pesticide.json \
         backend/data/knowledge/practice.json; do
    if [[ ! -f "$f" ]]; then
        err "缺少运行时数据文件 $f"
        err "  这不是可选项：缺了「寄主先验」和「引用溯源」会静默失效。"
        err "  如果你是用 git clone 拿到的代码，检查 .gitignore 是否忽略了 backend/data/。"
        exit 1
    fi
done
info "必需文件检查通过（含模型权重与运行时知识库）"

# ---------- 2. 安装 Docker ----------
if ! command -v docker >/dev/null 2>&1; then
    info "未检测到 Docker，开始安装..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://get.docker.com | sh
    info "Docker 安装完成"
else
    info "Docker 已安装：$(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
    err "docker compose 插件不可用，请升级 Docker 到 20.10+"
    exit 1
fi

# ---------- 3. 生成 .env ----------
if [[ -f .env ]]; then
    warn ".env 已存在，保留不动（如需重生成请先删除）"
else
    info "生成 .env 与强随机密钥..."
    SECRET_KEY="$(openssl rand -hex 32)"
    POSTGRES_PASSWORD="$(openssl rand -hex 16)"

    cat > .env <<EOF
# ---- 由 deploy/setup.sh 自动生成，请勿提交到仓库 ----
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
SECRET_KEY=${SECRET_KEY}

# 容器内的模型路径（docker-compose 已把 model_weights 挂载到 /models）
MODEL_PATH=/models/best.pt
# 生产环境禁用 mock 检测器，未加载真实模型时直接报错，避免静默返回假结果
ALLOW_MOCK_DETECTOR=false
# 构建镜像时安装 YOLO 运行时依赖（必须 true，否则容器内无法推理）
INSTALL_YOLO=true

# 部署后改成你的实际域名，多个用逗号分隔
CORS_ORIGINS=http://localhost:8000

# ---- 大模型防治建议（可选）----
# 留空则自动关闭大模型建议，检测主流程不受影响
# 填入后系统才会生成防治建议（答辩第四幕依赖此项）
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# ---- 反向代理后开启（配合 Nginx 使用）----
# 置 true 才会信任 X-Forwarded-For；直接暴露端口时保持 false
TRUST_PROXY=false
EOF
    chmod 600 .env
    info ".env 已生成（权限 600）"
fi

# ---------- 4. 交互确认域名与 API Key ----------
echo
read -r -p "请输入公网域名或服务器 IP（用于 CORS，直接回车跳过）： " DOMAIN
if [[ -n "${DOMAIN:-}" ]]; then
    SCHEME="https"
    [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && SCHEME="http"
    sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${SCHEME}://${DOMAIN}|" .env
    info "CORS_ORIGINS 已设为 ${SCHEME}://${DOMAIN}"
fi

echo
read -r -p "请输入 DeepSeek API Key（留空则不启用防治建议，检测功能不受影响）： " DSKEY
if [[ -n "${DSKEY:-}" ]]; then
    sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=${DSKEY}|" .env
    info "DeepSeek API Key 已写入"
else
    warn "未填写 API Key —— 系统仍可正常检测，但不会生成防治建议"
fi

# ---------- 5. 构建并启动 ----------
info "开始构建镜像（首次构建需下载依赖，可能需要 10–20 分钟，请耐心等待）..."
docker compose build

info "启动服务..."
docker compose up -d

# ---------- 6. 等待健康检查 ----------
info "等待服务就绪..."
for i in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        info "服务已就绪（耗时 ${i}0 秒内）"
        break
    fi
    if [[ $i -eq 60 ]]; then
        err "服务启动超时，请查看日志：docker compose logs api"
        exit 1
    fi
    sleep 10
done

# ---------- 7. 自检 ----------
echo
info "========== 部署自检 =========="
echo "容器状态："
docker compose ps --format "table {{.Service}}\t{{.Status}}" 2>/dev/null || docker compose ps
echo
HEALTH="$(curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null || echo 'unreachable')"
echo "健康检查： $HEALTH"
echo
info "========== 完成 =========="
echo "本地访问： http://127.0.0.1:8000"
[[ -n "${DOMAIN:-}" ]] && echo "公网访问： ${SCHEME}://${DOMAIN}（需先完成 Nginx + 域名解析，见 deploy/README.md）"
echo
echo "常用命令："
echo "  查看日志   docker compose logs -f api"
echo "  重启       docker compose restart"
echo "  停止       docker compose down"
echo "  更新代码   git pull && docker compose up -d --build"
echo
warn "下一步：按 deploy/README.md 配置 Nginx 反向代理与 SSL 证书"
warn "（摄像头拍照功能依赖 HTTPS，未配 SSL 时该功能不可用，其余功能不受影响）"
