// local.ts — LocalFileSystem provider using Tauri IPC with REST API fallback for web mode
// Modified: 2026-03-21 — Added REST API fallbacks for readDir and readFileText when not running in Tauri

import type { FileEntry, DefaultDirs, FileChangeEvent, FileSystemProvider, RecursiveSearchResult } from "./types";
import { getThumbnail as getCachedThumbnail } from "./thumbnail-cache";
import { API_BASE } from "$lib/api/config";

/** Raw shape returned by the Rust fs_read_dir command */
interface RawFileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified: number;
  extension: string;
}

/** Extended stat info returned by fs_stat_extended */
export interface FileStatExtended {
  name: string;
  path: string;
  isDir: boolean;
  size: number;
  modified: number;
  created: number;
  extension: string;
  readonly: boolean;
  isSymlink: boolean;
}

interface RawFileStatExtended {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified: number;
  created: number;
  extension: string;
  readonly: boolean;
  is_symlink: boolean;
}

/** REST API response shape for /api/v1/files/browse */
interface ApiBrowseEntry {
  name: string;
  isDir: boolean;
  size: string;
}

interface ApiBrowseResponse {
  path: string;
  files: ApiBrowseEntry[];
  error?: string | null;
}

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function mapEntry(raw: RawFileEntry): FileEntry {
  return {
    name: raw.name,
    path: raw.path,
    isDir: raw.is_dir,
    size: raw.size,
    modified: raw.modified,
    extension: raw.extension,
    source: "local",
  };
}

/** Map a REST API browse entry to a FileEntry (best-effort — path derived from parent + name) */
function mapApiBrowseEntry(raw: ApiBrowseEntry, parentPath: string): FileEntry {
  const sep = parentPath.endsWith("/") ? "" : "/";
  return {
    name: raw.name,
    path: `${parentPath}${sep}${raw.name}`,
    isDir: raw.isDir,
    // REST API returns human-readable size string — convert back to approximate bytes
    size: 0,
    modified: 0,
    extension: raw.isDir ? "" : (raw.name.includes(".") ? raw.name.split(".").pop() ?? "" : ""),
    source: "local",
  };
}

export class LocalFileSystem implements FileSystemProvider {
  scheme = "local" as const;

  async readDir(path: string): Promise<FileEntry[]> {
    if (!isTauri()) {
      // Web mode: fall back to the REST browse endpoint
      try {
        const url = `${API_BASE}/files/browse?path=${encodeURIComponent(path)}`;
        const resp = await fetch(url, { credentials: "include" });
        if (!resp.ok) return [];
        const data: ApiBrowseResponse = await resp.json();
        if (data.error) return [];
        return (data.files ?? []).map((e) => mapApiBrowseEntry(e, path));
      } catch {
        return [];
      }
    }
    const { invoke } = await import("@tauri-apps/api/core");
    const raw: RawFileEntry[] = await invoke("fs_read_dir", { path });
    return raw.map(mapEntry);
  }

  async readFileText(path: string): Promise<string> {
    if (!isTauri()) {
      // Web mode: fall back to the REST content endpoint
      try {
        const url = `${API_BASE}/files/content?path=${encodeURIComponent(path)}`;
        const resp = await fetch(url, { credentials: "include" });
        if (!resp.ok) return "";
        return resp.text();
      } catch {
        return "";
      }
    }
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("fs_read_file_text", { path });
  }

  async writeFile(path: string, content: string): Promise<void> {
    if (!isTauri()) {
      // Web mode: fall back to the REST write endpoint
      try {
        await fetch(`${API_BASE}/files/write`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, content }),
        });
      } catch {
        // Silently fail — caller can check by reading back
      }
      return;
    }
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_write_file", { path, content });
  }

  async deleteFile(path: string, recursive = false): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_delete", { path, recursive });
  }

  async rename(oldPath: string, newPath: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_rename", { oldPath, newPath });
  }

  async stat(path: string): Promise<FileEntry> {
    if (!isTauri()) {
      return { name: "", path, isDir: false, size: 0, modified: 0, extension: "", source: "local" };
    }
    const { invoke } = await import("@tauri-apps/api/core");
    const raw: RawFileEntry = await invoke("fs_stat", { path });
    return mapEntry(raw);
  }

  async createDir(path: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_create_dir", { path });
  }

  async exists(path: string): Promise<boolean> {
    if (!isTauri()) return false;
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("fs_exists", { path });
  }

  async watch(path: string, callback: (event: FileChangeEvent) => void): Promise<() => void> {
    if (!isTauri()) return () => {};
    const { invoke } = await import("@tauri-apps/api/core");
    const { listen } = await import("@tauri-apps/api/event");

    await invoke("fs_watch", { path });

    const unlisten = await listen<FileChangeEvent>("fs-change", (e) => {
      callback(e.payload);
    });

    return async () => {
      unlisten();
      try {
        await invoke("fs_unwatch");
      } catch {
        // Ignore cleanup errors
      }
    };
  }

  async getDefaultDirs(): Promise<DefaultDirs> {
    if (!isTauri()) {
      return { home: "", documents: "", downloads: "", desktop: "" };
    }
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("fs_get_default_dirs");
  }

  /** Local-only: read the first N bytes of a file as text (safe for large files) */
  async readFileHead(path: string, maxBytes: number = 2048): Promise<string> {
    if (!isTauri()) return "";
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("fs_read_file_head", { path, maxBytes });
  }

  /** Local-only: get a thumbnail data URL for an image file */
  async getThumbnail(path: string): Promise<string | null> {
    return getCachedThumbnail(path);
  }

  /** Local-only: get an asset URL for direct webview loading (audio/video/pdf) */
  async getFileSrc(path: string): Promise<string> {
    if (!isTauri()) return "";
    const { convertFileSrc } = await import("@tauri-apps/api/core");
    return convertFileSrc(path);
  }

  /** Local-only: read a binary file as a base64 data URL */
  async readFileBase64(path: string): Promise<string> {
    if (!isTauri()) return "";
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("fs_read_file_base64", { path });
  }

  /** Copy a single file from src to dest */
  async copyFile(src: string, dest: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_copy_file", { src, dest });
  }

  /** Recursively copy a directory from src to dest */
  async copyDir(src: string, dest: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_copy_dir", { src, dest });
  }

  /** Move a file or directory (uses rename under the hood) */
  async moveFile(src: string, dest: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_rename", { oldPath: src, newPath: dest });
  }

  /** Get extended stat info for a file */
  async statExtended(path: string): Promise<FileStatExtended> {
    if (!isTauri()) {
      return {
        name: "", path, isDir: false, size: 0, modified: 0, created: 0,
        extension: "", readonly: false, isSymlink: false,
      };
    }
    const { invoke } = await import("@tauri-apps/api/core");
    const raw: RawFileStatExtended = await invoke("fs_stat_extended", { path });
    return {
      name: raw.name,
      path: raw.path,
      isDir: raw.is_dir,
      size: raw.size,
      modified: raw.modified,
      created: raw.created,
      extension: raw.extension,
      readonly: raw.readonly,
      isSymlink: raw.is_symlink,
    };
  }

  /** Open a terminal at the given path */
  async openInTerminal(path: string): Promise<void> {
    if (!isTauri()) return;
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("fs_open_in_terminal", { path });
  }

  /** Recursively search for files matching a query within a directory tree */
  async searchRecursive(
    rootPath: string,
    query: string,
    maxResults = 500,
    maxDepth = 10,
  ): Promise<RecursiveSearchResult> {
    if (!isTauri()) return { entries: [], totalScanned: 0, truncated: false };
    const { invoke } = await import("@tauri-apps/api/core");
    const raw: { entries: RawFileEntry[]; total_scanned: number; truncated: boolean } =
      await invoke("fs_search_recursive", { rootPath, query, maxResults, maxDepth });
    return {
      entries: raw.entries.map(mapEntry),
      totalScanned: raw.total_scanned,
      truncated: raw.truncated,
    };
  }
}
