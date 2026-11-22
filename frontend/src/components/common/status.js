import { statusText } from '../../utils/format.js';
import { CASE_STATUS } from '../../constants/enums.js';
export function statusPill(status) { return `<span class="pill pill-${status}">${statusText(status)}</span>`; }
export function caseStatusPill(status) { return `<span class="pill pill-${status === 'decided' ? 'approved' : 'adjudication_pending'}">${CASE_STATUS[status] || status}</span>`; }
