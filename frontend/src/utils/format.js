import { STATUS, ROLES } from '../constants/enums.js';
export function statusText(value) { return STATUS[value] || value || '—'; }
export function roleText(value) { return ROLES[value] || value; }
export function hours(value) { return `${Number(value || 0).toFixed(2)} h`; }
export function dateText(value) { return value ? new Date(value).toLocaleDateString('zh-CN') : '—'; }
export function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c])); }
