"""Verify upgrading an existing 0008 database preserves results without new AI calls."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def main():
    with tempfile.TemporaryDirectory(prefix='pestguard_upgrade_') as directory:
        path = Path(directory) / 'old.db'
        os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{path.as_posix()}'
        cfg = Config('alembic.ini')
        command.upgrade(cfg, '0008_add_feedback')
        engine = create_engine(f'sqlite:///{path.as_posix()}')
        try:
            predictions = json.dumps([{'class': 'aphid', 'confidence': 1.15, 'raw_confidence': .92}])
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO users (id, email, password_hash, username, is_active) VALUES (1, 'test@example.invalid', 'hash', 'legacy_test', 1)"))
                for did, advice in [('with-advice', 'legacy advice'), ('without-advice', None)]:
                    connection.execute(text('INSERT INTO detections (id,user_id,media_type,original_name,stored_name,status,predictions,analysis) '
                        'VALUES (:id,1,\'image\',\'old.png\',:stored,\'completed\',:predictions,:analysis)'),
                        {'id': did, 'stored': did + '.png', 'predictions': predictions, 'analysis': advice})
            command.upgrade(cfg, 'head')
            with engine.connect() as connection:
                rows = connection.execute(text('SELECT id,analysis,analysis_status,predictions FROM detections ORDER BY id')).all()
                assert rows[0][0] == 'with-advice' and rows[0][1] == 'legacy advice' and rows[0][2] == 'completed'
                assert rows[1][0] == 'without-advice' and rows[1][1] is None and rows[1][2] == 'disabled'
                assert all(json.loads(row[3])[0]['raw_confidence'] == .92 for row in rows)
            print('PASS: existing results and advice survive upgrade; no advice auto-enqueued')
        finally:
            engine.dispose()


if __name__ == '__main__': main()
