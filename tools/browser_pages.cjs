const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {spawn}=require('child_process');
const {chromium}=require(process.env.PESTGUARD_PLAYWRIGHT_MODULE);
const root=path.resolve(__dirname,'..'),out=path.join(root,'output','pages-smoke');
fs.mkdirSync(out,{recursive:true});
const python=path.join(root,'.venv','Scripts','python.exe'),base='http://127.0.0.1:18080';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
const log=fs.openSync(path.join(out,'server.log'),'w');
const server=spawn(python,[path.join(root,'tools','smoke_full.py'),'18080'],{cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,PRODUCT_FRONTEND:'legacy',PYTHONIOENCODING:'utf-8'}});
let browser;const checks=[],errors=[];
try{
 for(let i=0;i<150;i++){if(server.exitCode!==null)throw Error('server exited');try{if((await fetch(base+'/api/health')).ok)break;}catch{}await pause(200);}
 const html=await(await fetch(base)).text();
 for(const script of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new(require('vm').Script)(script[1]);
 for(const match of html.matchAll(/<script[^>]+src="([^"]+)"/g)){
  const response=await fetch(base+match[1]);assert.equal(response.status,200,match[1]);
  new(require('vm').Script)(await response.text());
 }
 checks.push('all modular scripts are delivered and parse successfully');
 browser=await chromium.launch({channel:'msedge',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const page=await browser.newPage({viewport:{width:1440,height:1000},permissions:['camera']});
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const username='entry_'+Date.now(), password='Smoke-password-123';
 await page.goto(base);
 await page.waitForURL(url=>url.pathname==='/login');await page.locator('#authForm').waitFor();
 assert.equal(await page.locator('#modules').count(),0);
 await page.screenshot({path:path.join(out,'login-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'login-mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.setViewportSize({width:1440,height:1000});
 checks.push('first visit opens login/register before homepage');
 await page.locator('#regBtn').click();await page.locator('#username').fill(username);await page.locator('#password').fill(password);await page.locator('#loginBtn').click();
 await page.waitForURL(base+'/');await page.locator('#modules').waitFor();
 checks.push('registration enters homepage');
 // A fresh visitor opening a module must log in and return to that module.
 const fresh=await browser.newContext();const guest=await fresh.newPage();
 guest.on('pageerror',e=>errors.push(e.message));
 await guest.goto(base+'/video');await guest.waitForURL(url=>url.pathname==='/login');
 assert.equal(new URL(guest.url()).searchParams.get('next'),'/video');
 await guest.locator('#username').fill(username);await guest.locator('#password').fill(password);await guest.locator('#loginBtn').click();await guest.waitForURL(base+'/video');await guest.locator('#videoUpload').waitFor();await fresh.close();
 checks.push('direct module visit requires login and returns to module');
 const expired=await browser.newContext();const stale=await expired.newPage();stale.on('pageerror',e=>errors.push(e.message));
 await stale.goto(base+'/login');await stale.locator('#authForm').waitFor();await stale.evaluate(()=>localStorage.setItem('token','invalid-expired-session'));
 await stale.goto(base+'/');await stale.waitForURL(url=>url.pathname==='/login');await stale.locator('#authForm').waitFor();assert.equal(await stale.evaluate(()=>localStorage.getItem('token')),null);await expired.close();
 checks.push('invalid session returns to login without a redirect loop');
 assert.equal(await page.locator('#modules .module-card').count(),6);
 for(const selector of ['#console','#history','#statistics','#authForm','#vidFile'])assert.equal(await page.locator(selector).count(),0,'unrelated module present on home: '+selector);
 await page.screenshot({path:path.join(out,'home-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'home-mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.setViewportSize({width:1440,height:1000});
 checks.push('home shows navigation cards, not stacked modules');
 assert((await page.title()).includes('禾察'));assert(!(await page.locator('body').innerText()).includes('PestGuard'));
 assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'false');
 assert.equal(await page.locator('#moduleNav').isVisible(),false);
 await page.locator('#menuToggle').click();await page.locator('#moduleNav').waitFor();assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'true');
 assert(await page.locator('#moduleNav a[aria-current="page"]').count()>0);
 await page.screenshot({path:path.join(out,'sidebar-desktop.png'),fullPage:true});
 await page.keyboard.press('Escape');assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'false');
 await page.locator('#menuToggle').click();await page.locator('#menuBackdrop').click({position:{x:900,y:350}});assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'false');
 await page.setViewportSize({width:390,height:844});await page.locator('#menuToggle').click();await page.screenshot({path:path.join(out,'sidebar-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.keyboard.press('Escape');await page.setViewportSize({width:1440,height:1000});
 checks.push('禾察 branding and accessible left menu on desktop and mobile');

 for(const [url,id] of [['/features','#feats'],['/about','#pipe'],['/contact','#infoPage'],['/model','#infoPage'],['/deployment','#infoPage']]){
  const response=await page.goto(base+url);assert.equal(response.status(),200);await page.locator(id).waitFor();await page.reload();assert.equal(new URL(page.url()).pathname,url);
 }
 checks.push('independent informational pages support direct links and refresh');
 await page.goto(base);
 await page.locator('#modules a[href="/detect"]').click();assert.equal(new URL(page.url()).pathname,'/detect');
 await page.goBack();await page.locator('#modules').waitFor();await page.goForward();await page.locator('#console').waitFor();
 checks.push('module links and browser back/forward');
 await page.waitForFunction(()=>document.querySelector('#cropSel').options.length>1);
 checks.push('valid login preserved across independent pages');
 const fixture=spawn(python,['-c',"from PIL import Image; import cv2,numpy as np,sys; Image.new('RGB',(64,64),'green').save(sys.argv[1]); w=cv2.VideoWriter(sys.argv[2],cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64)); [w.write(np.zeros((64,64,3),dtype=np.uint8)) for _ in range(10)]; w.release()",path.join(out,'image.png'),path.join(out,'video.mp4')],{windowsHide:true});
 await new Promise((r,j)=>fixture.on('exit',c=>c===0?r():j(Error('fixtures'))));
 await page.locator('#imgFile').setInputFiles(path.join(out,'image.png'));
 await page.locator('#advice button').filter({hasText:'重试建议'}).first().waitFor({timeout:25000});
 assert(await page.locator('#stageImg').isVisible());assert.equal(await page.locator('#historyBox').count(),0);
 checks.push('image saved despite failed advice');
 await page.locator('#advice button').filter({hasText:'重试建议'}).first().click();
 await page.locator('#advice').filter({hasText:'集成测试的模拟防治建议'}).first().waitFor({timeout:25000});
 assert(await page.getByText('集成测试参考条目').count()>0);
 await page.screenshot({path:path.join(out,'detect-desktop.png'),fullPage:true});
 checks.push('local advice worker, automatic refresh, retry and references');
 await page.locator('#menuToggle').click();await page.locator('.nav-links a[href="/history"]').click();await page.locator('#historyBox .chat-head').first().click();await page.locator('#historyBox .chat-in input').first().fill('如何防治？');await page.locator('#historyBox .chat-in button').first().click();await page.locator('#historyBox .chat-log').filter({hasText:'集成测试的模拟追问回答'}).waitFor();
 await page.locator('#historyBox .fb-btn').first().click();await page.locator('#historyBox .fb-btn.on').waitFor();
 checks.push('follow-up chat and feedback');
 await page.reload();await page.locator('#historyBox .chat-head').first().waitFor();await page.locator('#historyBox .chat-head').first().click();await page.locator('#historyBox .chat-log').filter({hasText:'集成测试的模拟追问回答'}).waitFor();checks.push('login session and chat history survive reload');
 await page.locator('#menuToggle').click();await page.locator('.nav-links a[href="/video"]').click();assert.equal(await page.locator('#console').count(),0);
 await page.locator('#vidFile').setInputFiles(path.join(out,'video.mp4'));await page.locator('#historyBox .tl-head').first().waitFor({timeout:45000});await page.locator('#historyBox .tl-head').first().click();await page.locator('.tl.open .tl-row').first().waitFor();await page.locator('.vposter').first().click();await page.waitForFunction(()=>{let v=document.querySelector('.vwrap video');return v&&v.readyState>=2;});
 checks.push('local video worker without Redis, timeline and playable result');
 assert.equal(await page.locator('#historyBox .hcard').count(),1,'video page must only show video tasks');
 await page.locator('#menuToggle').click();await page.locator('.nav-links a[href="/detect"]').click();
 await page.evaluate(()=>openCamera());await page.locator('#camModal').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#camVideo').readyState>=2);await page.evaluate(()=>closeCamera());checks.push('camera preview');
 await page.locator('#menuToggle').click();await page.locator('.nav-links a[href="/statistics"]').click();await page.waitForFunction(()=>document.querySelectorAll('#stats .stat').length>0 || document.querySelector('#stats').textContent.includes('已识别害虫'));assert((await page.locator('#stats').textContent()).length>20);assert.equal(await page.locator('#historyBox').count(),0);checks.push('statistics independent from uploads and history');
 await page.locator('#menuToggle').click();await page.locator('.nav-links a[href="/history"]').click();await page.locator('#historyBox .hcard').first().waitFor();
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),JSON.stringify(await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,cls:e.className,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right})).filter(e=>e.right>innerWidth+1||e.left<0).slice(0,20)}))));checks.push('mobile layout');
 await page.locator('#historyBox .del').first().click();await page.waitForFunction(()=>document.querySelectorAll('#historyBox .hcard').length===1);checks.push('single record deletion');
 await page.evaluate(()=>clearAllData());await page.waitForFunction(()=>document.querySelectorAll('#historyBox .hcard').length===0);checks.push('clear records');
 await page.locator('#logoutBtn').click();await page.waitForURL(url=>url.pathname==='/login');await page.locator('#authForm').waitFor();assert.equal(await page.evaluate(()=>localStorage.getItem('token')),null);checks.push('logout from an independent module');
 assert.deepEqual(errors,[]);checks.push('no browser runtime errors');
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({checks,errors,synthetic:true,runner:'production local tasks'},null,2));console.log('PASS '+checks.length+' independent page checks');
}finally{if(browser)await browser.close();server.kill();fs.closeSync(log);}
})().catch(e=>{console.error(e);process.exitCode=1;});
