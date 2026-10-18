"""Real bundled-weight inference; synthetic images test execution, not accuracy."""
from pathlib import Path
import os, sys, json
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'output/real-model-check'
DATA.mkdir(parents=True,exist_ok=True)
os.environ['MODEL_PATH']=str(ROOT/'model_weights/best.pt')
os.environ['ALLOW_MOCK_DETECTOR']='false'
sys.path.insert(0,str(ROOT/'backend'))
os.chdir(ROOT/'backend')
from app.services.detector import detector
from app.workers.video import render_video
from app.services.ffmpeg import transcode_to_h264
from PIL import Image
import cv2, numpy as np
elapsed=detector.warmup()
assert detector.ready and detector.mode=='yolo'
img=DATA/'input.png'; Image.new('RGB',(64,64),'green').save(img)
result=DATA/'annotated.jpg'
predictions=detector.predict_image(img.read_bytes(),result)
assert result.is_file()
source=DATA/'input.mp4'; target=DATA/'result.mp4'
w=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64))
for _ in range(10):w.write(np.zeros((64,64,3),dtype=np.uint8))
w.release()
events,meta=render_video(source,target)
h264=transcode_to_h264(target)
assert meta['sampled_frames']==10 and h264
report={'mode':detector.mode,'ready':detector.ready,'warmup_seconds':elapsed,'image_predictions':len(predictions),'video_meta':meta,'h264':h264,'accuracy_evaluated':False}
(DATA/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
