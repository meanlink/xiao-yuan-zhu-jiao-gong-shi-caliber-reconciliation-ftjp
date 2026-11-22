export function withBusy(button, task) { button.disabled = true; button.classList.add('is-busy'); return task().finally(() => { button.disabled = false; button.classList.remove('is-busy'); }); }
