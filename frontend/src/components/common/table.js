import { escapeHtml } from '../../utils/format.js';
export function emptyState(title, detail) { return `<div class="empty-state"><div class="empty-mark">∅</div><h3>${title}</h3><p>${detail}</p></div>`; }
export function tableShell(headers, rows, empty = '暂无记录') { return rows.length ? `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>` : emptyState(empty, '调整筛选条件或先完成上一环节。'); }
export { escapeHtml };
