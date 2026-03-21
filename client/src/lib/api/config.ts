// config.ts — Single source of truth for backend connection settings.
// Modified: 2026-03-21 — Use relative URLs in web/browser mode to avoid CORS.
// In Tauri, the frontend is on a custom scheme and must reach localhost:8888 explicitly.
// In web mode (served from the same origin as the backend), relative URLs work and
// are simpler — no hardcoded host, no CORS preflight, no port assumptions.

/** Base URL for the backend.
 * - Tauri desktop: absolute URL pointing at the local Python server.
 * - Web browser:   empty string → relative paths (same origin).
 */
export const BACKEND_URL =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
    ? "http://localhost:8888"
    : "";

export const API_PREFIX = "/api/v1";

/** Full base for REST requests, e.g. "/api/v1" in web mode. */
export const API_BASE = `${BACKEND_URL}${API_PREFIX}`;
