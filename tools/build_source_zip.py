#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PestGuard 参赛源码打包脚本

用途：生成提交给组委会的「作品源代码」zip。

排除项（不是删文件，只是���打进包里）：
  - backend/.venv/        本地虚拟环境，1.6 GB，与平台相关
  - **/__pycache__/       字节码缓存
  - .git/ .idea/          版本库与 IDE 配置（属他人信息，不外传）
  - backend/_backups/     本地备份
  - _外部验证集/          233 张网图，其中 132 张为 CC BY-NC 禁商用，不可外发
  - _队友交图_待检/       组员原始交图，同上
  - 各类 *.db / *.log / node_modules

保留项（重要）：
  - model_weights/best.pt  模型权重 9.93 MB —— 缺了源码跑不起来，必须带
  - backend/data/knowledge/  知识库 69 条
  - docs/参赛材料/           设计文档等材料源文件
  - 根目录 4 张测试图         供评审复现

用法：
    python tools/build_source_zip.py
    python tools/build_source_zip.py --out D:/somewhere
"""

import argparse
import os
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 目录级排除（相对仓库根）
EXCLUDE_DIRS = {
    ".git", ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "__pycache__",
    "node_modules", "dist", "build", ".venv", "venv", "env",
    "_backups", "_外部验证集", "_队友交图_待检", "协作", ".cache", ".slidep",
    "redis",  # Windows 便携版 Redis，生产用 docker-compose 里的 redis:7.4-alpine
    # 输出目录：必须排除，否则脚本会把自己正在写的 zip 读进去，
    # 形成自反馈循环（上一次把包撑到 20GB 就是这个原因）
    "参赛打包",
}

# 文件级排除（扩展名 / 文件名）
EXCLUDE_EXT = {
    ".pyc", ".pyo", ".pyd", ".log", ".db", ".sqlite", ".sqlite3",
    ".onnx", ".tmp", ".bak", ".swp",
    # 归档文件一律不进包：内含压缩包会重复膨胀，且源码包本身没意义
    ".zip", ".7z", ".rar", ".tar", ".gz",
}

# SQLite 的旁路文件。os.path.splitext("x.db-wal") 得到 ".db-wal"，
# 不在上面的集合里，所以必须单独判后缀 —— 而 WAL 里可能含已提交的数据行
# （用户、密码哈希、聊天正文），漏掉它等于把数据库交出去。
EXCLUDE_SUFFIXES = (".db-wal", ".db-shm", ".db-journal", ".sqlite-wal", ".sqlite-shm")
# 运行时配置文件：里面是真实密钥，绝不能进交给评委的源码包。
# 只放 .env.example（占位示例），评审要运行就照它自己配。
#
# 参赛信息.json 与 .env 同级：里面有公网地址和演示账号密码。
# 上一版包（20261005）漏了这条规则，把测试账号密码一起交给了评委。
# 它是"填完即含密"的文件，所以连它的备份/变体一起按名字前缀拦掉。
_EXCLUDE_NAME_PREFIXES = ("参赛信息",)   # 只放行 参赛信息.example.json
EXCLUDE_NAMES = {
    ".DS_Store", "Thumbs.db", "pestguard.db", "pestguard_sim.db",
    ".env", ".env.local", ".env.production",
}

# 参赛信息.example.json 是占位模板，必须放行（EXCLUDE_NAMES 的显式豁免）
_KEEP_NAME_SUFFIXES = (".example.json",)

# 明确必须保留的（防止规则误伤）
FORCE_KEEP = {
    "model_weights/best.pt",
    "model_weights/training_metrics.json",
    "model_weights/training_curve.png",
}

MAX_FILE_MB = 200  # 单文件超过 200MB 跳过并告警


def should_skip_dir(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(p in EXCLUDE_DIRS for p in parts)


def should_skip_file(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel in FORCE_KEEP:
        return False
    name = os.path.basename(rel)

    # 占位模板先放行，别被下面的"参赛信息"前缀规则误伤
    if name.endswith(_KEEP_NAME_SUFFIXES):
        return False

    if name in EXCLUDE_NAMES:
        return True
    # "参赛信息.json" / "参赛信息-备份.json" / "参赛信息.20261005.json" 一律排除
    if name.startswith(_EXCLUDE_NAME_PREFIXES):
        return True
    if os.path.splitext(name)[1].lower() in EXCLUDE_EXT:
        return True
    if name.lower().endswith(EXCLUDE_SUFFIXES):
        return True
    # 排除根目录散落的测试视频（.gitignore 已声明不外传）
    if rel.startswith("测试_") and rel.endswith((".mp4", ".webm", ".mov")):
        return True
    return False


def collect() -> tuple:
    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")

        # 原地裁剪，避免走进排除目录
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and d != "__pycache__"
        ]
        if rel_dir and should_skip_dir(rel_dir):
            continue

        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            if should_skip_file(rel):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > MAX_FILE_MB * 1024 * 1024:
                skipped.append((rel, f"{size/1048576:.1f} MB"))
                continue
            files.append((full, rel, size))
    return files, skipped


def scan_secrets(files) -> list:
    """提交前最后一道防线：扫待打包的文本文件，找真实凭证。

    靠人工记着"这次没把 .env 放进去"是不可靠的 —— 规则一旦写漏，
    密钥就跟着源码包交到评委手里了。所以这里强制扫一遍内容，
    命中即中止打包，不留商量余地。
    """
    import re
    patterns = [
        ("DeepSeek API Key", re.compile(r"sk-[0-9a-f]{32}")),
        ("OpenAI API Key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
        ("通用私钥", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("阿里云 AccessKey", re.compile(r"LTAI[A-Za-z0-9]{12,}")),
        ("腾讯云 SecretId", re.compile(r"AKID[A-Za-z0-9]{20,}")),
        ("明文 JWT 密钥", re.compile(r"SECRET_KEY\s*=\s*[\"']?[A-Za-z0-9_\-]{16,}")),
        ("数据库口令", re.compile(r"(?i)(password|passwd|pwd)\s*=\s*[\"'][^\"'\s]{8,}[\"']")),
        # ---- 中文键名。上一版包漏掉的就是这一类：参赛信息.json 里的
        # 「测试密码」既不是 password= 也不是 sk- 形式，前几条规则全都没命中。
        ("中文凭据字段", re.compile(
            r"[\"']?(测试密码|测试用户名|测试账号|密码|口令|账号密码|"
            r"API[_ ]?密钥|密钥|AccessKey[_ ]?Secret|私钥)"
            r"[\"']?\s*[:=]\s*[\"']?([^\"',\s]{4,})")),
        # JSON 形态的英文口令：{"password": "xxx"}
        ("JSON 口令字段", re.compile(
            r"(?i)[\"'](password|passwd|pwd|secret|token|api_?key|username)[\"']"
            r"\s*:\s*[\"']([^\"']{6,})[\"']")),
    ]
    # 公网地址单独处理：它是"部署信息"而不是"密钥"，
    # 但同样不该随源码包外传。只认三种高置信度形态，
    # 否则会把 ultralytics 自带的几百个文档 URL 全报出来，警告就没人看了。
    addr_patterns = [
        # ① 真实可路由的 IPv4。内网/保留段与 0.0.0.0/1.1.1.1 之类公共 DNS 排除在外。
        ("公网 IP", re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")),
        # ② 明确写着"这是部署地址"的字段 —— 值必须真的像个地址。
        #    用两个捕获组包住整行前缀，使最后一个 group 就是地址本身
        #    （下面的"值不像真凭据就放过"逻辑依赖 lastindex 指向值）。
        ("部署地址字段", re.compile(
            r"([\"']?(?:公网地址|部署地址|服务器地址|演示地址|public[_ ]?url|"
            r"server[_ ]?url|deploy[_ ]?url)[\"']?\s*[:=]\s*[\"']?)"
            r"(https?://[\w.:/-]+|\d{1,3}(?:\.\d{1,3}){3}\S*)")),
        # ③ 内网穿透域名（cpolar/ngrok 之类），演示机入口
        ("内网穿透域名", re.compile(
            r"[\w-]+\.(?:cpolar\.(?:top|cn|io)|ngrok(?:-free)?\.(?:io|app)|"
            r"trycloudflare\.com|natapp(?:free)?\.(?:cc|cn))")),
    ]
    # 这些域名是文档/依赖里的正常内容，不是自建服务入口
    addr_ok = re.compile(
        r"(?i)localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org|net)|"
        r"your-domain|yourdomain|xxx\.|api\.deepseek\.com|"
        r"ultralytics|github\.com|python\.org|docker\.com|googleapis|gstatic|"
        r"w3\.org|pytorch\.org|nvidia\.com|readthedocs|schemas\.|json-schema|"
        r"creativecommons|apache\.org|opensource\.org|pypi\.org|npmjs")

    def is_public_ip(a: str, b: str, c: str, d: str) -> bool:
        """排除私网/保留/回环段与公共 DNS，只留真正可路由到某台机器的地址。"""
        o = [int(x) for x in (a, b, c, d)]
        if any(x > 255 for x in o):
            return False
        if o[0] in (0, 10, 127, 224, 225, 226, 227, 228, 229, 230, 231, 232,
                    233, 234, 235, 236, 237, 238, 239, 255):
            return False
        if o[0] == 172 and 16 <= o[1] <= 31:      # 172.16/12
            return False
        if o[0] == 192 and o[1] == 168:           # 192.168/16
            return False
        if o[0] == 169 and o[1] == 254:           # link-local
            return False
        if o[0] == 100 and 64 <= o[1] <= 127:     # CGNAT
            return False
        if o[0] == 1 and o[1] == 1 and o[2] == 1:  # 1.1.1.1
            return False
        if o[0] == 8 and o[1] == 8:                # 8.8.8.8
            return False
        if o[3] == 0:                              # 网络地址
            return False
        # 至少三段大于 30，才不像版本号（如 pandas 4.12.0.88）
        if sum(1 for x in o if x > 30) < 3:
            return False
        return True

    text_ext = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml",
                ".ini", ".cfg", ".sh", ".conf", ".html", ".ts", ".tsx", ".js", ".vue"}
    hits = []
    # 一看就是测试/占位的串要豁免，否则会把测试用例里的假密码当成真凭证，
    # 一路误报下去的结果就是没人再看这个警告
    benign = re.compile(
        r"(?i)(test|example|sample|dummy|mock|placeholder|changeme|change[-_]me|"
        r"replace[-_]with|xxxx|待填|todo|fake|dummy|your[-_])")
    # 这些字段名本身就是要填凭据的位置，不做 benign 豁免：
    # 模板里的占位值（如"填演示账号密码"）留在源码包里会误导，
    # 而真正填过的值更是必须拦下。宁可让作者把它改成 example 模板。
    strict_field = re.compile(
        r"测试密码|测试用户名|测试账号|账号密码|API[_ ]?密钥|公网地址|部署地址")
    # localhost / 示例域名是正常的开发文档内容，不该被"公网地址"规则误伤
    local_ok = re.compile(
        r"(?i)localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org)|"
        r"your-domain|xxx\.|yourdomain|api\.deepseek\.com|googleapis\.com|gstatic\.com|"
        r"w3\.org|cpolar\.top|ipv4|schemas\.|github\.com|python\.org|docker\.com")
    # 文档里用占位符代替真实地址是**正确做法**，不该被当成泄露拦下来
    placeholder_ok = re.compile(r"<[^>]*(?:IP|服务器|地址|域名|填)[^>]*>|请填写|你的域名")
    # 真实凭据几乎一定含数字或符号（带年份的口令、sk- 前缀的密钥等）；
    # 纯中文词句（"填演示账号密码"）是模板叮嘱，不是凭据。
    # 靠这一条把"模板占位"和"真的填过了"区分开。
    looks_real = re.compile(r"[0-9@_\-!.#$%^&*+=]")
    for full, rel, size in files:
        ext = os.path.splitext(full)[1].lower()
        # .env 之类无扩展名的文件也要扫（上次就是它漏的）
        no_ext = os.path.splitext(os.path.basename(full))[1] == ""
        if ext not in text_ext and not no_ext:
            continue
        if size > 4 * 1024 * 1024:  # 跳过超大文本，避免拖慢
            continue
        # 官方 ultralytics 源码是第三方依赖，内有几百个文档 URL，
        # 扫它只会淹没真正的告警，且它本来就不该出现我们的凭据。
        if rel.startswith("backend/ultralytics/"):
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
        except OSError:
            continue
        for line in body.splitlines():
            if len(line) > 500:      # 超长行（压缩/日志）不参与匹配
                continue
            for label, pat in patterns:
                m = pat.search(line)
                if not m:
                    continue
                # localhost / 示例域名 / 公共 CDN 不算泄露
                if local_ok.search(line):
                    continue
                # 行内出现凭据字段名时不走 benign 豁免：占位模板本身也该由作者
                # 改成 .example，而不是留在源码包里。
                strict = bool(strict_field.search(line))
                if not strict and (benign.search(m.group(0)) or benign.search(line)):
                    continue        # 明显是测试串，放过
                # 模板里的纯中文叮嘱（"填演示账号密码"）不是凭据；
                # 但只要值里出现数字或符号，就当成真填过，必须拦。
                value = m.group(m.lastindex) if m.lastindex else m.group(0)
                if strict and not looks_real.search(value):
                    continue
                hits.append((label, rel, m.group(0)[:40]))
                break

            if local_ok.search(line) or placeholder_ok.search(line):
                continue
            addr_label = None
            addr_sample = ""
            for label, pat in addr_patterns:
                am = pat.search(line)
                if not am:
                    continue
                if label == "公网 IP":
                    if not is_public_ip(*am.groups()):
                        continue
                    # 只有"测试专用"那几个地址才按所在行豁免，
                    # 不因为行里出现 test/example 就放过一个真实公网 IP
                    if am.group(0) in {"1.2.3.4", "9.9.9.9", "5.6.7.8", "2.2.2.2",
                                       "3.3.3.3", "4.4.4.4", "1.1.1.1"}:
                        continue
                elif label == "部署地址字段":
                    # 值必须是真地址。模板里的 "https://请填写" 只是叮嘱，
                    # 真填过的地址一定含数字（IP）或完整域名后缀。
                    val = am.group(am.lastindex) if am.lastindex else am.group(0)
                    if not looks_real.search(val):
                        continue
                addr_label, addr_sample = label, am.group(0)[:40]
                break
            if addr_label and not addr_ok.search(line):
                hits.append((addr_label, rel, addr_sample))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="输出目录，默认写到 参赛打包/")
    ap.add_argument("--allow-secrets", "--allow-private-info",
                    dest="allow_secrets", action="store_true",
                    help="明知含敏感串也要打包（仅限本地自测用，后果自负）")
    args = ap.parse_args()

    out_dir = args.out or os.path.join(ROOT, "参赛打包")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    zip_path = os.path.join(out_dir, f"PestGuard源代码_{stamp}.zip")

    # 双保险：即使 EXCLUDE_DIRS 漏配了输出目录，也绝不把归档产物打进归档。
    # 自反馈会让包体积指数级膨胀（实测撑到 20GB），且不会报错，只会耗尽磁盘。
    out_real = os.path.realpath(out_dir)
    files, skipped = collect()
    before = len(files)
    files = [
        (f, r, s) for f, r, s in files
        if not os.path.realpath(f).startswith(out_real + os.sep)
    ]
    dropped = before - len(files)
    if dropped:
        print(f"  已剔除 {dropped} 个位于输出目录内的文件（防自反馈）")
    total = sum(s for _, _, s in files)

    print(f"待打包文件 {len(files)} 个，合计 {total/1048576:.1f} MB")

    # 密钥泄露扫描：命中就中止，绝不把凭证交出去
    hits = scan_secrets(files)
    if hits:
        print("\n" + "!" * 70)
        print("打包中止：检测到疑似真实凭证")
        print("!" * 70)
        for label, rel, sample in hits:
            print(f"  [{label}] {rel}\n      {sample}")
        print("\n处理办法：把真实值移出待打包文件（如 .env 已被排除但仍命中，")
        print("说明密钥写进了 .py/.md 里，改成读环境变量即可）。")
        if not args.allow_secrets:
            return 2
        print("  （--allow-secrets 已开启，继续打包，后果自负）")
    else:
        print("  凭证扫描：未发现真实密钥  OK")

    if skipped:
        print(f"\n跳过 {len(skipped)} 个超大文件：")
        for rel, why in skipped:
            print(f"  - {rel}  ({why})")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for full, rel, _ in files:
            zf.write(full, arcname=f"PestGuard/{rel}")

    final = os.path.getsize(zip_path)
    print(f"\n输出：{zip_path}")
    print(f"压缩后体积：{final/1048576:.1f} MB")

    # 关键文件自检
    print("\n关键文件自检：")
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        must = [
            "PestGuard/model_weights/best.pt",
            "PestGuard/backend/Dockerfile",
            "PestGuard/backend/requirements.txt",
            "PestGuard/docker-compose.yml",
            "PestGuard/README.md",
            "PestGuard/backend/data/host_prior.json",          # 运行时必需，缺了先验功能失效
        ]
        for m in must:
            print(f"  {'OK  ' if m in names else 'MISS'} {m}")
        kb = [n for n in names if "/data/knowledge/" in n]
        print(f"  {'OK  ' if kb else 'MISS'} 知识库文件 {len(kb)} 个")
        venv = [n for n in names if "/.venv/" in n]
        print(f"  {'OK  ' if not venv else 'WARN'} 虚拟环境已排除（残留 {len(venv)} 项）")

        # 凭据自检：参赛信息.json 必须不在包里。
        # 这一条是补上 20261005 那次事故 —— 规则写漏了，谁也没发现。
        leaked = [n for n in names
                  if os.path.basename(n).startswith("参赛信息")
                  and not n.endswith(".example.json")]
        env_leaked = [n for n in names
                      if os.path.basename(n) in {".env", ".env.local", ".env.production"}]
        print(f"  {'OK  ' if not leaked else 'FAIL'} 参赛信息.json 已排除"
              + (f"（残留 {leaked}）" if leaked else ""))
        print(f"  {'OK  ' if not env_leaked else 'FAIL'} .env 已排除"
              + (f"（残留 {env_leaked}）" if env_leaked else ""))
        example_kept = [n for n in names if n.endswith("参赛信息.example.json")]
        print(f"  {'OK  ' if example_kept else 'WARN'} 参赛信息.example.json 模板保留")
        if leaked or env_leaked:
            print("\n打包产物含凭据，请勿提交！删除该 zip 并修好排除规则后重跑。")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
