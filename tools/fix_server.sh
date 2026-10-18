#!/usr/bin/env bash
# ============================================================
# PestGuard 服务器修复脚本（诊断 + 修复）
# 症状：首页能打开，但所有检测接口返回 500
#
# 用法：
#   SERVER_IP=<你的服务器IP> bash fix_server.sh
#   ssh root@<你的服务器IP> 'bash fix_server.sh'
#
# 注意：不要把真实服务器地址写回这个文件 —— 源码包是要交给评委的，
# 公网入口属于部署信息，不该随源码外传（打包脚本会拦下来）。
# ============================================================
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/pestguard}"
BACKEND="$APP_DIR/backend"
SERVER_IP="${SERVER_IP:-<请设置 SERVER_IP>}"
API_URL="${API_URL:-http://${SERVER_IP}:8000}"

echo "=========================================="
echo " PestGuard 服务器诊断"
echo " 时间：$(date '+%F %T')"
echo "=========================================="

# ---------- 1. 进程与端口 ----------
echo ""
echo "[1/6] 检查服务进程与端口"
if command -v ss >/dev/null 2>&1; then
    ss -lntp | grep -E ':8000' || echo "  !! 8000 未监听"
else
    netstat -lntp 2>/dev/null | grep ':8000' || echo "  !! 8000 未监听"
fi
ps aux | grep -E 'uvicorn|gunicorn|python.*app' | grep -v grep | head -5 || echo "  !! 未找到应用进程"

# ---------- 2. Python 与依赖 ----------
echo ""
echo "[2/6] 检查 Python 环境"
cd "$BACKEND" || { echo "!! 找不到 $BACKEND，请先上传代码"; exit 1; }
echo "  当前目录：$(pwd)"
echo "  Python：$(python3 -V 2>&1)"
# 优先使用项目自带的虚拟环境
if [ -f .venv/bin/activate ]; then
    echo "  发现 .venv，切换到虚拟环境"
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi
echo "  pip alembic：$(python3 -c 'import alembic; print(alembic.__version__)' 2>&1)"
echo "  fastapi：$(python3 -c 'import fastapi; print(fastapi.__version__)' 2>&1)"

# ---------- 3. 数据库定位 ----------
echo ""
echo "[3/6] 定位数据库"
DB_URL=$(grep -E '^DATABASE_URL' .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$DB_URL" ]; then
    # 与 backend/.env.example 保持一致
    DB_URL="sqlite+aiosqlite:///./pestguard.db"
    echo "  .env 未配置 DATABASE_URL，使用默认：$DB_URL"
else
    echo "  DATABASE_URL=$DB_URL"
fi

# ---------- 4. 诊断 Detection 表结构 ----------
echo ""
echo "[4/6] 诊断 Detection 表实际字段"

# 用环境变量把DB_URL 传进 Python
export DB_URL
python3 - <<'PY'
import os
import sqlite3

url = os.environ.get("DB_URL", "") or "sqlite+aiosqlite:///./pestguard.db"

# 只处理 sqlite；MySQL / PostgreSQL 请手工执行 SHOW COLUMNS FROM detections;
if not url.startswith("sqlite"):
    print(f"  当前 DATABASE_URL 非 SQLite（{url}）")
    print("  请手工执行：SHOW COLUMNS FROM detections; 并对照下方应有字段")
    sys_exit = True
else:
    sys_exit = False

if not sys_exit:
    # sqlite:///./x.db-> ./x.db；sqlite:////abs/x.db -> /abs/x.db
    # 不能简单 lstrip("/")：那会把绝对路径的首层斜杠也吃掉。
    path = url.split("///", 1)[1] if "///" in url else url
    if url.startswith("sqlite:////"):
        path = "/" + path
    path = path[5:] if path.startswith("file:") else path

    if not os.path.exists(path):
        print(f"  !! 数据库文件不存在：{path}")
        print(f"     找找实际文件：find {os.path.dirname(path) or '.'} -name '*.db' 2>/dev/null")
    else:
        con = sqlite3.connect(path)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  数据库：{path}")
        print(f"  表：{', '.join(tables) or '(空)'}")

        if "detections" not in tables:
            print("  !! detections 表不存在 -> 需要完整跑一次迁移")
        else:
            cur.execute("PRAGMA table_info(detections)")
            have = {r[1] for r in cur.fetchall()}
            need = {
                "id", "user_id", "media_type", "original_name", "stored_name",
                "predictions", "result_path", "analysis", "references",
                "video_meta", "crop", "status", "error", "created_at",
            }
            missing = sorted(need - have)
            print(f"  detections 现有字段（{len(have)}）：{', '.join(sorted(have))}")
            if missing:
                print("")
                print(f">>> 缺失 {len(missing)} 个字段：{', '.join(missing)}")
                print("    这就是 500 的根因。执行第 5 步修复。")
            else:
                print("  字段完整，500 另有原因，请查看服务日志（第 6 步）")
        con.close()
PY

# ---------- 5. 修复：补齐迁移 ----------
echo ""
echo "[5/6] 修复 —— 补齐数据库迁移"
echo "  当前迁移版本："
python3 -m alembic current 2>&1 | sed 's/^/    /'
echo "  目标版本：head（0007_add_crop）"
echo ""

# SQLite 下 alembic 的 batch 模式对 ALTER 支持有限，
# 若迁移失败则用下面的重建法兜底。
if python3 -m alembic upgrade head 2>&1 | sed 's/^/    /'; then
    echo ""
    echo "  ✅ alembic upgrade head 执行完成"
else
    echo ""
    echo "  ⚠️ alembic 迁移失败，改用兜底方案：删除旧库重建"
    read -r -p "  确认删除并重建数据库？会丢失现有用户与检测记录（输入 yes 继续）：" ans
    if [ "$ans" = "yes" ]; then
        # 先备份
        BK="${DB_URL#sqlite:///}"
        BK="${BK#//}"
        if [ -f "$BK" ]; then
            cp "$BK" "$BK.bak.$(date +%s)" && echo "  已备份到 $BK.bak"
            rm -f "$BK"
        fi
        # 重建
        python3 - <<'PY'
from app.models.base import Base
from app.core.database import engine
import app.models  # noqa: F401  确保所有模型被注册
Base.metadata.create_all(bind=engine.sync_engine)
print("  ✅ 表结构已按当前模型重建（注意：这是最新结构，含全部列）")
PY
    else
        echo "  已取消，请手工处理"
    fi
fi

# ---------- 6. 重启并验证 ----------
echo ""
echo "[6/6] 重启服务"
echo "  提示：先看服务是怎么起的，再按同样方式重启"
echo "  常见方式："
echo "    systemctl restart pestguard"
echo "    或  pkill -f uvicorn && cd $BACKEND && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "  ⚠️ 若用 systemd，重启后确认日志：journalctl -u pestguard -n 50 --no-pager"
echo ""
echo "=========================================="
echo " 完成后在浏览器打开验证："
echo "    ${API_URL}/api/health"
echo "  期望：{\"status\":\"ok\",...} 且 redis 不再是 error"
echo ""
echo "  再验证检测（口令自行替换）："
echo "    POST ${API_URL}/api/auth/register  {\"username\":\"t1\",\"password\":\"<自行设置>\"}"
echo "=========================================="
