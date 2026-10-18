from functools import lru_cache
from pathlib import Path
import secrets

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 相对路径一律锚定到 backend/，而不是进程的当前工作目录。
# 之前用 Path("data/uploads")，一旦从别的目录启动（快捷方式、IDE、systemd），
# 文件就会写到另一个 data/ 里去，表现为「上传成功但结果图 404」。
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend/app/core/config.py → backend

# 一眼可见的占位/示例密钥。这些串在网上流传、也写在各种教程里，
# 放到公网等于把签名密钥公开 —— 必须拦，且不看环境。
_WEAK_SECRET_BLACKLIST = {
    "changeme", "changeme-please", "secret", "password", "pestguard",
    "development-only-secret-change-me-please",
    "replace-with-at-least-32-random-characters",
    "your-secret-key", "your_secret_key",
}
_WEAK_SECRET_PREFIXES = (
    "development-only", "replace-with", "your-", "your_", "example", "TODO",
)


def _anchor(value: Path) -> Path:
    return value if value.is_absolute() else (_BACKEND_ROOT / value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    product_frontend: str = Field(default="react", pattern="^(react|legacy)$")
    app_name: str = "禾察 API"
    app_env: str = "development"
    # 不设默认值 —— 之前写死 "development-only-secret-change-me-please"，
    # 公网部署时忘了配的话，任何人都能照着源码里的这串伪造 JWT 冒充任意用户。
    # （实测过：用占位串签出的 token 命中了线上 /api/auth/me 返回真实用户数据）
    # 为空时按环境处理：production 直接拒绝启动，开发/测试临时随机生成。
    secret_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./pestguard.db"
    # 用 127.0.0.1 而非 localhost：Windows 上 localhost 优先解析为 IPv6 ::1，
    # 而项目自带的 Redis 5.0 Windows 版只监听 IPv4，会导致连接超时
    redis_url: str = "redis://127.0.0.1:6379/0"
    task_backend: str = Field(default="redis", pattern="^(redis|local)$")
    analysis_queue_name: str = "arq:analysis"
    model_path: str = ""
    allow_mock_detector: bool = True
    # 视频抽帧用的阈值。图片走的下面那套 TTA，不用这个值。
    # 0.35 而不是 0.4：181 张人工复核图实测 640 单尺度下 minC 0.25~0.35 都是
    # 43.6%，0.4 掉到 41.4% —— 0.4 这条线砍掉的真框比它滤掉的误检更多。
    conf_threshold: float = 0.35
    # ── 图片检测：全图 + 局部切片 测试时增强（TTA）─────────────────────
    # 切片是唯一真正有效的增强。把图切四块各自按原始分辨率送进网络，
    # 小目标在切片里不会被整图缩放压扁 —— 红蜘蛛这类毫米级螨虫全靠它救。
    # 181 张人工复核图实测 Top-1：
    #   640 全图            43.6%（成本 1x）
    #   + 2x2 切片          49.2%（成本 5x）  ← 采用
    #   再叠 960/1280/1600  47.5%~44.8%（成本 9~42x，越堆越差）
    # 「多跑几遍一定更准」是错的：权重是 640 训的，把目标放大到训练分布之外
    # 反而更糟。所以这里刻意只保留 640 一个尺度。
    detect_tta: bool = True
    detect_scales: str = "640"
    # 0 = 关切片。2 = 切 2x2 四块，每块单独推理（块间留 25% 重叠防切到目标）
    detect_tiles: int = 2
    # 征集候选框时的低阈值（先多捞，再按 detect_min_conf 筛）
    detect_gather_conf: float = 0.15
    # 最终保留框的最低置信度。实测 0.30 最优：再低误判暴涨，再高漏检暴涨
    detect_min_conf: float = 0.30
    # 同类框空间聚集度加成。真害虫常成片出现，孤立噪声框不该被当成主要害虫。
    # 实测 0.6 最优（0.0 时 45.9% → 0.6 时 48.6%）
    detect_cluster_bonus: float = 0.6
    # 开发期常见来源：Vite 默认 5173、端口被占自动顺延到 5174/5175、以及用 IP 直接访问。
    # 缺了 127.0.0.1 与备用端口会导致登录请求被浏览器 CORS 拦截。
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )
    max_image_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    image_concurrency: int = Field(default=2, ge=1, le=16)
    image_queue_size: int = Field(default=8, ge=0, le=100)
    image_queue_timeout_seconds: float = Field(default=15, gt=0)
    maintenance_interval_seconds: float = Field(default=5, gt=0)
    analysis_job_timeout_seconds: int = Field(default=90, ge=15)
    job_heartbeat_timeout_seconds: int = Field(default=90, ge=30)
    max_video_bytes: int = 100 * 1024 * 1024
    upload_dir: Path = Path("data/uploads")
    result_dir: Path = Path("data/results")
    # 演示/路演场景页面会长时间停留，30 分钟太短，容易被无声登出
    access_token_minutes: int = 60 * 12   # 12 小时
    # 视频任务多久没动静就算超时。Worker 忘了启动（或 Redis 里的任务丢了）时，
    # 记录会永远停在 queued，前端就一直转圈——这里给它一个明确的终点。
    # 演示场景下评委不会为一个视频等 15 分钟，5 分钟足够覆盖正常处理 + 排队。
    video_job_timeout_minutes: int = 5
    # 是否信任 X-Forwarded-For。只有部署在可信反向代理后面才应打开，
    # 否则任何人伪造这个头就能绕过登录/注册限流。
    trust_proxy: bool = False

    # DeepSeek 二次解读（可选）：留空则自动关闭，不影响 YOLO 主流程
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    # Provider timeout within the independent advice job.
    deepseek_timeout: int = 12
    # 关闭思考模式用的 extra_body 参数，格式是 {"键": {子键: 值}} 的 JSON。
    # 之所以做成可配置：这段是**厂商私有**参数，不是 OpenAI 标准字段。
    #   DeepSeek : {"thinking": {"type": "disabled"}}
    #   阿里百炼  : {"enable_thinking": false}
    #   纯非思考模型（qwen-max 等）: 置空字符串，不发送该参数
    # 换了 base_url 却留着 DeepSeek 的参数，运气好被忽略、运气差直接 400，
    # 而 LLM 是"任何失败都降级"的可选增强 —— 用户只会看到「建议生成失败」，
    # 不报错、不进日志、极难排查。默认值保持 DeepSeek 现状不变。
    deepseek_thinking_param: str = '{"thinking": {"type": "disabled"}}'

    @field_validator("secret_key", mode="after")
    @classmethod
    def _resolve_secret(cls, value: str, info) -> str:
        """弱密钥黑名单对所有环境生效 —— 不管 app_env 是什么，
        可预测的密钥都等同于没有密钥，不能因为"这是开发环境"就放行。"""
        data = getattr(info, "data", None) or {}
        env = str(data.get("app_env") or "development").lower()
        v = (value or "").strip()

        if v:
            lowered = v.lower()
            if lowered in _WEAK_SECRET_BLACKLIST or any(
                    lowered.startswith(p) for p in _WEAK_SECRET_PREFIXES):
                raise ValueError(
                    "SECRET_KEY 是可预测的占位值，等同于没有密钥。"
                    "请生成随机串：python -c \"import secrets;print(secrets.token_urlsafe(48))\""
                )
            if env == "production" and len(v) < 32:
                raise ValueError("production 环境下 SECRET_KEY 必须不少于 32 个字符")
            return v

        # 未配置
        if env == "production":
            raise ValueError(
                "production 环境必须在环境变量中显式提供 SECRET_KEY（32 位以上随机串），"
                "拒绝带默认密钥启动，否则等于把鉴权大门敞开。"
            )
        # 本地开发/测试：临时生成一个，重启即失效（登录态会掉，但总比弱密钥强）
        return secrets.token_urlsafe(48)

    @field_validator("upload_dir", "result_dir", mode="after")
    @classmethod
    def _absolute_dirs(cls, value: Path) -> Path:
        return _anchor(value)

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def validate_production(self) -> None:
        unsafe_values = {"replace-with-at-least-32-random-characters", "changeme"}
        if self.app_env == "production" and (
            self.secret_key.startswith("development")
            or self.secret_key.lower() in unsafe_values
            or len(self.secret_key) < 32
        ):
            raise RuntimeError("Production requires a strong SECRET_KEY (32+ characters)")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.result_dir.mkdir(parents=True, exist_ok=True)
    return settings
