import { statusText } from '../../utils/format.js';
export function statusPill(status) { return `<span class="pill pill-${status}">${statusText(status)}</span>`; }
