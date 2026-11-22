import { session } from '../../stores/session.js';
import { roleText } from '../../utils/format.js';
export function layout(active, content) {
  const user = session.user;
  return `<div class="shell"><aside class="rail">
    <div class="brand-mark">D</div><div class="brand-copy"><b>东澜大学</b><span>教务核算台</span></div>
    <div class="rail-rule"></div><nav>
      <a class="nav-item ${active === 'dashboard' ? 'active' : ''}" href="#/dashboard"><span>01</span>总览</a>
      <a class="nav-item ${active === 'attendance' ? 'active' : ''}" href="#/attendance"><span>02</span>排班签到</a>
      <a class="nav-item ${active === 'hours' ? 'active' : ''}" href="#/hours"><span>03</span>工时填报</a>
      <a class="nav-item ${active === 'review' ? 'active' : ''}" href="#/review"><span>04</span>审批与月报</a>
    </nav>
    <div class="rail-footer"><small>2026 秋季学期</small><strong>信息工程学院</strong></div>
  </aside><main class="main"><header class="topbar"><div><span class="eyebrow">ACADEMIC OPERATIONS / 2026.11</span><h1>${activeTitle(active)}</h1></div><div class="user-chip"><span class="avatar">${(user?.name || '访').slice(0,1)}</span><div><b>${user?.name || '访客'}</b><small>${roleText(user?.role || '')}</small></div><button class="ghost-btn" id="logout">退出</button></div></header><section class="content">${content}</section></main></div>`;
}
function activeTitle(active) { return ({ dashboard: '工时口径总览', attendance: '排班与签到', hours: '助教工时填报', review: '教师审批与学院月报' })[active] || '登录'; }
export function bindLayout() { document.getElementById('logout')?.addEventListener('click', () => session.logout()); }
