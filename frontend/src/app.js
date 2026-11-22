import { session } from './stores/session.js';
import { loginPage, bindLogin } from './pages/login.js';
import { renderDashboard } from './pages/dashboard.js';
import { renderAttendance } from './pages/attendance.js';
import { renderHours } from './pages/hours.js';
import { renderReview } from './pages/review.js';

async function render() {
  const route = location.hash.replace('#/', '') || (session.user ? 'dashboard' : 'login');
  if (!session.user && route !== 'login') { location.hash = '#/login'; return; }
  if (route === 'login') { document.getElementById('app').innerHTML = loginPage(); bindLogin(); return; }
  try {
    if (route === 'dashboard') await renderDashboard();
    else if (route === 'attendance') await renderAttendance();
    else if (route === 'hours') await renderHours();
    else if (route === 'review') await renderReview();
    else { location.hash = '#/dashboard'; }
  } catch (error) { document.getElementById('app').innerHTML = `<div class="fatal-error"><h2>页面加载失败</h2><p>${error.message}</p><a href="#/dashboard">返回总览</a></div>`; }
}
window.addEventListener('hashchange', render);
render();
