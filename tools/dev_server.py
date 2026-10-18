"""Run only this project's processes; Ctrl+C shuts down owned child processes."""
import argparse
import json
import secrets
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from init_config import initialize

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.5)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--redis', action='store_true', help='Use external Redis and separate workers.')
    parser.add_argument('--api-only', action='store_true', help='Image demonstration without workers; use Redis for videos and advice.')
    args = parser.parse_args()
    if listening(args.port):
        raise SystemExit(f'Port {args.port} is already in use. Select --port or stop the existing service yourself.')
    if args.redis and not args.api_only and not listening(6379):
        raise SystemExit('Redis is not listening on 6379. Start Redis, or use --api-only for an image demonstration.')
    if not (BACKEND / 'static/index.html').is_file():
        raise SystemExit('Missing backend/static/index.html; restore the complete project package.')
    initialize()
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'}
    env['TASK_BACKEND'] = 'redis' if args.redis and not args.api_only else 'local'
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, env=env, check=True)
    commands = [[sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(args.port)]]
    if args.redis and not args.api_only:
        commands.extend([[sys.executable, '-m', 'arq', 'app.workers.video.WorkerSettings'],
                         [sys.executable, '-m', 'arq', 'app.workers.analysis.WorkerSettings']])
    log_dir = ROOT / 'output' / 'local'
    log_dir.mkdir(parents=True, exist_ok=True)
    processes, logs = [], []
    session = secrets.token_urlsafe(24)
    state_file = log_dir / 'runtime.json'
    stop_file = log_dir / 'stop.request'

    try:
        for index, command in enumerate(commands):
            log = (log_dir / f'process-{index}.log').open('a', encoding='utf-8')
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        for _ in range(180):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f'A service exited. Check logs in {log_dir}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/health', timeout=1): pass
                break
            except Exception:
                time.sleep(.5)
        else:
            raise RuntimeError(f'Service startup timed out. Check logs in {log_dir}')
        state_file.write_text(json.dumps({'session': session, 'port': args.port}), encoding='utf-8')
        print(f'Ready: http://127.0.0.1:{args.port}/  |  Logs: {log_dir}', flush=True)
        print('Press Ctrl+C to stop this project. Desktop tasks run locally without Redis.', flush=True)
        if os.environ.get('PESTGUARD_OPEN_BROWSER') == '1':
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{args.port}/')
        while True:
            if stop_file.exists() and stop_file.read_text(encoding='utf-8').strip() == session:
                stop_file.unlink(missing_ok=True)
                break
            time.sleep(1)
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f'A service exited. Check logs in {log_dir}')
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(processes):
            if p.poll() is None: p.terminate()
        for p in processes:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for log in logs: log.close()
        if state_file.exists():
            try:
                if json.loads(state_file.read_text(encoding='utf-8'))['session'] == session:
                    state_file.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError): pass


if __name__ == '__main__':
    main()
