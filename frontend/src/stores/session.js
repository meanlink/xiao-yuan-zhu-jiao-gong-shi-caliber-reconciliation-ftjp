import { api } from '../api/client.js';
export const session = {
  user: JSON.parse(localStorage.getItem('campusUser') || 'null'),
  async login(email, password) {
    const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    localStorage.setItem('campusToken', data.access_token);
    localStorage.setItem('campusUser', JSON.stringify(data.user));
    this.user = data.user;
    return data.user;
  },
  logout() { localStorage.clear(); this.user = null; location.hash = '#/login'; }
};
