"""Render independent product pages from shared markup and interaction code."""
import re
import json
import hashlib
from html import escape
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from app.core.config import get_settings

router=APIRouter()
TEMPLATE=Path(__file__).resolve().parents[2]/'static/index.html'
FRAGMENTS=TEMPLATE.parents[1]/'templates/product'
ASSETS=TEMPLATE.parent/'product'
PAGES={
 '/':('home','首页','选择你要使用的功能。'),
 '/legacy':('home','首页','选择你要使用的功能。'),
 '/detect':('detect','图片识别','上传图片或拍摄照片，查看识别结果与防治建议。'),
 '/video':('video','视频识别','上传田间视频，查看进度、识别结果与时间线。'),
 '/history':('history','历史记录','查看已保存的检测结果，继续追问、反馈或管理记录。'),
 '/statistics':('statistics','数据统计','查看当前账号的累计检测数据。'),
 '/features':('features','核心能力','了解平台支持的识别与植保辅助能力。'),
 '/about':('about','技术介绍','了解从影像采集到识别分析的工作过程。'),
 '/login':('login','登录与注册','登录后即可使用识别与记录管理功能。'),
 '/contact':('contact','联系我们','项目交流与部署咨询。'),
 '/model':('model','模型说明','查看自带模型的结构与训练记录。'),
 '/deployment':('deployment','源码与部署','了解项目组成与部署方式。'),
}

def render_page(path):
 key,title,description=PAGES[path]
 html=TEMPLATE.read_text(encoding='utf-8')
 manifest=json.loads((FRAGMENTS/'manifest.json').read_text(encoding='utf-8'))
 for name,allowed in manifest.items():
  fragment=(FRAGMENTS/name).read_text(encoding='utf-8') if key in allowed else ''
  html=html.replace('{{fragment:'+name+'}}',fragment)
 # Asset fingerprints prevent an old cached script being paired with new markup.
 for asset in ASSETS.iterdir():
  if asset.suffix in ('.js','.css'):
   url='/static/product/'+asset.name
   version=hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
   html=html.replace('"'+url+'"','"'+url+'?v='+version+'"')
 html=html.replace('<body>','<body data-page="'+key+'">',1)
 html=re.sub(r'<title>.*?</title>','<title>'+escape(title)+' · 禾察</title>',html,count=1)
 active='/' if key=='home' else path
 html=html.replace('href="'+active+'"','aria-current="page" href="'+active+'"')
 heading=''
 if key!='home':
  heading='<div class="page-heading"><div class="breadcrumb"><a href="/">首页</a> / '+escape(title)+'</div><h1 class="serif">'+escape(title)+'</h1><p>'+escape(description)+'</p></div>'
  if key in ('detect','video','history','statistics'):
   heading+='<div id="loginNote" class="module-login-note" hidden>登录后即可使用此模块。<a href="/login?next='+path+'">登录 / 注册 →</a></div>'
 html=html.replace('{{page_heading}}',heading)
 if key=='video':
  html=html.replace('>历史记录</h2>','>视频任务与结果</h2>')
  html=re.sub(r'<button onclick="clearAllData\(\)"[^>]*>.*?</button>','',html,flags=re.S)
  html=html.replace('暂无检测记录，上传一张图片试试。','暂无视频任务，上传一段视频开始分析。')
 return html

DIST_INDEX=TEMPLATE.parents[2]/'frontend/dist/index.html'

def react_page():
 return FileResponse(DIST_INDEX, headers={'Cache-Control': 'no-cache'})

def product_page(request:Request):
 if get_settings().product_frontend == 'react' and request.url.path != '/legacy' and DIST_INDEX.is_file():
  return react_page()
 return HTMLResponse(render_page(request.url.path),headers={'Cache-Control':'no-cache'})

for path in PAGES:
 router.add_api_route(path,product_page,methods=['GET'],include_in_schema=False)

# Serve the SPA entry for directly opened preview routes as well.
@router.get('/experimental', include_in_schema=False)
@router.get('/experimental/{path:path}', include_in_schema=False)
def preview_page(path: str = ''):
 if DIST_INDEX.is_file():
  return react_page()
 return HTMLResponse('前端尚未构建', status_code=503)
