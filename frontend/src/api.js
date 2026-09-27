const SAFE_PROTOCOLS = new Set(["https:", "http:", "tel:"]);
const IMAGE_PATH = /^\/api\/jobs\/[0-9a-f]{32}\/images\/[A-Za-z0-9._-]+\.jpg$/;

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new ApiError("Server tidak bisa dihubungi. Pastikan backend jalan: python -m scraper.web");
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.detail || `Request gagal (HTTP ${response.status}).`, response.status);
  }
  return body;
}

export const getHealth = () => request("/api/health");

export const createJob = ({ keyword, area, maxResults, priceMin = null, priceMax = null }) =>
  request("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ keyword, area, max_results: maxResults, price_min: priceMin, price_max: priceMax }),
  });

export const getJob = (id) => request(`/api/jobs/${encodeURIComponent(id)}`);

export const fileUrl = (id, kind) => `/api/jobs/${encodeURIComponent(id)}/files/${kind}`;

export function safeImageSrc(path) {
  return IMAGE_PATH.test(path || "") ? path : null;
}

export function safeHref(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return SAFE_PROTOCOLS.has(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}
