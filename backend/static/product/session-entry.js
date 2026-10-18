
// Resolve the first-visit entry before the product interface can flash on screen.
if (location.pathname.replace(/\/$/, '') !== '/login') {
  document.documentElement.setAttribute('data-session-pending', '');
  let hasSession=false;
  try { hasSession=!!localStorage.getItem('token'); } catch(e) {}
  if (!hasSession) location.replace('/login?next='+encodeURIComponent(location.pathname));
}
