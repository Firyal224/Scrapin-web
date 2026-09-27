# Web UI Restoran/Cafe Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selesaikan sisa arsitektur "GitHub-only" dari spec: GitHub Actions workflow untuk menjalankan scraper Python yang sudah ada, static frontend (Vite+React) untuk trigger/poll/download hasil lewat GitHub REST API, workflow deploy ke GitHub Pages, dan README setup — semuanya dengan perhatian keamanan (PAT hanya di localStorage, tidak ada script injection di workflow, CSP di frontend, least-privilege permissions).

**Architecture:** Backend Python scraper (`scraper/`) sudah lengkap dan teruji fungsinya secara statis (Google Places API → normalize → output CSV/XLSX + gambar lokal). Yang dibangun sekarang murni lapisan orkestrasi: (1) `.github/workflows/scrape.yml` menjalankan `python -m scraper.main` dengan input `workflow_dispatch` dan meng-upload `output/` sebagai artifact; (2) `.github/workflows/deploy-pages.yml` build `frontend/` lalu deploy ke GitHub Pages; (3) `frontend/` (Vite+React, minim dependency) memanggil GitHub REST API langsung dari browser dengan PAT milik user (disimpan di `localStorage`), polling run, download+unzip artifact via JSZip, render tabel hasil, dan sediakan tombol download CSV/XLSX asli.

**Tech Stack:** Python 3.11 (sudah ada), GitHub Actions, Vite + React 18, papaparse, jszip. Tidak ada dependency baru di backend.

**Spec:** `document/document.md`

## Global Constraints

- TANPA AI/LLM di seluruh pipeline (sudah dipatuhi backend; frontend juga tidak boleh memanggil LLM apapun).
- PAT GitHub disimpan hanya di `localStorage` browser, dikirim HANYA ke `api.github.com` (dan domain redirect resmi GitHub untuk artifact download) — tidak pernah ke server pihak ketiga.
- Urutan kolom output tetap: `Nama, Der Treffpunkt, Sosmed, Kontak, Gambar, Alasan` (sudah diimplementasikan di `scraper/output_writer.py`, jangan diubah).
- Tidak ada secret (API key, PAT) yang pernah di-commit atau tercetak di log Actions.
- `workflow_dispatch` inputs tidak boleh diinterpolasi langsung ke `run:` shell (`${{ inputs.x }}` di dalam script) — wajib lewat `env:` untuk menghindari script injection GitHub Actions yang sudah dikenal.
- Least privilege: setiap workflow set `permissions:` eksplisit, tidak pakai default (yang di banyak org masih `read/write` semua).
- Frontend statis murni (tanpa server backend terpisah), semua script dibundle sendiri lewat build Vite — tidak ada `<script src="https://cdn...">` pihak ketiga di halaman yang menyimpan token.

---

## Task 1: GitHub Actions — `scrape.yml`

**Files:**
- Create: `.github/workflows/scrape.yml`

**Interfaces:**
- Consumes: `scraper/main.py` CLI — `python -m scraper.main --keyword <str> --area <str> --max-results <int 1-60>` (sudah ada, lihat `scraper/main.py:18-30`). Env vars yang dibaca `scraper/config.py`: `GOOGLE_PLACES_API_KEY`, `STORAGE_MODE`, `OUTPUT_DIR` (opsional).
- Produces: artifact GitHub Actions bernama `hasil-scraping` berisi `output/hasil_scraping.csv`, `output/hasil_scraping.xlsx`, `output/images/**`. Nama artifact ini dikonsumsi oleh `frontend/src/github-api.js` di Task 3.

- [ ] **Step 1: Tulis workflow file**

```yaml
name: Scrape Restoran/Cafe

on:
  workflow_dispatch:
    inputs:
      keyword:
        description: "Keyword pencarian (mis. cafe)"
        required: true
        type: string
      area:
        description: "Area pencarian (mis. Jakarta Selatan)"
        required: true
        type: string
      max_results:
        description: "Jumlah maksimum hasil (1-60)"
        required: false
        type: string
        default: "20"

permissions:
  contents: read

concurrency:
  group: scrape-restoran
  cancel-in-progress: false

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      KEYWORD: ${{ inputs.keyword }}
      AREA: ${{ inputs.area }}
      MAX_RESULTS: ${{ inputs.max_results }}
      GOOGLE_PLACES_API_KEY: ${{ secrets.GOOGLE_PLACES_API_KEY }}
      STORAGE_MODE: local
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run scraper
        run: |
          python -m scraper.main \
            --keyword "$KEYWORD" \
            --area "$AREA" \
            --max-results "$MAX_RESULTS"

      - name: Upload hasil sebagai artifact
        uses: actions/upload-artifact@v4
        with:
          name: hasil-scraping
          path: output/
          retention-days: 7
          if-no-files-found: error
```

Catatan keamanan yang WAJIB dipertahankan saat menulis file ini:
- Input `keyword`/`area`/`max_results` masuk lewat `env:` di level job, BUKAN diinterpolasi langsung ke dalam blok `run:` (mis. `run: python -m scraper.main --keyword "${{ inputs.keyword }}"` itu SALAH — rentan command injection kalau attacker punya akses trigger workflow dan menaruh backtick/`$()`/`;` di input).
- `permissions: contents: read` di level workflow — job ini tidak butuh menulis apapun ke repo.
- `GOOGLE_PLACES_API_KEY` hanya ada di scope job ini via `secrets.*`, tidak pernah di-`echo` atau masuk step lain.

- [ ] **Step 2: Validasi sintaks YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/scrape.yml', encoding='utf-8')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Review manual checklist injeksi**

Buka file, pastikan tidak ada satupun `${{ inputs.` atau `${{ github.event.inputs.` yang muncul di dalam blok `run:`. Semua pemakaian `${{ inputs.* }}` hanya boleh muncul di blok `env:`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci: add workflow_dispatch scraper job with least-privilege permissions"
```

---

## Task 2: GitHub Actions — `deploy-pages.yml`

**Files:**
- Create: `.github/workflows/deploy-pages.yml`

**Interfaces:**
- Consumes: `frontend/package.json` build script `npm run build` yang menghasilkan `frontend/dist/` (dibuat di Task 3).
- Produces: situs statis live di GitHub Pages — dikonsumsi manual oleh user (dibuka di browser), didokumentasikan di README (Task 5).

- [ ] **Step 1: Tulis workflow file**

```yaml
name: Deploy Frontend to Pages

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"
      - ".github/workflows/deploy-pages.yml"
  workflow_dispatch: {}

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install deps
        working-directory: frontend
        run: npm ci

      - name: Build
        working-directory: frontend
        run: npm run build

      - uses: actions/configure-pages@v5

      - uses: actions/upload-pages-artifact@v3
        with:
          path: frontend/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Validasi sintaks YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-pages.yml', encoding='utf-8')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-pages.yml
git commit -m "ci: add GitHub Pages deploy workflow for frontend"
```

---

## Task 3: Frontend scaffold — Vite + React, tanpa dependency berlebih

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/index.css`
- Create: `frontend/.gitignore` (kalau belum ke-cover oleh root `.gitignore` — cek dulu, root sudah cover `frontend/node_modules` dan `frontend/dist`, jadi tidak perlu file baru)

**Interfaces:**
- Produces: `npm run dev` (dev server), `npm run build` → `dist/` (dikonsumsi Task 2), `npm run test` (vitest, dikonsumsi Task 4).

- [ ] **Step 1: `frontend/package.json`**

```json
{
  "name": "resto-scraper-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "jszip": "^3.10.1",
    "papaparse": "^5.4.1",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.8",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: `frontend/vite.config.js`**

```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
```

`sourcemap: false` sengaja — sourcemap production tidak perlu untuk static tool sederhana ini dan mengurangi ukuran deploy.

- [ ] **Step 3: `frontend/index.html`**

```html
<!doctype html>
<html lang="id">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' https://api.github.com https://*.githubusercontent.com https://*.blob.core.windows.net; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    />
    <title>Resto/Cafe Scraper</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

CSP ini penting karena halaman ini menyimpan GitHub PAT di `localStorage` — membatasi `connect-src` dan `script-src` ke domain yang benar-benar dipakai mengurangi risiko eksfiltrasi token lewat XSS atau dependency yang disusupi.

- [ ] **Step 4: `frontend/src/index.css`**

```css
:root {
  color-scheme: light dark;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  padding: 2rem;
  max-width: 960px;
  margin-inline: auto;
}

.card {
  border: 1px solid #d0d7de;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 1rem;
}

.row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  border: 1px solid #d0d7de;
  padding: 0.5rem;
  text-align: left;
  vertical-align: top;
}

img.thumb {
  max-width: 96px;
  max-height: 96px;
  object-fit: cover;
  border-radius: 4px;
}

.error {
  color: #b71c1c;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
```

- [ ] **Step 5: `frontend/src/main.jsx`**

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 6: Install dependencies dan verifikasi dev server bisa start**

Run: `cd frontend && npm install`
Expected: install selesai tanpa error, `package-lock.json` dibuat.

(App.jsx belum ada — dibuat di Task 5. Verifikasi build penuh dilakukan di akhir Task 5.)

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html frontend/src/main.jsx frontend/src/index.css
git commit -m "feat(frontend): scaffold Vite+React app with hardened CSP"
```

---

## Task 4: `frontend/src/github-api.js` — GitHub REST API client

**Files:**
- Create: `frontend/src/github-api.js`
- Test: `frontend/src/github-api.test.js`

**Interfaces:**
- Consumes: fetch global (browser/vitest env), `localStorage` untuk cache repo owner/name (tidak untuk token — token disimpan terpisah oleh `App.jsx`).
- Produces (dipakai oleh `App.jsx` di Task 5):
  - `parseRepoFromLocation(hostname, pathname) -> { owner: string, repo: string } | null`
  - `maskToken(token: string) -> string`
  - `dispatchWorkflow({ token, owner, repo, workflowFile, inputs }) -> Promise<{ dispatchedAt: string }>`
  - `findRunAfter({ token, owner, repo, workflowFile, dispatchedAt, signal }) -> Promise<{ id: number, status: string, conclusion: string|null, html_url: string }>`
  - `getRun({ token, owner, repo, runId }) -> Promise<RunObject>`
  - `listArtifacts({ token, owner, repo, runId }) -> Promise<Array<{ id: number, name: string, archive_download_url: string }>>`
  - `downloadArtifactZip({ token, artifactDownloadUrl }) -> Promise<Blob>`
  - `class GitHubApiError extends Error { status: number }`

- [ ] **Step 1: Tulis test untuk pure helper functions**

```javascript
import { describe, it, expect } from "vitest";
import { parseRepoFromLocation, maskToken } from "./github-api.js";

describe("parseRepoFromLocation", () => {
  it("parses owner/repo from a github.io pages URL", () => {
    const result = parseRepoFromLocation("myuser.github.io", "/resto-scraper/");
    expect(result).toEqual({ owner: "myuser", repo: "resto-scraper" });
  });

  it("returns null for a non-github.io host", () => {
    expect(parseRepoFromLocation("localhost", "/")).toBeNull();
  });

  it("returns null when pathname has no repo segment", () => {
    expect(parseRepoFromLocation("myuser.github.io", "/")).toBeNull();
  });
});

describe("maskToken", () => {
  it("keeps only the last 4 characters visible", () => {
    expect(maskToken("ghp_abcdef123456")).toBe("••••••••••••3456");
  });

  it("fully masks short tokens", () => {
    expect(maskToken("abc")).toBe("•••");
  });

  it("returns empty string for empty input", () => {
    expect(maskToken("")).toBe("");
  });
});
```

- [ ] **Step 2: Jalankan test, pastikan gagal (module belum ada)**

Run: `cd frontend && npx vitest run src/github-api.test.js`
Expected: FAIL — `Cannot find module './github-api.js'` atau named export tidak ditemukan.

- [ ] **Step 3: Implementasi `github-api.js`**

```javascript
const API_BASE = "https://api.github.com";
const API_VERSION = "2022-11-28";

export class GitHubApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "GitHubApiError";
    this.status = status;
  }
}

export function parseRepoFromLocation(hostname, pathname) {
  if (!hostname.endsWith(".github.io")) return null;
  const owner = hostname.split(".")[0];
  const segments = pathname.split("/").filter(Boolean);
  if (!owner || segments.length === 0) return null;
  return { owner, repo: segments[0] };
}

export function maskToken(token) {
  if (!token) return "";
  if (token.length <= 4) return "•".repeat(token.length);
  return "•".repeat(token.length - 4) + token.slice(-4);
}

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": API_VERSION,
  };
}

async function githubFetch(url, { token, ...options } = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { ...authHeaders(token), ...(options.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new GitHubApiError(
      `GitHub API ${response.status} pada ${url}: ${body.slice(0, 200)}`,
      response.status
    );
  }
  return response;
}

export async function dispatchWorkflow({ token, owner, repo, workflowFile, inputs }) {
  const dispatchedAt = new Date().toISOString();
  await githubFetch(
    `${API_BASE}/repos/${owner}/${repo}/actions/workflows/${workflowFile}/dispatches`,
    {
      token,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );
  return { dispatchedAt };
}

export async function findRunAfter({ token, owner, repo, workflowFile, dispatchedAt }) {
  const response = await githubFetch(
    `${API_BASE}/repos/${owner}/${repo}/actions/workflows/${workflowFile}/runs?event=workflow_dispatch&per_page=5`,
    { token }
  );
  const data = await response.json();
  const cutoff = new Date(dispatchedAt).getTime() - 5000;
  const match = (data.workflow_runs || []).find(
    (run) => new Date(run.created_at).getTime() >= cutoff
  );
  return match || null;
}

export async function getRun({ token, owner, repo, runId }) {
  const response = await githubFetch(
    `${API_BASE}/repos/${owner}/${repo}/actions/runs/${runId}`,
    { token }
  );
  return response.json();
}

export async function listArtifacts({ token, owner, repo, runId }) {
  const response = await githubFetch(
    `${API_BASE}/repos/${owner}/${repo}/actions/runs/${runId}/artifacts`,
    { token }
  );
  const data = await response.json();
  return data.artifacts || [];
}

export async function downloadArtifactZip({ token, artifactDownloadUrl }) {
  const response = await githubFetch(artifactDownloadUrl, { token });
  return response.blob();
}
```

Catatan: `ref: "main"` di-hardcode karena struktur repo target selalu punya branch default `main` (sesuai spec). Kalau user pakai branch lain, ini didokumentasikan di README sebagai hal yang perlu disesuaikan.

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `cd frontend && npx vitest run src/github-api.test.js`
Expected: PASS, 6 test lulus.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/github-api.js frontend/src/github-api.test.js
git commit -m "feat(frontend): add GitHub REST API client with tests"
```

---

## Task 5: `frontend/src/App.jsx` — UI utama

**Files:**
- Create: `frontend/src/App.jsx`
- Modify: `frontend/package.json` (tambah `jsdom` sebagai devDependency untuk test yang butuh DOM environment, jika Task 4 test perlu — di Task 4 tidak perlu DOM jadi cek dulu; kalau tidak perlu, skip)

**Interfaces:**
- Consumes semua export dari `frontend/src/github-api.js` (Task 4) dan `papaparse` (parse CSV), `jszip` (unzip artifact blob).
- Produces: halaman fungsional siap di-build (`npm run build`) dan di-deploy oleh Task 2.

- [ ] **Step 1: Implementasi `App.jsx`**

```jsx
import { useEffect, useMemo, useState } from "react";
import Papa from "papaparse";
import JSZip from "jszip";
import {
  parseRepoFromLocation,
  maskToken,
  dispatchWorkflow,
  findRunAfter,
  getRun,
  listArtifacts,
  downloadArtifactZip,
  GitHubApiError,
} from "./github-api.js";

const TOKEN_STORAGE_KEY = "resto_scraper_pat";
const WORKFLOW_FILE = "scrape.yml";
const POLL_INTERVAL_MS = 5000;
const MAX_POLL_ATTEMPTS = 120; // ~10 menit

function readStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function storeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // localStorage tidak tersedia (mis. private mode ketat) — abaikan, token tetap di memori state
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function App() {
  const detectedRepo = useMemo(
    () => parseRepoFromLocation(window.location.hostname, window.location.pathname),
    []
  );

  const [token, setToken] = useState(readStoredToken);
  const [tokenInput, setTokenInput] = useState("");
  const [owner, setOwner] = useState(detectedRepo?.owner || "");
  const [repo, setRepo] = useState(detectedRepo?.repo || "");
  const [keyword, setKeyword] = useState("");
  const [area, setArea] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [status, setStatus] = useState("idle"); // idle | dispatching | running | downloading | done | error
  const [statusMessage, setStatusMessage] = useState("");
  const [rows, setRows] = useState([]);
  const [imageUrls, setImageUrls] = useState({});
  const [downloadUrls, setDownloadUrls] = useState({ csv: null, xlsx: null });
  const [error, setError] = useState("");

  useEffect(() => {
    return () => {
      Object.values(imageUrls).forEach((url) => URL.revokeObjectURL(url));
      if (downloadUrls.csv) URL.revokeObjectURL(downloadUrls.csv);
      if (downloadUrls.xlsx) URL.revokeObjectURL(downloadUrls.xlsx);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSaveToken(event) {
    event.preventDefault();
    const trimmed = tokenInput.trim();
    setToken(trimmed);
    storeToken(trimmed);
    setTokenInput("");
  }

  function handleClearToken() {
    setToken("");
    storeToken("");
  }

  async function handleScrape(event) {
    event.preventDefault();
    setError("");
    setRows([]);
    setDownloadUrls({ csv: null, xlsx: null });

    const trimmedKeyword = keyword.trim();
    const trimmedArea = area.trim();
    if (!token || !owner || !repo || !trimmedKeyword || !trimmedArea) {
      setError("Token, owner/repo, keyword, dan area wajib diisi.");
      return;
    }
    if (maxResults < 1 || maxResults > 60) {
      setError("Jumlah hasil maksimum harus antara 1 dan 60.");
      return;
    }

    try {
      setStatus("dispatching");
      setStatusMessage("Memicu workflow di GitHub Actions...");
      const { dispatchedAt } = await dispatchWorkflow({
        token,
        owner,
        repo,
        workflowFile: WORKFLOW_FILE,
        inputs: {
          keyword: trimmedKeyword,
          area: trimmedArea,
          max_results: String(maxResults),
        },
      });

      setStatus("running");
      let run = null;
      for (let attempt = 0; attempt < 6 && !run; attempt += 1) {
        await sleep(2000);
        run = await findRunAfter({ token, owner, repo, workflowFile: WORKFLOW_FILE, dispatchedAt });
      }
      if (!run) throw new Error("Run baru tidak ditemukan setelah dispatch. Cek tab Actions di GitHub secara manual.");

      setStatusMessage(`Menjalankan scraping (run #${run.run_number})...`);
      let finished = run;
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
        finished = await getRun({ token, owner, repo, runId: run.id });
        if (finished.status === "completed") break;
        setStatusMessage(`Status: ${finished.status} (run #${run.run_number})...`);
        await sleep(POLL_INTERVAL_MS);
      }
      if (finished.status !== "completed") {
        throw new Error("Timeout menunggu workflow selesai. Cek tab Actions di GitHub.");
      }
      if (finished.conclusion !== "success") {
        throw new Error(`Workflow selesai dengan status "${finished.conclusion}". Cek log Actions untuk detail.`);
      }

      setStatus("downloading");
      setStatusMessage("Mengambil hasil...");
      const artifacts = await listArtifacts({ token, owner, repo, runId: finished.id });
      const artifact = artifacts.find((item) => item.name === "hasil-scraping");
      if (!artifact) throw new Error("Artifact 'hasil-scraping' tidak ditemukan pada run ini.");

      const zipBlob = await downloadArtifactZip({ token, artifactDownloadUrl: artifact.archive_download_url });
      const zip = await JSZip.loadAsync(zipBlob);

      const csvEntry = zip.file("hasil_scraping.csv");
      const xlsxEntry = zip.file("hasil_scraping.xlsx");
      if (!csvEntry || !xlsxEntry) throw new Error("File hasil_scraping.csv/xlsx tidak ditemukan di dalam artifact.");

      const csvText = await csvEntry.async("string");
      const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });
      setRows(parsed.data);

      const newImageUrls = {};
      const imageFiles = zip.folder("images");
      if (imageFiles) {
        const entries = Object.values(imageFiles.files).filter((f) => !f.dir);
        for (const entry of entries) {
          const blob = await entry.async("blob");
          newImageUrls[`images/${entry.name.split("/").pop()}`] = URL.createObjectURL(blob);
        }
      }
      setImageUrls(newImageUrls);

      const csvBlob = await csvEntry.async("blob");
      const xlsxBlob = await xlsxEntry.async("blob");
      setDownloadUrls({
        csv: URL.createObjectURL(csvBlob),
        xlsx: URL.createObjectURL(xlsxBlob),
      });

      setStatus("done");
      setStatusMessage(`Selesai. ${parsed.data.length} baris hasil.`);
    } catch (err) {
      setStatus("error");
      const message = err instanceof GitHubApiError ? err.message : err.message || String(err);
      setError(message);
      setStatusMessage("");
    }
  }

  const isBusy = status === "dispatching" || status === "running" || status === "downloading";

  return (
    <main>
      <h1>Resto/Cafe Scraper</h1>

      <section className="card">
        <h2>1. GitHub Personal Access Token</h2>
        {token ? (
          <p>
            Token aktif: <code>{maskToken(token)}</code>{" "}
            <button type="button" onClick={handleClearToken}>Hapus Token</button>
          </p>
        ) : (
          <form onSubmit={handleSaveToken} className="row">
            <input
              type="password"
              placeholder="ghp_xxx atau fine-grained token"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              autoComplete="off"
            />
            <button type="submit">Simpan Token</button>
          </form>
        )}
        <p><small>Token disimpan hanya di localStorage browser ini dan hanya dikirim ke api.github.com.</small></p>
      </section>

      <section className="card">
        <h2>2. Repository target</h2>
        <div className="row">
          <div className="field">
            <label htmlFor="owner">Owner</label>
            <input id="owner" value={owner} onChange={(event) => setOwner(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="repo">Repo</label>
            <input id="repo" value={repo} onChange={(event) => setRepo(event.target.value)} />
          </div>
        </div>
      </section>

      <section className="card">
        <h2>3. Parameter scraping</h2>
        <form onSubmit={handleScrape}>
          <div className="row">
            <div className="field">
              <label htmlFor="keyword">Keyword</label>
              <input id="keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="cafe" maxLength={100} />
            </div>
            <div className="field">
              <label htmlFor="area">Area</label>
              <input id="area" value={area} onChange={(event) => setArea(event.target.value)} placeholder="Jakarta Selatan" maxLength={100} />
            </div>
            <div className="field">
              <label htmlFor="maxResults">Maks hasil</label>
              <input
                id="maxResults"
                type="number"
                min={1}
                max={60}
                value={maxResults}
                onChange={(event) => setMaxResults(Number(event.target.value))}
              />
            </div>
          </div>
          <button type="submit" disabled={isBusy}>
            {isBusy ? "Sedang berjalan..." : "Scrape Sekarang"}
          </button>
        </form>
        {statusMessage && <p>{statusMessage}</p>}
        {error && <p className="error">{error}</p>}
      </section>

      {rows.length > 0 && (
        <section className="card">
          <h2>4. Hasil</h2>
          <div className="row">
            {downloadUrls.csv && <a href={downloadUrls.csv} download="hasil_scraping.csv"><button type="button">Download CSV</button></a>}
            {downloadUrls.xlsx && <a href={downloadUrls.xlsx} download="hasil_scraping.xlsx"><button type="button">Download XLSX</button></a>}
          </div>
          <table>
            <thead>
              <tr>
                <th>Nama</th>
                <th>Der Treffpunkt</th>
                <th>Sosmed</th>
                <th>Kontak</th>
                <th>Gambar</th>
                <th>Alasan</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  <td>{row["Nama"]}</td>
                  <td>{row["Der Treffpunkt"] && <a href={row["Der Treffpunkt"]} target="_blank" rel="noreferrer">Maps</a>}</td>
                  <td>{row["Sosmed"] && <a href={row["Sosmed"]} target="_blank" rel="noreferrer">Sosmed</a>}</td>
                  <td>{row["Kontak"] && <a href={row["Kontak"]} target="_blank" rel="noreferrer">WhatsApp</a>}</td>
                  <td>{imageUrls[row["Gambar"]] && <img className="thumb" src={imageUrls[row["Gambar"]]} alt={row["Nama"]} loading="lazy" />}</td>
                  <td>{row["Alasan"]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
```

Catatan keamanan: semua nilai dari CSV (`row["Nama"]`, dst.) dirender lewat JSX text node biasa — React meng-escape otomatis, jadi tidak ada risiko XSS meskipun nama tempat mengandung karakter HTML.

- [ ] **Step 2: Build production untuk verifikasi**

Run: `cd frontend && npm run build`
Expected: build sukses, `frontend/dist/index.html` dan asset JS/CSS ter-generate tanpa error.

- [ ] **Step 3: Jalankan dev server dan verifikasi manual di browser**

Run: `cd frontend && npm run dev`
Buka URL yang ditampilkan (biasanya `http://localhost:5173`), verifikasi:
- Form token muncul, input token tersimpan (cek DevTools → Application → Local Storage → key `resto_scraper_pat`).
- Field owner/repo, keyword, area, maks hasil bisa diisi.
- Klik "Scrape Sekarang" tanpa token menampilkan pesan error validasi (bukan crash).
- Tidak ada error di console terkait CSP (kalau ada `Refused to connect` untuk domain yang sah, sesuaikan `connect-src` di `index.html`).

Matikan dev server setelah verifikasi (Ctrl+C).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(frontend): implement scrape trigger, polling, and results UI"
```

---

## Task 6: `README.md`

**Files:**
- Create: `README.md`

**Interfaces:**
- Tidak ada interface kode — dokumen setup end-to-end untuk user non-teknis-GitHub-Actions.

- [ ] **Step 1: Tulis README.md**

Isi wajib (tulis lengkap, bukan placeholder):
1. Deskripsi singkat tool + arsitektur (tabel dari `document/document.md`).
2. **Setup Google Places API key**: buat project di Google Cloud Console, aktifkan "Places API", buat API key, batasi key ke API tersebut saja (Application restrictions → None untuk server-side Actions runner, API restrictions → Places API only untuk membatasi blast radius jika bocor).
3. **Set GitHub Secret**: Settings → Secrets and variables → Actions → New repository secret → nama `GOOGLE_PLACES_API_KEY`.
4. **Aktifkan GitHub Pages**: Settings → Pages → Source: GitHub Actions (bukan branch), lalu jalankan workflow `Deploy Frontend to Pages` (otomatis jalan saat push ke `main` yang mengubah `frontend/**`, atau trigger manual).
5. **Buat Personal Access Token**: rekomendasikan **fine-grained PAT** (Settings → Developer settings → Fine-grained tokens), scope ke repository ini saja, permission minimal: `Actions: Read and write`, `Contents: Read-only`. Jelaskan risiko: siapapun yang mendapat token ini bisa memicu workflow dan membaca hasil scraping repo ini — set expiry pendek (mis. 30-90 hari) dan revoke setelah tidak dipakai.
6. **Cara pakai**: buka Pages URL → masukkan token → isi owner/repo (biasanya sudah otomatis terisi) → isi keyword+area → klik Scrape → tunggu polling → download hasil.
7. **Jalankan scraper secara lokal (opsional, untuk testing)**: `cp .env.example .env`, isi `GOOGLE_PLACES_API_KEY`, `python -m venv .venv`, `pip install -r requirements.txt`, `python -m scraper.main --keyword cafe --area "Jakarta Selatan"`.
8. **Catatan keamanan**: jangan commit `.env`/token; PAT hanya disimpan di localStorage browser dan bisa dihapus lewat tombol "Hapus Token"; retensi artifact 7 hari (bisa diubah di `scrape.yml`).
9. **Troubleshooting** singkat: run gagal → cek tab Actions; artifact tidak ketemu → pastikan workflow selesai `success`; CSP error di console → domain artifact download berubah, sesuaikan `connect-src`.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add end-to-end setup guide"
```

---

## Task 7: Security & consistency pass

**Files:**
- Modify (jika ditemukan masalah): file manapun dari Task 1-6.

- [ ] **Step 1: Grep untuk memastikan tidak ada input workflow diinterpolasi langsung di `run:`**

Run: `grep -n 'inputs\.' .github/workflows/*.yml`
Expected: semua match hanya muncul di baris `env:` block, tidak ada di dalam string `run:` manapun.

- [ ] **Step 2: Pastikan `.env` asli tidak pernah ter-track**

Run: `git status --porcelain | grep -E '^\?\? \.env$|^\?\? \.env\.'`
Expected: `.env` tidak muncul (sudah di-ignore); `.env.example` boleh muncul kalau belum ditambahkan sebelumnya (biasanya sudah ada di commit awal).

- [ ] **Step 3: Full test suite backend + frontend**

Run:
```bash
cd frontend && npx vitest run
cd .. && python -m pytest 2>&1 || echo "belum ada test backend — lihat catatan di bawah"
```

Kalau belum ada test backend (`tests/` kosong), catat ini sebagai known gap di README bagian Troubleshooting, tidak perlu menulis test backend baru di plan ini (di luar scope — backend sudah dianggap selesai & terverifikasi sebelumnya oleh user sesuai `document/document.md` langkah 2).

- [ ] **Step 4: Build frontend final**

Run: `cd frontend && npm run build`
Expected: sukses, tidak ada warning terkait dependency dengan known vulnerability tinggi. Jalankan juga `npm audit --omit=dev` dan tinjau hasilnya — kalau ada `high`/`critical` pada dependency inti (react/vite/jszip/papaparse), catat dan perbaiki versi di `package.json`.

- [ ] **Step 5: Commit final (jika ada perubahan dari review)**

```bash
git add -A
git commit -m "fix: address security review findings"
```

---

## Self-Review Notes

- **Spec coverage:** kolom output (sudah ada di backend), trigger via `workflow_dispatch` (Task 1), token di localStorage + dipanggil langsung ke GitHub API (Task 4-5), polling run + artifact (Task 4-5), tabel hasil + download CSV/XLSX (Task 5), README setup lengkap (Task 6). Deploy Pages ditambahkan sebagai Task 2 karena spec menyebut "deploy sepenuhnya di GitHub" tapi tidak eksplisit menulis workflow-nya — perlu ada mekanisme build+deploy `frontend/dist` ke Pages, jadi ditambahkan agar arsitektur benar-benar "GitHub-only".
- **Placeholder scan:** semua step berisi kode/command konkret, tidak ada "TODO"/"handle appropriately".
- **Type/name consistency:** nama artifact `hasil-scraping` konsisten antara Task 1 (`upload-artifact name:`) dan Task 5 (`artifacts.find((item) => item.name === "hasil-scraping")`). Nama file `hasil_scraping.csv`/`.xlsx` konsisten dengan `scraper/output_writer.py:14-15`. Fungsi-fungsi `github-api.js` yang dipakai `App.jsx` (Task 5) semuanya didefinisikan dengan signature yang sama di Task 4.
