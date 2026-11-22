import { get, post, postIdempotent } from '../api/client.js';
import { layout, bindLayout } from '../components/common/layout.js';
import { statusPill, caseStatusPill } from '../components/common/status.js';
import { toast } from '../hooks/useToast.js';
import { escapeHtml, tableShell } from '../components/common/table.js';
import { CASE_STATUS } from '../constants/enums.js';
import { session } from '../stores/session.js';

const MONTH = '2026-11';
const DEPT = '信息工程学院';

// 浏览器端稳定短哈希，仅用于拼幂等键，不需要密码学强度。
function hashReason(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (Math.imul(31, hash) + text.charCodeAt(i)) | 0;
  return (hash >>> 0).toString(36);
}

function previewRows(previews) {
  return (previews || []).map((p) => `<tr><td><b>${escapeHtml(p.department)}</b><small class="cell-sub">${escapeHtml(p.month)} 月报预览</small></td><td>${p.row_count} 组</td><td><b>${Number(p.total_approved_hours).toFixed(2)} h</b></td></tr>`).join('');
}

function recordLine(record, winnerId) {
  const isWinner = winnerId === record.id;
  return `<div class="case-record ${isWinner ? 'is-winner' : ''}">
    <div><b>#${record.id} ${escapeHtml(record.class_code)}</b>
      <small class="cell-sub">${escapeHtml(record.department)} · ${escapeHtml(record.work_date)} · ${escapeHtml(record.activity_type)}</small>
      <small class="cell-sub">签到 ${escapeHtml(record.check_in || '—')} → ${escapeHtml(record.check_out || '—')}</small>
    </div>
    <div>${statusPill(record.status)}<small class="cell-sub">有效 ${Number(record.validated_hours).toFixed(2)} h</small></div>
    <div>${isWinner ? '<span class="winner-tag">当前计薪</span>' : '<span class="muted">未计薪</span>'}</div>
  </div>`;
}

function decisionList(decisions) {
  if (!decisions.length) return '<p class="case-empty">尚未裁决。</p>';
  return `<ol class="decision-list">${decisions.map((d) => `<li>
    <b>第 ${d.seq} 次 · 选择 #${d.chosen_record_id}</b>
    ${d.previous_record_id ? `<span class="muted">（原为 #${d.previous_record_id}）</span>` : ''}
    <small class="cell-sub">${escapeHtml(d.actor_name || '学院管理员')} · ${escapeHtml(d.created_at)}</small>
    <p>${escapeHtml(d.reason)}</p>
  </li>`).join('')}</ol>`;
}

function caseCard(item, isAdmin) {
  const canChoose = isAdmin;
  const options = item.records.map((r) => `<label class="choice"><input type="radio" name="chosen-${item.id}" value="${r.id}" ${item.winner_record_id === r.id ? 'checked' : ''}>
    <span>改选 #${r.id} ${escapeHtml(r.class_code)}（${escapeHtml(r.department)}）</span></label>`).join('');
  return `<article class="case-card" data-case="${item.id}" data-version="${item.version}">
    <header class="case-head">
      <div><span class="eyebrow">ADJUDICATION CASE #${item.id}</span>
        <h3>${escapeHtml(item.ta_name)} · ${escapeHtml(item.month || '')} 跨学院时段重叠</h3></div>
      <div>${caseStatusPill(item.status)}
        <small class="cell-sub">${CASE_STATUS[item.status] || item.status} · 版本 ${item.version}</small></div>
    </header>
    <div class="case-records">${item.records.map((r) => recordLine(r, item.winner_record_id)).join('')}</div>
    <div class="case-previews">
      <span class="eyebrow">MONTHLY PREVIEW / 两院同步</span>
      <table><thead><tr><th>学院</th><th>透视组</th><th>已审批</th></tr></thead><tbody>${previewRows(item.previews)}</tbody></table>
    </div>
    <div class="case-decisions"><span class="eyebrow">DECISION TRACE / 每次裁决理由</span>${decisionList(item.decisions)}</div>
    ${canChoose ? `<form class="case-form" data-case="${item.id}" data-version="${item.version}">
      <div class="choices">${options}</div>
      <label>改选理由<textarea name="reason" rows="2" minlength="2" maxlength="500" required placeholder="例如：另一笔签到时间与排班窗口一致，且课程要求必须到场"></textarea></label>
      <button class="primary-mini" type="submit">提交裁决并更新两院月报</button>
      <div class="case-result"></div>
    </form>` : ''}
  </article>`;
}

export async function renderReview() {
  const isAdmin = session.user?.role === 'college_admin';
  const [records, report, cases] = await Promise.all([
    get('/work-records'),
    get(`/reports/monthly?month=${MONTH}&department=${encodeURIComponent(DEPT)}`),
    get('/adjudications')
  ]);

  const rows = records.items.map((r) => `<tr><td><b>${escapeHtml(r.class_code)}</b><small class="cell-sub">${escapeHtml(r.ta_name)} · ${escapeHtml(r.work_date)}</small></td><td>${escapeHtml(r.activity_type)}<small class="cell-sub">有效 ${r.validated_hours} h</small></td><td>${statusPill(r.status)}${r.conflict_type ? `<small class="cell-sub conflict">${escapeHtml(r.conflict_type)}</small>` : ''}</td><td>${r.status === 'manual_review' ? `<button class="outline-btn resolve" data-id="${r.id}">学院复核</button>` : r.status === 'submitted' ? `<button class="primary-mini approve" data-id="${r.id}">教师审批</button>` : r.status === 'adjudication_pending' ? '<span class="muted">等待学院裁决</span>' : '<span class="muted">已处理</span>'}</td></tr>`);

  const reportRows = report.rows.slice(0, 8).map((r) => `<tr><td>${escapeHtml(r.class_code)}<small class="cell-sub">${escapeHtml(r.course_name)}</small></td><td>${escapeHtml(r.activity_type)}</td><td>${escapeHtml(r.ta_name)}</td><td><b>${Number(r.approved_hours).toFixed(2)} h</b></td></tr>`);
  const casesHtml = cases.items.length
    ? cases.items.map((item) => caseCard(item, isAdmin)).join('')
    : '<div class="empty-state"><div class="empty-mark">∅</div><h3>暂无冲突裁决</h3><p>同一助教跨学院签到时段重叠时，这里会出现冲突案例与每次裁决理由。</p></div>';

  document.getElementById('app').innerHTML = layout('review', `
    <div class="section-bar"><div><p class="kicker">REVIEW / MONTHLY PIVOT</p><h2>教师审批与学院月报</h2><p>冲突的两笔记录都会保留，只有一笔进入计薪；学院管理员可说明理由后改选。</p></div><div class="report-total"><span>${MONTH} 本院已审批</span><b>${Number(report.total_approved_hours).toFixed(2)} h</b></div></div>
    <div class="review-grid">
      <section class="panel table-panel"><div class="panel-head"><div><span class="eyebrow">REVIEW QUEUE</span><h3>待处理记录</h3></div><span class="queue-count">${records.items.filter((r) => ['submitted', 'manual_review', 'adjudication_pending'].includes(r.status)).length} 条</span></div>${tableShell(['课程班 / 助教', '活动 / 有效工时', '状态', '动作'], rows, '审批队列为空')}</section>
      <section class="panel table-panel report-panel"><div class="panel-head"><div><span class="eyebrow">COLLEGE PIVOT / ${MONTH}</span><h3>${DEPT}月报</h3></div><button class="primary-mini" id="publish-report">发布快照</button></div>${tableShell(['课程班', '活动类型', '助教', '已审批'], reportRows, '暂无已审批工时')}<div class="report-foot">透视维度：学院 × 课程班 × 活动类型 × 助教</div></section>
    </div>
    <section class="section-bar adjudication-bar"><div><p class="kicker">CONFLICT ADJUDICATION</p><h2>跨学院时段冲突裁决</h2><p>并发审批时先到的一笔计薪，后到的一笔保留为待裁决；改选在同一次事务内同时刷新两个学院月报。</p></div><div class="filter-chip">${cases.items.length} 个冲突案例</div></section>
    <section class="case-list">${casesHtml}</section>
    <section class="audit-strip"><span class="eyebrow">CONTROL NOTE</span><b>未审核工时不会出现在月报合计。</b><span>裁决回执丢失时按同一幂等键重试，不会重复记账，也不会覆盖后来作出的裁决。</span></section>
  `);
  bindLayout();

  document.querySelectorAll('.approve').forEach((b) => b.addEventListener('click', async () => {
    try {
      const result = await post(`/work-records/${b.dataset.id}/review`, { note: '任课教师核对签到与工作说明' });
      toast(result.message || (result.status === 'approved' ? '已审批，记录进入月报' : '记录已转入学院裁决'), result.status === 'approved' ? 'success' : 'info');
      renderReview();
    } catch (e) { toast(e.message, 'error'); }
  }));

  document.querySelectorAll('.resolve').forEach((b) => b.addEventListener('click', async () => {
    try {
      await post(`/work-records/${b.dataset.id}/resolve-conflict`, { note: '学院管理员核对排班后转教师审批' });
      toast('冲突已解除，等待教师审批', 'success');
      renderReview();
    } catch (e) { toast(e.message, 'error'); }
  }));

  document.querySelectorAll('.case-form').forEach((form) => form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const caseId = Number(form.dataset.case);
    const version = Number(form.dataset.version);
    const chosen = form.querySelector('input[type=radio]:checked');
    const resultBox = form.querySelector('.case-result');
    const reason = form.querySelector('[name=reason]').value.trim();
    if (!chosen) { toast('请选择要计薪的记录', 'error'); return; }
    if (reason.length < 2) { toast('请填写改选理由', 'error'); return; }
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    // 幂等键由本次裁决内容确定：同一意图刷新或重发都复用，改选不同记录则生成新键。
    const chosenId = Number(chosen.value);
    const key = `case-${caseId}-v${version}-${chosenId}-${hashReason(reason)}`;
    try {
      const receipt = await postIdempotent(`/adjudications/${caseId}/decisions`, {
        chosen_record_id: chosenId, reason, expected_version: version
      }, key);
      if (receipt.superseded) {
        resultBox.textContent = '裁决已被后续操作更新，以最新版本为准；本次未覆盖后来的裁决。';
        resultBox.className = 'case-result is-warning';
        toast('裁决已被后续操作更新，未覆盖新决定', 'info');
      } else {
        const previews = (receipt.previews || []).map((p) => `${p.department} ${Number(p.total_approved_hours).toFixed(2)}h`).join(' · ');
        resultBox.textContent = `${receipt.replayed ? '回执已重放，未重复记账。' : '裁决已生效。'}${previews}`;
        resultBox.className = 'case-result is-success';
        toast(receipt.replayed ? '回执已重放，账目未重复' : '裁决已生效，两院月报已同步', 'success');
      }
      renderReview();
    } catch (err) {
      resultBox.textContent = err.message;
      resultBox.className = 'case-result is-warning';
      toast(err.message, 'error');
      button.disabled = false;
    }
  }));

  document.getElementById('publish-report').addEventListener('click', async () => {
    try {
      const result = await post('/reports/monthly/publish', { month: MONTH, department: DEPT });
      toast(`月报已发布，共 ${result.total_approved_hours.toFixed(2)} 小时`, 'success');
    } catch (e) { toast(e.message, 'error'); }
  });
}
