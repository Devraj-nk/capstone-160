const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`${options.method || "GET"} ${path} failed: ${res.status}`);
  }
  return res.json();
}

// The review queue: undecided situations, including ones auto-routed because
// no reviewer decided in time (they still need a human verdict).
export function getPendingSituations() {
  return request("/situations?status=pending&status=auto_routed");
}

export function getConfirmedSituations() {
  return request("/situations?status=confirmed");
}

export function decideSituation(id, decision, note) {
  return request(`/situations/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, note: note || null }),
  });
}

export function getPipelineStats() {
  return request("/pipeline/stats");
}

export function getResponseMetrics() {
  return request("/analytics/response");
}

export function getTrends() {
  return request("/analytics/trends");
}

export function getHeatmaps() {
  return request("/analytics/heatmaps");
}

export function listDailyReports() {
  return request("/reports/daily");
}

export function getDailyReport(day) {
  return request(`/reports/daily/${day}`);
}

export function getTodayReport() {
  return request("/reports/daily/today");
}

export function rebuildDailyReport(day) {
  return request(`/reports/daily/${day}`, { method: "POST" });
}

export function getTickets(department) {
  const query = department ? `?department=${encodeURIComponent(department)}` : "";
  return request(`/tickets${query}`);
}

export function updateTicket(id, status) {
  return request(`/tickets/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function getAnalyticsSummary() {
  return request("/analytics/summary");
}

export function getFilteredPosts(reason, limit = 8) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (reason) params.set("reason", reason);
  return request(`/analytics/filtered?${params}`);
}
