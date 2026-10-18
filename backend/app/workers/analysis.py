"""Advice runs independently so a long video cannot hold up image advice."""
from arq.connections import RedisSettings
from app.core.config import get_settings
from app.core.database import engine
from app.services.analysis_jobs import process_analysis

settings = get_settings()


class WorkerSettings:
    functions = [process_analysis]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = settings.analysis_queue_name
    max_jobs = 4
    job_timeout = settings.analysis_job_timeout_seconds + 10
    max_tries = 1
    keep_result = 0

    @staticmethod
    async def on_shutdown(ctx):
        await engine.dispose()
