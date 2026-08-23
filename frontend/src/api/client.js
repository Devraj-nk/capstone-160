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

export function getPendingSituations() {
  return request("/situations?status=pending");
}

export function getConfirmedSituations() {
  return request("/situations?status=confirmed");
}

export function decideSituation(id, decision) {
  return request(`/situations/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}

export function getAnalyticsSummary() {
  return request("/analytics/summary");
}
