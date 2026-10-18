
(function(){
 const sidebar=document.getElementById('moduleSidebar'), toggle=document.getElementById('menuToggle'), menu=document.getElementById('moduleNav'), backdrop=document.getElementById('menuBackdrop'), content=document.querySelector('.wrap');
 if (!sidebar || !toggle) return;
 function setMenu(open, restoreFocus) {
   sidebar.classList.toggle('is-open',open);
   toggle.setAttribute('aria-expanded',String(open));
   toggle.setAttribute('aria-label',open?'收起功能菜单':'展开功能菜单');
   toggle.querySelector('span').textContent=open?'×':'☰';
   menu.inert=!open; backdrop.hidden=!open;
   content.inert=open;
   if(!open && restoreFocus) toggle.focus();
 }
 toggle.addEventListener('click',()=>setMenu(!sidebar.classList.contains('is-open'),false));
 backdrop.addEventListener('click',()=>setMenu(false,true));
 menu.addEventListener('click',e=>{if(e.target.closest('a'))setMenu(false,false);});
 document.addEventListener('keydown',e=>{
   if(!sidebar.classList.contains('is-open'))return;
   if(e.key==='Escape'){e.preventDefault();setMenu(false,true);return;}
   if(e.key==='Tab'){
     const links=[...menu.querySelectorAll('a')],last=links[links.length-1];
     if(e.shiftKey && document.activeElement===toggle){e.preventDefault();last.focus();}
     else if(!e.shiftKey && document.activeElement===last){e.preventDefault();toggle.focus();}
   }
 });
})();
