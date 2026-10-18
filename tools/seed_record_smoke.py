"""Seed only an explicitly isolated browser-test database, never application data."""
import json, shutil, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
root = Path(__file__).resolve().parents[1]
data = Path(sys.argv[1]).resolve()
if not data.is_relative_to((root/'output').resolve()): raise SystemExit('Test directory required')
user_id=int(sys.argv[2])
connection=sqlite3.connect(data/'smoke.db')
assert connection.execute('SELECT id FROM users WHERE id=?',(user_id,)).fetchone()
base=datetime(2026,1,1,tzinfo=timezone.utc)
for i in range(125):
    did=str(uuid4());video=i%3==0
    predictions=[{'class':'aphid','class_cn':'蚜虫','confidence':.7}]
    if video: predictions=[{'time_ms':0,'detections':predictions}]
    connection.execute('INSERT INTO detections (id,user_id,media_type,original_name,stored_name,status,predictions,analysis_status,created_at,crop) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (did,user_id,'video' if video else 'image',f'田间旧记录_{i:03}.'+('mp4' if video else 'png'),did+'.bin','completed',json.dumps(predictions),'skipped',(base+timedelta(days=i%3,seconds=i)).replace(tzinfo=None).isoformat(' '),'玉米'))
did=str(uuid4());stored=did+'.mp4';(data/'uploads').mkdir(exist_ok=True)
shutil.copyfile(sys.argv[3],data/'uploads'/stored)
connection.execute('INSERT INTO detections (id,user_id,media_type,original_name,stored_name,status,predictions,analysis_status,created_at,error) VALUES (?,?,?,?,?,?,?,?,?,?)',
    (did,user_id,'video','retry-source.mp4',stored,'failed','[]','disabled',datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' '),'模拟上次处理被中断'))
connection.commit();connection.close();print('Seeded 126 isolated records including one retained video source.')
