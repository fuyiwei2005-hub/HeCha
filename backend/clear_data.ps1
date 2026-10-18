# PestGuard 演示数据清理
# 用法：
#   .\clear_data.ps1              默认 Mode=records：清文件 + 清检测记录 + 清聊天记录（保留账号）
#   .\clear_data.ps1 -Mode files  仅清文件（会同步把失去文件的记录一并删掉，避免出现 404 幽灵记录）
#   .\clear_data.ps1 -Mode all    连账号一起清（危险，需 -Force）
param(
    [ValidateSet('records','files','all')]
    [string]$Mode = 'records',
    [switch]$Force
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$data = Join-Path $root "data"
$py   = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($Mode -eq 'all' -and -not $Force) {
    Write-Host "Mode=all 会删除全部账号，请加 -Force 确认。" -ForegroundColor Red
    exit 1
}

# 全部清理逻辑放在一个 Python 脚本里，而不是 PowerShell 拼 SQL。
#
# 历史 bug：原来的 switch 只有 'all' 和 default 两个分支，
# 于是 -Mode files 落进 default，执行的是和 -Mode records 一模一样的
# `DELETE FROM chat_messages; DELETE FROM detections;` ——
# 演示前按文档跑 -Mode files 会把所有记录清光。
#
# 现在三种模式语义明确：
#   records → 清空所有检测记录与聊天（保留账号），并删掉对应文件
#   files   → 只删「没有任何记录指向」的孤儿文件；
#             并把「文件已不在磁盘」的记录删掉（避免 404 幽灵条目）
#   all     → 连账号一起清
$pyScript = @'
import os
import sqlite3
import sys

mode = sys.argv[1]
root = sys.argv[2]
data = os.path.join(root, "data")
db = os.path.join(root, "pestguard.db")

if not os.path.isfile(db):
    print("找不到数据库：%s" % db)
    print("提示：Docker/生产环境用的是 PostgreSQL，本脚本只适用于本地 SQLite。")
    sys.exit(1)

con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
cur = con.cursor()

try:
    rows = cur.execute(
        "SELECT id, stored_name, result_path FROM detections"
    ).fetchall()
except sqlite3.OperationalError as exc:
    print("读取 detections 失败：%s" % exc)
    con.close()
    sys.exit(1)

def path_of(sub, name):
    return os.path.join(data, sub, name) if name else None

# 每个 detection 实际引用的文件
referenced = set()
for r in rows:
    for sub, name in (("uploads", r["stored_name"]), ("results", r["result_path"])):
        p = path_of(sub, name)
        if p and os.path.isfile(p):
            referenced.add(os.path.realpath(p))


def delete_records(ids):
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    cur.execute("DELETE FROM chat_messages WHERE detection_id IN (%s)" % marks, ids)
    cur.execute("DELETE FROM detections WHERE id IN (%s)" % marks, ids)
    return len(ids)


if mode == "all":
    print("清空 chat_messages / detections / users")
    cur.executescript(
        "DELETE FROM chat_messages; DELETE FROM detections; DELETE FROM users;"
    )
    # 删掉两个目录下的全部文件
    for sub in ("uploads", "results"):
        d = os.path.join(data, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except OSError as exc:
                    print("  删除失败 %s: %s" % (fp, exc))
        print("cleared: %s" % d)

elif mode == "records":
    print("清空 chat_messages / detections（保留账号）")
    cur.executescript("DELETE FROM chat_messages; DELETE FROM detections;")
    for sub in ("uploads", "results"):
        d = os.path.join(data, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            # 保留 ultralytics 的配置缓存目录，它不是用户数据
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except OSError as exc:
                    print("  删除失败 %s: %s" % (fp, exc))
        print("cleared: %s" % d)

else:  # files
    # ① 删孤儿文件：磁盘上有、但没有任何记录指向
    removed_files = 0
    for sub in ("uploads", "results"):
        d = os.path.join(data, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            if not os.path.isfile(fp):
                continue
            if os.path.realpath(fp) in referenced:
                continue
            try:
                os.remove(fp)
                removed_files += 1
            except OSError as exc:
                print("  删除失败 %s: %s" % (fp, exc))
    print("删除孤儿文件：%d 个" % removed_files)

    # ② 删幽灵记录：记录还在，但它的所有文件都不在磁盘上了
    orphans = []
    for r in rows:
        names = [
            path_of("uploads", r["stored_name"]),
            path_of("results", r["result_path"]),
        ]
        names = [p for p in names if p]
        if names and all(not os.path.isfile(p) for p in names):
            orphans.append(r["id"])
    n = delete_records(orphans)
    print("删除幽灵记录：%d 条（保留仍有文件的记录）" % n)

con.commit()
con.close()
print("db ok")
'@

$pyScript | & $py -
if ($LASTEXITCODE -ne 0) {
    Write-Host "清理未成功完成（退出码 $LASTEXITCODE）" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 清掉遗留的 0 字节空库 data/pestguard.db（若存在）
$stray = Join-Path $data "pestguard.db"
if ((Test-Path $stray) -and ((Get-Item $stray).Length -eq 0)) {
    Remove-Item $stray -Force
    Write-Host "removed empty: $stray"
}

Write-Host "`nDone. mode=$Mode" -ForegroundColor Cyan
