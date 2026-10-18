from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# SQLite 默认不开外键约束，ON DELETE CASCADE 不会生效；这里显式打开
# WAL：让读不被写阻塞。API 进程和 ARQ worker 是两个进程在写同一个库文件，
# 不开 WAL 时并发写直接抛 "database is locked"，表现为上传偶发 500。
# busy_timeout：抢不到写锁先自旋等待 15 秒，而不是立刻失败。
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    # 整个函数体都必须在 sqlite 判断之内。
    # PRAGMA 不是合法的 PostgreSQL 语法，而 SQLAlchemy 的 asyncpg 方言
    # 会把语句原样发给服务端 —— 之前这里把 PRAGMA foreign_keys=ON 写在
    # 判断之前，于是 docker-compose 用的 postgresql+asyncpg 上
    # **每一条新建连接都会报语法错误**，整条 Postgres 路径直接不可用。
    # 之所以一直没暴露：本地和线上实际部署用的都是 SQLite。
    if not str(settings.database_url).startswith("sqlite"):
        return
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        # 某些 SQLite 构建（或内存库）不支持全部 PRAGMA，忽略即可。
        pass
    finally:
        cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

