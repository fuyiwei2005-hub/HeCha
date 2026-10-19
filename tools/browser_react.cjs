const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {spawn}=require('child_process');
const {chromium}=require(process.env.PESTGUARD_PLAYWRIGHT_MODULE);
const root=path.resolve(__dirname,'..'),out=path.join(root,'output','react-smoke'),base='http://127.0.0.1:18081';
fs.mkdirSync(out,{recursive:true});
const python=process.env.PESTGUARD_PYTHON||path.join(root,'.venv','Scripts','python.exe'),pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const log=fs.openSync(path.join(out,'server.log'),'w');
 const server=spawn(python,[path.join(root,'tools/smoke_full.py'),'18081'],{cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,PRODUCT_FRONTEND:'react',PYTHONIOENCODING:'utf-8'}});
 let browser;const checks=[],errors=[];
 try{
  let ready=false;for(let i=0;i<150;i++){if(server.exitCode!==null)throw Error('test server exited');try{if((await fetch(base+'/api/health')).ok){ready=true;break;}}catch{}await pause(200);}assert(ready);
  browser=await chromium.launch({channel:'msedge',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
  const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['camera']});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',dialog=>dialog.accept());
  const username='react_'+Date.now(),password='Smoke-password-123';
  await page.goto(base+'/');await page.waitForURL(url=>url.pathname==='/login');await page.locator('#authForm').waitFor();
  assert.equal(await page.locator('#modules').count(),0);assert(!(await page.locator('body').innerText()).includes('PESTGUARD'));
  await page.screenshot({path:path.join(out,'login-desktop.png'),fullPage:true,animations:'disabled'});checks.push('first visit opens branded login before product');
  await page.getByRole('button',{name:'没有账号？去注册'}).click();await page.locator('#username').fill(username);await page.locator('#password').fill(password);await page.getByRole('button',{name:'注册并登录',exact:true}).click();
  await page.waitForURL(base+'/');await page.locator('#modules').waitFor();assert.equal(await page.locator('.vine-leaf').count(),6);checks.push('registration enters module homepage');
  assert.equal(await page.locator('#imgFile').count(),0);assert.equal(await page.locator('#history').count(),0);checks.push('home does not stack functional modules');
  const vine=page.locator('.vine-workspace');await vine.waitFor();
  for(const value of [.02,.5,.98]){await vine.evaluate((el,value)=>window.scrollTo({top:el.getBoundingClientRect().top+scrollY-88+(el.offsetHeight-innerHeight+88)*value,behavior:'instant'}),value);await page.waitForFunction(value=>Math.abs(Number(document.querySelector('.vine-workspace').dataset.progress)-value)<.02,value);}
  assert.equal(await page.locator('.vine-leaf[aria-hidden="false"]').count(),6);checks.push('scroll rotates the vine and reveals all six pest leaves');
  await page.emulateMedia({reducedMotion:'reduce'});await page.locator('.vine-workspace[data-motion="reduced"]').waitFor();assert.equal(await page.locator('.vine-leaf[aria-hidden="false"]').count(),6);checks.push('reduced motion exposes all feature leaves without a pinned scene');
  await page.emulateMedia({reducedMotion:'no-preference'});await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:path.join(out,'home-desktop.png'),fullPage:true,animations:'disabled'});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'home-mobile.png'),fullPage:true,animations:'disabled'});await page.setViewportSize({width:1440,height:1000});
  await page.route('**/api/auth/me', route => route.fulfill({status:503,contentType:'application/json',body:'{"detail":"temporary failure"}'}));
  await page.reload();await page.getByRole('button',{name:'重试连接',exact:true}).waitFor();assert(await page.evaluate(()=>!!localStorage.getItem('token')));
  await page.unroute('**/api/auth/me');await page.getByRole('button',{name:'重试连接',exact:true}).click();await page.locator('#modules').waitFor();checks.push('temporary authentication outage preserves session and allows retry');
  const fresh=await browser.newContext();const guest=await fresh.newPage();guest.on('pageerror',e=>errors.push(e.message));
  await guest.goto(base+'/video');await guest.waitForURL(url=>url.pathname==='/login');assert.equal(new URL(guest.url()).searchParams.get('next'),'/video');
  await guest.locator('#username').fill(username);await guest.locator('#password').fill(password);await guest.getByRole('button',{name:'登录',exact:true}).click();await guest.waitForURL(base+'/video');await guest.locator('#videoUpload').waitFor();await fresh.close();checks.push('deep link login returns to requested module');
  const stale=await browser.newContext();const invalid=await stale.newPage();await invalid.goto(base+'/login');await invalid.evaluate(()=>localStorage.setItem('token','expired-test-session'));await invalid.goto(base+'/history');await invalid.waitForURL(url=>url.pathname==='/login');await invalid.locator('#authForm').waitFor();assert.equal(await invalid.evaluate(()=>localStorage.getItem('token')),null);await stale.close();checks.push('invalid session returns to login');
  // Redirects accept only known local product paths.
  await page.goto(base+'/login?next=https://example.org');await page.waitForURL(base+'/');checks.push('login return path rejects external destinations');
  await page.locator('#menuToggle').click();await page.locator('#moduleNav').waitFor();assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'true');
  await page.keyboard.press('Escape');assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'false');
  await page.locator('#menuToggle').click();await page.locator('.drawer-backdrop').click({position:{x:900,y:350}});assert.equal(await page.locator('#moduleDrawer').getAttribute('aria-hidden'),'true');checks.push('left menu opens and closes with keyboard and backdrop');
  for(const url of ['/features','/about','/deployment']){assert.equal((await page.goto(base+url)).status(),200);await page.locator('#infoPage').waitFor();await page.reload();await page.locator('#infoPage').waitFor();assert(new URL(page.url()).pathname===url);}checks.push('information modules support direct links and refresh');
  await page.getByRole('link',{name:'联系我们 ↗',exact:true}).click();await page.waitForURL(base+'/#contact');await page.locator('#contact').waitFor();assert(await page.locator('#contact').isVisible());assert.equal(await page.locator('#contact a[href="mailto:1826244602@qq.com"]').count(),3);await page.screenshot({path:path.join(out,'contact-desktop.png'),animations:'disabled'});
  await page.locator('#menuToggle').click();assert.equal(await page.locator('#moduleNav a[href="/model"],#moduleNav a[href="/contact"]').count(),0);await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844});await page.locator('#contact').evaluate(el=>el.scrollIntoView({behavior:'instant',block:'start'}));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'contact-mobile.png'),fullPage:false,animations:'disabled'});await page.reload();await page.locator('#contact').waitFor();await page.waitForFunction(()=>document.querySelector('#contact').getBoundingClientRect().top<innerHeight);checks.push('contact is a responsive homepage footer with working cross-page and refresh anchors');
  await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/model');await page.waitForURL(base+'/');assert.equal(await page.locator('.model-editorial').count(),0);assert.equal(await page.locator('a[href="/model"]').count(),0);await page.goto(base+'/contact');await page.waitForURL(base+'/#contact');checks.push('removed model redirects home and former contact route opens homepage footer');

  await page.goto(base+'/');await page.getByRole('button',{name:'查看蚜虫与图片识别',exact:true}).click();await page.locator('.vine-use-feature').click();await page.locator('#console').waitFor();await page.goBack();await page.locator('#modules').waitFor();await page.goForward();await page.locator('#console').waitFor();checks.push('router links and browser history');
  await page.waitForFunction(()=>document.querySelector('select')?.options.length>1);
  const fixture=spawn(python,['-c',"from PIL import Image; import cv2,numpy as np,sys; Image.new('RGB',(64,64),'green').save(sys.argv[1]); w=cv2.VideoWriter(sys.argv[2],cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64)); [w.write(np.zeros((64,64,3),dtype=np.uint8)) for _ in range(10)]; w.release()",path.join(out,'image.png'),path.join(out,'video.mp4')],{windowsHide:true});await new Promise((resolve,reject)=>fixture.on('exit',code=>code===0?resolve():reject(Error('fixtures'))));
  await page.locator('select').selectOption({index:1});const crop=await page.locator('select').inputValue();await page.reload();await page.locator('select').waitFor();await page.waitForFunction(value=>document.querySelector('select')?.value===value,crop);checks.push('crop selection persists');
  await page.locator('#imgFile').setInputFiles(path.join(out,'image.png'));await page.getByRole('button',{name:'重试建议',exact:true}).waitFor({timeout:25000});
  assert(await page.locator('.detection-media img').isVisible());await page.getByRole('button',{name:'重试建议',exact:true}).click();await page.getByText('这是浏览器集成测试的模拟防治建议。',{exact:false}).waitFor({timeout:25000});
  await page.getByRole('button',{name:'查看 1 条参考资料'}).click();await page.getByText('集成测试参考条目',{exact:true}).waitFor();assert(await page.getByRole('link',{name:'下载标注结果'}).count());checks.push('image result, advice retry, automatic query refresh, references and download');
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,'detect-desktop.png'),fullPage:true,animations:'disabled'});
  await page.locator('.detection-media img').click();await page.getByRole('dialog',{name:'查看大图'}).waitFor();await page.keyboard.press('Escape');checks.push('image lightbox');
  await page.locator('#menuToggle').click();await page.locator('#moduleNav a[href="/history"]').click();await page.getByRole('button',{name:'继续追问 AI'}).click();await page.getByPlaceholder('输入你的问题（≤500 字）').fill('如何防治？');await page.getByRole('button',{name:'发送',exact:true}).click();await page.getByText('这是集成测试的模拟追问回答。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'👍 有用'}).click();await page.getByText('已反馈，谢谢！').waitFor();await page.reload();await page.getByText('已反馈，谢谢！').waitFor();await page.getByRole('button',{name:'继续追问 AI'}).click();await page.getByText('这是集成测试的模拟追问回答。',{exact:true}).waitFor();checks.push('chat and feedback persist after refresh');
  await page.locator('#menuToggle').click();await page.locator('#moduleNav a[href="/video"]').click();assert.equal(await page.getByRole('button',{name:'选择图片',exact:true}).count(),0);
  await page.locator('#vidFile').setInputFiles(path.join(out,'video.mp4'));await page.getByRole('button',{name:/查看 .* 个检出时间点/}).waitFor({timeout:45000});await page.getByRole('button',{name:/查看 .* 个检出时间点/}).click();await page.locator('.timeline-event').first().click();await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);
  assert.equal(await page.locator('.detection').count(),1);await page.screenshot({path:path.join(out,'video-desktop.png'),fullPage:true,animations:'disabled'});checks.push('video queue, filtered results, playable video and seek timeline');
  await page.reload();await page.getByRole('button',{name:/查看 .* 个检出时间点/}).waitFor();checks.push('video results survive direct refresh');
  await page.goto(base+'/experimental/video');await page.getByRole('button',{name:/查看 .* 个检出时间点/}).waitFor();await page.reload();await page.locator('#videoUpload').waitFor();assert.equal(new URL(page.url()).pathname,'/experimental/video');await page.goto(base+'/video');await page.locator('#videoUpload').waitFor();checks.push('preview deep links and refresh use the same modules');
  await page.locator('#menuToggle').click();await page.locator('#moduleNav a[href="/detect"]').click();await page.getByRole('button',{name:'拍照识别',exact:true}).click();await page.getByRole('dialog',{name:'拍照识别'}).waitFor();await page.waitForFunction(()=>document.querySelector('.cam-view video')?.readyState>=2);await page.getByRole('button',{name:'取消',exact:true}).click();checks.push('camera preview opens and closes');
  await page.locator('#menuToggle').click();await page.locator('#moduleNav a[href="/statistics"]').click();await page.locator('#stats .metric').first().waitFor();assert.equal(await page.locator('#imgFile').count(),0);assert.equal(await page.locator('.detection').count(),0);checks.push('statistics is an independent page');
  await page.goto(base+'/history');await page.locator('.detection').first().waitFor();await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'history-mobile.png'),fullPage:true,animations:'disabled'});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.locator('#menuToggle').click();await page.screenshot({path:path.join(out,'menu-mobile.png'),fullPage:true,animations:'disabled'});await page.keyboard.press('Escape');checks.push('mobile pages and sidebar fit screen');
  await page.getByRole('button',{name:'删除这条记录'}).first().click();await page.waitForFunction(()=>document.querySelectorAll('.detection').length===1);checks.push('single record deletion');
  await page.getByRole('button',{name:'清空记录',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.detection').length===0);checks.push('clear records');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();await page.waitForURL(url=>url.pathname==='/login');await page.locator('#authForm').waitFor();assert.equal(await page.evaluate(()=>localStorage.getItem('token')),null);checks.push('logout clears account state');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'login-mobile.png'),fullPage:true,animations:'disabled'});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(errors,[]);checks.push('no browser runtime errors');
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({checks,errors,synthetic:true,runner:'React routes with production local tasks'},null,2));console.log('PASS '+checks.length+' React page checks');
 }catch(error){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({checks,errors,error:String(error)},null,2));throw error;}
 finally{if(browser)await browser.close();server.kill();fs.closeSync(log);}
})().catch(error=>{console.error(error);process.exitCode=1;});
