"""Request graceful shutdown of the launcher belonging to this directory."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
state=ROOT/'output/local/runtime.json'
if not state.is_file():
    print('No running desktop launcher recorded for this project.')
else:
    data=json.loads(state.read_text(encoding='utf-8'))
    (state.parent/'stop.request').write_text(data['session'],encoding='utf-8')
    print('Shutdown requested. The launcher will stop its own services.')
