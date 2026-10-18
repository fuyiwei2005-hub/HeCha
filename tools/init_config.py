"""Initialize local configuration without copying secrets from the source archive."""
from pathlib import Path
import secrets
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def initialize():
    path = ROOT / 'backend' / '.env'
    if path.exists():
        return path
    lines = [
        'APP_ENV=development', f'SECRET_KEY={secrets.token_urlsafe(48)}',
        'DATABASE_URL=sqlite+aiosqlite:///./pestguard.db',
        'REDIS_URL=redis://127.0.0.1:6379/0',
        ('MODEL_PATH=../model_weights/best.pt' if importlib.util.find_spec('torch') and (ROOT / 'model_weights/best.pt').is_file() else 'MODEL_PATH='),
        ('ALLOW_MOCK_DETECTOR=false' if importlib.util.find_spec('torch') and (ROOT / 'model_weights/best.pt').is_file() else 'ALLOW_MOCK_DETECTOR=true'),
        'DEEPSEEK_API_KEY=', 'DEEPSEEK_BASE_URL=https://api.deepseek.com',
        'DEEPSEEK_MODEL=deepseek-chat',
    ]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


if __name__ == '__main__':
    print(f'Local configuration: {initialize()}')
