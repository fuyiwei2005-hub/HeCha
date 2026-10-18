"""Package restored paths and the React build, excluding local data and secrets."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.git',
             'output', 'ppt', '.ultralytics', 'ultralytics.egg-info'}


def include(path):
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts): return False
    if rel.parts[:3] in [('backend', 'data', 'uploads'), ('backend', 'data', 'results')]: return False
    name = path.name.lower()
    if name.startswith('.env') and name != '.env.example': return False
    if name.endswith(('.pyc', '.tsbuildinfo', '.log', '.zip', '.bak', '.key')): return False
    if '.bak_' in name or name.endswith(('.db', '.db-wal', '.db-shm', '.db-journal')): return False
    return True


def original_path(name):
    if name.endswith('__init__.py'):
        return name[:-len('__init__.py')].replace('__', '/') + '__init__.py'
    return name.replace('__', '/')


def main():
    manifest_path = ROOT / 'docs/refactor/change-manifest.json'
    files = sorted(path for path in ROOT.rglob('*') if path.is_file() and include(path) and path != manifest_path)
    current = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with zipfile.ZipFile(ROOT.parent / '作品源代码.zip') as original:
        old = {original_path(e.filename): hashlib.sha256(original.read(e)).hexdigest()
               for e in original.infolist() if not e.is_dir()}
    manifest = {
        'added': sorted(set(current)-set(old)),
        'changed': sorted(name for name in set(current)&set(old) if current[name] != old[name]),
        'excluded_or_archived': sorted(set(old)-set(current)),
        'weights_unchanged': current.get('model_weights/best.pt') == old.get('model_weights/best.pt'),
        'files': current,
    }
    docs = ROOT / 'docs/refactor'
    docs.mkdir(parents=True, exist_ok=True)
    (docs / 'change-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    # Add the manifest after computing content hashes; it does not hash itself.
    files.append(docs / 'change-manifest.json')
    target = ROOT.parent / 'PestGuard_功能恢复修复版_源码.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, 'PestGuard-refactored/' + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert 'PestGuard-refactored/frontend/dist/index.html' in names
        assert 'PestGuard-refactored/backend/app/__init__.py' in names
        assert not any(Path(name).name.startswith('.env') and not name.endswith('.env.example') for name in names)
        assert not any(name.endswith(('.db', '.db-wal', '.db-shm')) for name in names)
    print(f'Packaged {len(files)} files, {target.stat().st_size / 1048576:.1f} MiB')
    print(f'Changed {len(manifest["changed"])} files; added {len(manifest["added"])}; weights unchanged: {manifest["weights_unchanged"]}')


if __name__ == '__main__': main()
