# 禾察公网部署指南

> **为什么必须部署**：大赛方案原文规定，仅限专网或校园网访问、无法通过公网访问的作品"将被视为无效参赛作品"。**公网可访问是硬性要求，不是加分项。**

---

## 一、整体流程（大约 1 小时）

```
买云主机 → 域名解析 → 跑一键脚本 → 配 Nginx → 申请 SSL → 验证
```

| 步骤 | 谁做 | 耗时 |
| --- | --- | --- |
| 买云主机 | 你 | 10 分钟 |
| 域名与解析 | 你 | 10 分钟（可跳过，用 IP 访问） |
| 跑 `deploy/setup.sh` | 脚本 | 20–30 分钟（主要是构建镜像） |
| 配 Nginx + SSL | 你，按本文件复制命令 | 15 分钟 |
| 验证 | 你 | 5 分钟 |

---

## 二、服务器选型

| 项 | 最低要求 | 建议 |
| --- | --- | --- |
| CPU | 2 核 | 2–4 核 |
| 内存 | 4 GB | 4–8 GB |
| 磁盘 | 40 GB | 60 GB（镜像较大） |
| 系统 | Ubuntu 22.04 / Debian 12 | Ubuntu 22.04 |
| 带宽 | 3 Mbps | 5 Mbps 以上 |
| 端口 | 开放 80 / 443 | 若用 IP 直连需开 8000 |

**不需要 GPU。** 模型在 CPU 上单图 78.6 ms / 12.7 FPS，2 核机器足够。这是本作品轻量化设计的直接收益。

> 国内云厂商（阿里云、腾讯云、华为云）都有学生优惠机，几十元/月。若服务器在境内且用域名，**域名需要备案**；若时间来不及，直接用 IP + 8000 端口访问也能满足"公网可访问"要求（只是摄像头拍照功能因无 HTTPS 不可用）。

---

## 三、部署步骤

### 第 1 步：上传代码

```bash
# 方式 A：服务器直接拉（推荐）
git clone https://github.com/fuyiwei2005-hub/HeCha.git pestguard && cd pestguard

# 方式 B：本地打包上传
#   注意 model_weights/best.pt 必须一并上传（约 10MB），它是检测能力的核心
```

### 第 2 步：跑一键脚本

```bash
cd pestguard
bash deploy/setup.sh
```

脚本会自动完成：安装 Docker → 生成强随机密钥的 `.env` → 构建镜像 → 启动服务 → 等待健康检查 → 打印自检结果。

> 默认启动的是 **5 个服务**：`api` / `worker` / `analysis-worker` / `db` / `redis`。
> 第 6 个 `frontend`（`web`）在 `profiles: ["web"]` 下，默认**不启动** ——
> 因为演示入口就是后端的 `:8000`，前端已由后端托管。
> 需要独立的 nginx 前端时：`docker compose --profile web up -d`（对外是 `:8080`）。
> 两种方式二选一，别同时暴露。

中途会问两个问题：
- **公网域名或 IP** → 填了会自动写进 `CORS_ORIGINS`
- **DeepSeek API Key** → **留空也能跑**，只是不生成防治建议

> ⚠️ 关于 API Key：`DEEPSEEK_API_KEY` 留空时系统自动关闭大模型建议，**检测主流程完全不受影响**。但若答辩要展示"AI 防治建议 + 引用溯源"这一幕，**必须填**。建议填上，成本很低。


### 第 3 步：配置 Nginx

```bash
sudo apt-get install -y nginx
sudo cp deploy/nginx-site.conf /etc/nginx/sites-available/pestguard
sudo sed -i 's/your-domain.com/你的实际域名/g' /etc/nginx/sites-available/pestguard
sudo ln -s /etc/nginx/sites-available/pestguard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

### 第 4 步：申请 SSL 证书

SSL 证书申请需要先让 80 端口可访问（Certbot 校验用），但配置文件里 443 段引用了尚不存在的证书，会导致 `nginx -t` 失败。顺序如下：

```bash
# 1) 先注释掉 nginx 配置里 ssl_certificate 那两行
sudo sed -i 's/^    ssl_certificate/    # ssl_certificate/' /etc/nginx/sites-available/pestguard

# 2) 启动 Nginx（此时只有 HTTP 段生效）
sudo nginx -t && sudo systemctl reload nginx

# 3) 申请证书
sudo apt-get install -y certbot
sudo certbot certonly --webroot -w /var/www/html -d 你的域名

# 4) 取消注释，恢复 SSL 配置
sudo sed -i 's/^    # ssl_certificate/    ssl_certificate/' /etc/nginx/sites-available/pestguard

# 5) 校验并重载
sudo nginx -t && sudo systemctl reload nginx
```

证书 90 天到期，Certbot 会自动配置续期定时任务。

### 第 5 步：确认代理信任设置

`TRUST_PROXY` 决定后端是否相信 `X-Forwarded-For` / `X-Real-IP`。
**它必须和你的实际架构匹配**，否则限流会失效或误伤：

| 你的部署方式 | 应设 | 原因 |
| --- | --- | --- |
| 系统 Nginx 反代到 8000（本文档第 3 步） | **`true`** | `deploy/nginx-site.conf` 会转发这两个头。不开的话后端看到的来源 IP 全是 `127.0.0.1`，登录限流退化成全局 10 次/分钟，多人同时注册就被 429 |
| 直接暴露 8000 端口（IP 直连） | **`false`** | 没有可信代理。开了的话任何人伪造 `X-Forwarded-For` 就能绕过限流 |
| `docker compose --profile web`（容器内 nginx） | **`true`** | `frontend/nginx.conf` 会转发这两个头；compose 已为 `web` profile 预设 |

修改方式（`TRUST_PROXY` 由 compose 从 `.env` 插值进容器）：

```bash
# 编辑 .env，把 TRUST_PROXY 改成 true/false
docker compose up -d          # 让 api/worker 重新读取环境变量
```

> ⚠️ 两个容易踩的坑：
> 1. `docker compose restart api` **不会**重新读取 `.env` —— `restart` 只重启容器进程，
>    环境变量在容器创建时就固定了。必须用 `up -d` 重建（compose 会就地更新）。
> 2. 改完请实际验证：连续快速注册几个账号，如果第 4 个之后就 429，
>    说明限流仍然按单个 IP 计数（可能是 `TRUST_PROXY` 没生效）。

---

## 四、验证清单

部署完成后逐项确认：

- [ ] `https://你的域名` 能打开首页
- [ ] 注册一个新账号能成功
- [ ] 上传 `测试_蚜虫.jpg` 能出 4 个边界框
- [ ] **防治建议区域有内容**（若为空，检查 `DEEPSEEK_API_KEY`）
- [ ] 点开引用编号能看到出处
- [ ] 上传视频能走完 pending → completed
- [ ] `/docs` 能打开
- [ ] **换一台设备、断开校园网，用手机流量访问** —— 这一步才是真正的公网验证

---

## 五、常见问题

**Q：构建镜像时特别慢 / 卡住？**
首次构建要装 PyTorch 等大依赖，20 分钟属正常。若超时，确认服务器能访问 PyPI，必要时换国内源。

**Q：容器起来了但检测返回空？**
检查 `MODEL_PATH=/models/best.pt` 且 `ALLOW_MOCK_DETECTOR=false`。用 `docker compose logs api` 看是否报模型加载错误。

**Q：能检测但没有防治建议？**
`DEEPSEEK_API_KEY` 为空。这是设计上的降级——大模型不可用时主流程照常工作。填上 Key 后 `docker compose restart api`。

**Q：摄像头拍照按钮没反应？**
该功能依赖 HTTPS。确认 SSL 已配好且用 `https://` 访问。用 IP 直连时该功能不可用，其余功能不受影响。

**Q：视频任务一直转圈不完成？**
多半是 Worker 没起来。执行 `docker compose ps` 确认 `worker` 服务是 Up 状态，或用 `docker compose logs worker` 查错。

**Q：磁盘不够？**
`docker system prune -a` 清理悬空镜像（谨慎，会清掉未使用的镜像）。

---

## 六、安全提醒

1. `.env` 含密钥，**绝对不要提交到 Git**。脚本已设权限 600。
2. 服务器安全组只开放必要端口（80/443，以及 SSH 的 22）。
3. 部署完成后立即修改默认 SSH 配置，禁用密码登录改用密钥。
4. 定期备份 `pest_uploads`、`pest_results` 与 `postgres_data` 三个数据卷
   （前两个是用户上传的图片与检测结果，知识库与寄主先验表在镜像内，无需备份）。

```bash
docker run --rm -v pestguard_pest_uploads:/data -v $(pwd):/backup \
  alpine tar czf /backup/pest_uploads_backup.tar.gz /data
docker run --rm -v pestguard_pest_results:/data -v $(pwd):/backup \
  alpine tar czf /backup/pest_results_backup.tar.gz /data
```
