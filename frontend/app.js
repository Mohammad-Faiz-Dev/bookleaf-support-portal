// BookLeaf portal SPA (Vue 3, no build step). Talks only to the REST API; holds no secrets.
const { createApp } = Vue;
const POLL_MS = 4000; // near-real-time: poll the open view every 4s

async function api(path, { method = 'GET', body } = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(path, {
    method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error || {};
    const err = new Error(e.details?.length ? e.details.map(d => `${d.field}: ${d.message}`).join('; ') : (e.message || `Request failed (${res.status})`));
    err.status = res.status; throw err;
  }
  return data;
}

createApp({
  data: () => ({
    user: JSON.parse(localStorage.getItem('user') || 'null'), view: '', busy: false, error: '', flash: '',
    loginForm: { email: '', password: '' }, meta: { statuses: [], categories: [], priorities: [] },
    books: [], tickets: [], current: null, replyText: '', noteText: '',
    ticketForm: { book_id: null, subject: '', description: '', attachment_name: null },
    queue: [], stats: {}, filters: { status: '', category: '', priority: '', assigned: '', date_from: '', date_to: '', q: '' },
    draftSource: '', draftLoading: false, timer: null,
  }),
  computed: { isAdmin() { return this.user?.role === 'admin'; } },
  watch: { filters: { deep: true, handler() { this.loadQueue(); } } },
  async mounted() {
    this.meta = await api('/api/meta');
    if (this.user) this.home();
    this.timer = setInterval(() => this.poll(), POLL_MS);
  },
  methods: {
    async run(fn) { this.error = ''; this.busy = true; try { return await fn(); } catch (e) { this.error = e.message; if (e.status === 401) this.logout(); } finally { this.busy = false; } },
    async login() { await this.run(async () => {
      const r = await api('/api/auth/login', { method: 'POST', body: this.loginForm });
      localStorage.setItem('token', r.access_token); localStorage.setItem('user', JSON.stringify(r.user)); this.user = r.user; this.home(); }); },
    logout() { localStorage.clear(); this.user = null; this.current = null; },
    home() { this.go(this.isAdmin ? 'queue' : 'books'); },
    async go(v) { this.view = v; this.flash = ''; this.error = ''; this.current = null; this.replyText = '';
      if (v === 'books' || v === 'new') this.books = await api('/api/me/books');
      if (v === 'tickets') this.tickets = await api('/api/me/tickets');
      if (v === 'queue') this.loadQueue(); },
    newFor(id) { this.go('new'); this.ticketForm.book_id = id; },
    async createTicket() { await this.run(async () => {
      const t = await api('/api/me/tickets', { method: 'POST', body: this.ticketForm });
      this.ticketForm = { book_id: null, subject: '', description: '', attachment_name: null };
      await this.openTicket(t.id); this.flash = `Ticket #${t.id} created. We usually reply within 24–48 hours.`; }); },
    async openTicket(id) { this.error = '';
      try { const t = await api(`/api/me/tickets/${id}`); this.current = t; this.view = 'ticket'; }
      catch (e) { this.error = e.message; if (e.status === 401) this.logout(); } },
    async authorReply() { await this.run(async () => { this.current = await api(`/api/me/tickets/${this.current.id}/messages`, { method: 'POST', body: { body: this.replyText } }); this.replyText = ''; }); },
    async loadQueue() { if (!this.isAdmin) return;
      const qs = new URLSearchParams(Object.entries(this.filters).filter(([, v]) => v)).toString();
      try { [this.queue, this.stats] = await Promise.all([api(`/api/admin/tickets?${qs}`), api('/api/admin/stats')]); } catch (e) { this.error = e.message; } },
    async openAdmin(id) { this.replyText = ''; this.noteText = ''; this.draftSource = ''; this.error = '';
      try { this.current = await api(`/api/admin/tickets/${id}`); this.view = 'admin-ticket'; this.loadDraft(false); }
      catch (e) { this.error = e.message; if (e.status === 401) this.logout(); } },
    async loadDraft(regenerate) { this.draftLoading = true;
      try { const d = await api(`/api/admin/tickets/${this.current.id}/draft?regenerate=${regenerate}`); this.replyText = d.draft; this.draftSource = d.source; }
      catch (e) { this.draftSource = ''; this.error = 'Could not generate a draft. Please write the reply manually.'; }
      finally { this.draftLoading = false; } },
    async adminReply() { await this.run(async () => { this.current = await api(`/api/admin/tickets/${this.current.id}/responses`, { method: 'POST', body: { body: this.replyText } }); this.replyText = ''; this.flash = 'Reply sent to the author.'; }); },
    async addNote() { await this.run(async () => { this.current = await api(`/api/admin/tickets/${this.current.id}/notes`, { method: 'POST', body: { body: this.noteText } }); this.noteText = ''; }); },
    async patch(body) { await this.run(async () => { this.current = await api(`/api/admin/tickets/${this.current.id}`, { method: 'PATCH', body }); }); },
    async poll() { if (!this.user || document.hidden) return;
      try {
        if (this.view === 'tickets') this.tickets = await api('/api/me/tickets');
        else if (this.view === 'ticket' && this.current) this.current = await api(`/api/me/tickets/${this.current.id}`);
        else if (this.view === 'queue') await this.loadQueue();
        else if (this.view === 'admin-ticket' && this.current) { const t = await api(`/api/admin/tickets/${this.current.id}`); this.current = t; }
      } catch (_) { /* transient; next poll retries */ } },
    inr: n => '₹' + (n || 0).toLocaleString('en-IN'),
    fmt: d => new Date(d + 'Z').toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }),
    ago(d) { const m = (Date.now() - new Date(d + 'Z')) / 60000; return m < 1 ? 'just now' : m < 60 ? `${Math.round(m)} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; },
    ageLabel: h => h < 1 ? '<1h' : h < 48 ? `${Math.round(h)}h` : `${Math.round(h / 24)}d`,
    statusColor: s => ({ 'Open': 'blue', 'In Progress': 'amber', 'Resolved': 'green', 'Closed': 'grey' }[s]),
    srcTitle: s => ({ ai: 'Set by AI', rules: 'Set by keyword fallback', admin: 'Overridden by admin' }[s]),
  },
}).mount('#app');
