<!-- FilesPanel.svelte — Poly-style file browser for the Agent OS.
     Updated: 2026-03-22 — Full-viewport tab (no floating window).
     No window chrome, no traffic lights, no drag/resize.
     AI sidebar is native — no branding header, just flows naturally.
-->
<script lang="ts">
  import { onMount, tick } from "svelte";
  import Home from "@lucide/svelte/icons/home";
  import Archive from "@lucide/svelte/icons/archive";
  import Bot from "@lucide/svelte/icons/bot";
  import Star from "@lucide/svelte/icons/star";
  import FolderOpen from "@lucide/svelte/icons/folder-open";
  import FileText from "@lucide/svelte/icons/file-text";
  import Image from "@lucide/svelte/icons/image";
  import Film from "@lucide/svelte/icons/film";
  import Music from "@lucide/svelte/icons/music";
  import File from "@lucide/svelte/icons/file";
  import Search from "@lucide/svelte/icons/search";
  import LayoutGrid from "@lucide/svelte/icons/layout-grid";
  import List from "@lucide/svelte/icons/list";
  import Columns3 from "@lucide/svelte/icons/columns-3";
  import GalleryHorizontalEnd from "@lucide/svelte/icons/gallery-horizontal-end";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import HardDrive from "@lucide/svelte/icons/hard-drive";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import Mic from "@lucide/svelte/icons/mic";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Wand2 from "@lucide/svelte/icons/wand-2";
  import Tags from "@lucide/svelte/icons/tags";
  import ScanSearch from "@lucide/svelte/icons/scan-search";
  import Palette from "@lucide/svelte/icons/palette";
  import Zap from "@lucide/svelte/icons/zap";
  import SlidersHorizontal from "@lucide/svelte/icons/sliders-horizontal";

  // --- Sidebar settings state ---
  let sidebarSettingsOpen = $state(false);
  let showHidden = $state(false);
  let sortBy = $state<"name" | "date" | "size">("date");
  let previewPane = $state(true);

  // --- AI Sidebar chat state ---
  type AiMessage = { id: string; role: "user" | "agent"; text: string };

  let aiMessages = $state<AiMessage[]>([]);
  let aiInput = $state("");
  let aiTyping = $state(false);
  let aiChatEl: HTMLDivElement | null = null;

  const AI_RESPONSES = [
    "Found 4 files matching that criteria. I've highlighted them in the grid.",
    "Done — tagged 8 files with auto-detected categories. Check the labels.",
    "I reorganized that folder by date. 3 subfolders created: 2024, 2025, 2026.",
    "Summarized: 12 PDFs (research), 5 images (diagrams), 3 markdown files (notes).",
    "Similar files found in 'Archive' and 'Shared Notes'. Want me to show duplicates?",
    "Generated thumbnails for 6 videos. They'll appear in grid view now.",
  ];

  async function scrollAiChat() {
    await tick();
    if (aiChatEl) aiChatEl.scrollTop = aiChatEl.scrollHeight;
  }

  async function sendAiMessage() {
    const text = aiInput.trim();
    if (!text || aiTyping) return;
    aiInput = "";
    aiMessages = [...aiMessages, { id: `u${Date.now()}`, role: "user", text }];
    await scrollAiChat();
    aiTyping = true;
    await scrollAiChat();
    await new Promise((r) => setTimeout(r, 600 + Math.random() * 600));
    aiMessages = [...aiMessages, {
      id: `a${Date.now()}`, role: "agent",
      text: AI_RESPONSES[Math.floor(Math.random() * AI_RESPONSES.length)],
    }];
    aiTyping = false;
    await scrollAiChat();
  }

  function handleAiKey(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiMessage(); }
  }

  function handleQuickAction(label: string) {
    aiInput = label;
    sendAiMessage();
  }

  // No props needed — full viewport tab, closing handled by parent tab toggle

  // --- Resizable sidebars ---
  let leftW = $state(180);
  let aiW = $state(220);
  let sidebarDragging = $state<"left" | "ai" | null>(null);
  let sidebarDragStart = { mx: 0, w: 0 };

  function onSidebarResizeDown(e: PointerEvent, which: "left" | "ai") {
    e.preventDefault();
    sidebarDragging = which;
    sidebarDragStart = { mx: e.clientX, w: which === "left" ? leftW : aiW };
    window.addEventListener("pointermove", onSidebarResizeMove);
    window.addEventListener("pointerup", onSidebarResizeUp);
  }
  function onSidebarResizeMove(e: PointerEvent) {
    const dx = e.clientX - sidebarDragStart.mx;
    if (sidebarDragging === "left") leftW = Math.max(120, Math.min(320, sidebarDragStart.w + dx));
    else if (sidebarDragging === "ai") aiW = Math.max(160, Math.min(400, sidebarDragStart.w - dx));
  }
  function onSidebarResizeUp() {
    sidebarDragging = null;
    window.removeEventListener("pointermove", onSidebarResizeMove);
    window.removeEventListener("pointerup", onSidebarResizeUp);
  }

  // --- View mode ---
  type ViewMode = "grid" | "list" | "column" | "gallery";
  let viewMode = $state<ViewMode>("grid");

  // --- Navigation ---
  type NavItem = { id: string; label: string; icon: any };
  const NAV_ITEMS: NavItem[] = [
    { id: "home", label: "Home", icon: Home },
    { id: "archive", label: "Archive", icon: Archive },
    { id: "agent", label: "Agent", icon: Bot },
  ];
  const FAVORITES: NavItem[] = [
    { id: "documents", label: "Documents", icon: FolderOpen },
    { id: "research", label: "Research", icon: Star },
    { id: "projects", label: "Projects", icon: FolderOpen },
  ];
  const SHARED: NavItem[] = [
    { id: "team-drive", label: "Team Drive", icon: HardDrive },
    { id: "shared-notes", label: "Shared Notes", icon: FileText },
  ];
  let activeNav = $state("home");

  // --- Mock files ---
  type FileItem = {
    id: string; name: string;
    type: "folder" | "image" | "document" | "video" | "audio" | "other";
    size: string; modified: string; color?: string;
  };

  const MOCK_FILES: FileItem[] = [
    { id: "f1", name: "Product Screenshots", type: "folder", size: "2.4 GB", modified: "2 hours ago", color: "#0A84FF" },
    { id: "f2", name: "Brand Assets", type: "folder", size: "890 MB", modified: "Yesterday", color: "#FF9F0A" },
    { id: "f3", name: "Research Notes", type: "folder", size: "156 MB", modified: "3 days ago", color: "#30D158" },
    { id: "f4", name: "Launch Plan.pdf", type: "document", size: "25 MB", modified: "1 hour ago" },
    { id: "f5", name: "Architecture Diagram.png", type: "image", size: "8.2 MB", modified: "5 hours ago" },
    { id: "f6", name: "Demo Recording.mp4", type: "video", size: "340 MB", modified: "Yesterday" },
    { id: "f7", name: "UI Mockups", type: "folder", size: "1.2 GB", modified: "2 days ago", color: "#BF5AF2" },
    { id: "f8", name: "README.md", type: "document", size: "12 KB", modified: "3 hours ago" },
    { id: "f9", name: "Podcast Episode.mp3", type: "audio", size: "45 MB", modified: "4 days ago" },
    { id: "f10", name: "Soul Protocol Spec", type: "folder", size: "67 MB", modified: "1 day ago", color: "#5E5CE6" },
    { id: "f11", name: "Competitor Analysis.xlsx", type: "document", size: "2.1 MB", modified: "6 hours ago" },
    { id: "f12", name: "Hero Image.webp", type: "image", size: "1.8 MB", modified: "Yesterday" },
    { id: "f13", name: "Meeting Notes.md", type: "document", size: "8 KB", modified: "30 min ago" },
    { id: "f14", name: "Prototypes", type: "folder", size: "456 MB", modified: "3 days ago", color: "#FF453A" },
    { id: "f15", name: "Team Photo.jpg", type: "image", size: "4.5 MB", modified: "1 week ago" },
    { id: "f16", name: "API Docs", type: "folder", size: "23 MB", modified: "2 days ago", color: "#0A84FF" },
  ];

  function getFileIcon(type: string) {
    switch (type) {
      case "folder": return FolderOpen;
      case "image": return Image;
      case "document": return FileText;
      case "video": return Film;
      case "audio": return Music;
      default: return File;
    }
  }

  // Fade in
  let visible = $state(false);
  onMount(() => { requestAnimationFrame(() => { visible = true; }); });
</script>

<!-- Full-viewport panel below top bar -->
<div class={visible ? "files-panel files-visible liquid-glass glass-noise" : "files-panel liquid-glass glass-noise"}>
  <!-- Toolbar: breadcrumb + search + view modes -->
  <header class="toolbar">
    <div class="breadcrumb">
      <span class="bc-item bc-root">Home</span>
      <ChevronRight size={12} strokeWidth={2} />
      <span class="bc-item bc-current">Personal</span>
    </div>
    <div class="toolbar-right">
      <button class="tb-btn"><Search size={14} strokeWidth={1.8} /></button>
      <div class="view-modes">
        <button class={viewMode === "grid" ? "vm-btn vm-active" : "vm-btn"} onclick={() => viewMode = "grid"} title="Grid"><LayoutGrid size={14} strokeWidth={1.8} /></button>
        <button class={viewMode === "list" ? "vm-btn vm-active" : "vm-btn"} onclick={() => viewMode = "list"} title="List"><List size={14} strokeWidth={1.8} /></button>
        <button class={viewMode === "column" ? "vm-btn vm-active" : "vm-btn"} onclick={() => viewMode = "column"} title="Column"><Columns3 size={14} strokeWidth={1.8} /></button>
        <button class={viewMode === "gallery" ? "vm-btn vm-active" : "vm-btn"} onclick={() => viewMode = "gallery"} title="Gallery"><GalleryHorizontalEnd size={14} strokeWidth={1.8} /></button>
      </div>
    </div>
  </header>

  <div class="body">
    <!-- Left sidebar -->
    <aside class="sidebar" style="width:{leftW}px">
      <div class="nav-section">
        {#each NAV_ITEMS as item}
          <button class={activeNav === item.id ? "nav-item nav-active" : "nav-item"} onclick={() => activeNav = item.id}>
            <item.icon size={14} strokeWidth={1.8} /><span>{item.label}</span>
          </button>
        {/each}
      </div>
      <div class="nav-label">Favorites</div>
      <div class="nav-section">
        {#each FAVORITES as item}
          <button class="nav-item" onclick={() => activeNav = item.id}>
            <item.icon size={14} strokeWidth={1.8} /><span>{item.label}</span>
          </button>
        {/each}
      </div>
      <div class="nav-label">Shared Drives</div>
      <div class="nav-section">
        {#each SHARED as item}
          <button class="nav-item" onclick={() => activeNav = item.id}>
            <item.icon size={14} strokeWidth={1.8} /><span>{item.label}</span>
          </button>
        {/each}
      </div>

      <!-- Sidebar settings footer -->
      <div class="sb-settings-spacer"></div>
      {#if sidebarSettingsOpen}
        <div class="sb-settings-panel">
          <div class="sb-setting-row">
            <span class="sb-setting-label">Sort by</span>
            <div class="sb-chips">
              <button class={sortBy === "name" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => sortBy = "name"}>Name</button>
              <button class={sortBy === "date" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => sortBy = "date"}>Date</button>
              <button class={sortBy === "size" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => sortBy = "size"}>Size</button>
            </div>
          </div>
          <div class="sb-setting-row">
            <span class="sb-setting-label">Hidden files</span>
            <button class={showHidden ? "sb-toggle sb-toggle-on" : "sb-toggle"} onclick={() => showHidden = !showHidden}>
              <span class="sb-toggle-knob"></span>
            </button>
          </div>
          <div class="sb-setting-row">
            <span class="sb-setting-label">Preview pane</span>
            <button class={previewPane ? "sb-toggle sb-toggle-on" : "sb-toggle"} onclick={() => previewPane = !previewPane}>
              <span class="sb-toggle-knob"></span>
            </button>
          </div>
        </div>
      {/if}
      <button class="sb-settings-trigger" class:sb-settings-active={sidebarSettingsOpen} onclick={() => sidebarSettingsOpen = !sidebarSettingsOpen}>
        <SlidersHorizontal size={13} strokeWidth={1.8} />
        <span>Settings</span>
      </button>
    </aside>
    <div class="sidebar-resize-handle" onpointerdown={(e) => onSidebarResizeDown(e, "left")}></div>

    <!-- File grid / list -->
    <main class="content">
      {#if viewMode === "grid" || viewMode === "gallery" || viewMode === "column"}
        <div class="file-grid">
          {#each MOCK_FILES as file}
            {@const Icon = getFileIcon(file.type)}
            <button class="file-card" title={file.name}>
              <div class="file-thumb" style={file.color ? `background:${file.color}20;` : ""}>
                <Icon size={file.type === "folder" ? 28 : 22} strokeWidth={1.5} style={file.color ? `color:${file.color}` : ""} />
              </div>
              <div class="file-info">
                <span class="file-name">{file.name}</span>
                <span class="file-meta">{file.size} · {file.modified}</span>
              </div>
            </button>
          {/each}
        </div>
      {:else}
        <div class="file-list">
          {#each MOCK_FILES as file}
            {@const Icon = getFileIcon(file.type)}
            <button class="list-row">
              <span class="list-icon" style={file.color ? `color:${file.color}` : ""}><Icon size={16} strokeWidth={1.8} /></span>
              <span class="list-name">{file.name}</span>
              <span class="list-meta">{file.modified}</span>
              <span class="list-size">{file.size}</span>
            </button>
          {/each}
        </div>
      {/if}
    </main>

    <div class="sidebar-resize-handle" onpointerdown={(e) => onSidebarResizeDown(e, "ai")}></div>

    <!-- AI Sidebar — no header, just actions and chat -->
    <aside class="ai-sidebar" style="width:{aiW}px">
      {#if aiMessages.length === 0}
        <!-- Quick actions — the AI just IS here -->
        <div class="ai-section">
          <div class="ai-section-label">Quick Actions</div>
          <button class="ai-action-btn" onclick={() => handleQuickAction("Find similar files in this folder")}>
            <ScanSearch size={14} strokeWidth={1.8} /><span>Find similar files</span>
          </button>
          <button class="ai-action-btn" onclick={() => handleQuickAction("Auto-tag all files in current view")}>
            <Tags size={14} strokeWidth={1.8} /><span>Auto-tag selected</span>
          </button>
          <button class="ai-action-btn" onclick={() => handleQuickAction("Organize this folder by type and date")}>
            <Wand2 size={14} strokeWidth={1.8} /><span>Organize folder</span>
          </button>
          <button class="ai-action-btn" onclick={() => handleQuickAction("Generate thumbnails for all media files")}>
            <Palette size={14} strokeWidth={1.8} /><span>Generate thumbnails</span>
          </button>
          <button class="ai-action-btn" onclick={() => handleQuickAction("Summarize contents of this folder")}>
            <Zap size={14} strokeWidth={1.8} /><span>Summarize contents</span>
          </button>
        </div>

        <div class="ai-section">
          <div class="ai-section-label">Recent Activity</div>
          <div class="ai-activity-item">
            <span class="ai-act-dot ai-act-done"></span>
            <span class="ai-act-text">Tagged 12 images with EXIF data</span>
          </div>
          <div class="ai-activity-item">
            <span class="ai-act-dot ai-act-done"></span>
            <span class="ai-act-text">Moved 3 duplicates to Archive</span>
          </div>
          <div class="ai-activity-item">
            <span class="ai-act-dot ai-act-pending"></span>
            <span class="ai-act-text">Indexing Research Notes folder...</span>
          </div>
        </div>
      {:else}
        <div class="ai-chat-area" bind:this={aiChatEl}>
          {#each aiMessages as msg (msg.id)}
            <div class={msg.role === "user" ? "ai-msg ai-msg-user" : "ai-msg ai-msg-agent"}>
              {#if msg.role === "agent"}
                <div class="ai-msg-avatar"><Sparkles size={10} strokeWidth={2} /></div>
              {/if}
              <div class={msg.role === "user" ? "ai-msg-bubble ai-bubble-user" : "ai-msg-bubble ai-bubble-agent"}>
                {msg.text}
              </div>
            </div>
          {/each}
          {#if aiTyping}
            <div class="ai-msg ai-msg-agent">
              <div class="ai-msg-avatar"><Sparkles size={10} strokeWidth={2} /></div>
              <div class="ai-msg-bubble ai-bubble-agent ai-typing-bubble">
                <span class="ai-typing-dot"></span><span class="ai-typing-dot"></span><span class="ai-typing-dot"></span>
              </div>
            </div>
          {/if}
        </div>
      {/if}

      <!-- Input — always at bottom -->
      <div class="ai-input-area">
        <div class="ai-input-row liquid-glass">
          <input
            class="ai-input" type="text" placeholder="Ask anything..."
            bind:value={aiInput} onkeydown={handleAiKey}
            disabled={aiTyping} autocomplete="off" spellcheck="false"
          />
          <button class="ai-send-btn" disabled={!aiInput.trim() || aiTyping} onclick={sendAiMessage}>
            <ArrowUp size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
    </aside>
  </div>
</div>

<style>
  /* Full viewport below top bar */
  .files-panel {
    position: fixed;
    top: 32px;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 50;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    opacity: 0;
    transition: opacity 200ms ease;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .files-visible { opacity: 1; }

  /* ---- Toolbar ---- */
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 36px;
    padding: 0 14px;
    flex-shrink: 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }

  .breadcrumb {
    display: flex; align-items: center; gap: 4px;
    color: rgba(255,255,255,0.40);
  }
  .bc-item { font-size: 12px; font-weight: 500; }
  .bc-root { color: rgba(255,255,255,0.50); cursor: pointer; }
  .bc-root:hover { color: rgba(255,255,255,0.80); }
  .bc-current { color: rgba(255,255,255,0.85); }

  .toolbar-right { display: flex; align-items: center; gap: 6px; }
  .tb-btn {
    width: 26px; height: 26px; border-radius: 6px; border: none; background: none;
    display: flex; align-items: center; justify-content: center;
    color: rgba(255,255,255,0.45); cursor: pointer;
    transition: color 0.12s, background 0.12s;
  }
  .tb-btn:hover { color: rgba(255,255,255,0.80); background: rgba(255,255,255,0.08); }

  .view-modes {
    display: flex; align-items: center; gap: 2px;
    background: rgba(255,255,255,0.05); border-radius: 6px; padding: 2px;
  }
  .vm-btn {
    width: 24px; height: 24px; border-radius: 4px; border: none; background: none;
    display: flex; align-items: center; justify-content: center;
    color: rgba(255,255,255,0.40); cursor: pointer; transition: color 0.12s, background 0.12s;
  }
  .vm-btn:hover { color: rgba(255,255,255,0.70); }
  .vm-active { color: rgba(255,255,255,0.90); background: rgba(255,255,255,0.10); }

  /* ---- Body ---- */
  .body { display: flex; flex: 1; min-height: 0; }

  /* Sidebar resize handle */
  .sidebar-resize-handle {
    width: 5px; flex-shrink: 0; cursor: col-resize;
    position: relative; z-index: 5; margin: 0 -2px;
    transition: background 0.15s;
  }
  .sidebar-resize-handle:hover { background: rgba(255,255,255,0.08); }

  /* ---- Left sidebar ---- */
  .sidebar {
    flex-shrink: 0;
    border-right: 1px solid rgba(255,255,255,0.06);
    padding: 10px 8px;
    overflow-y: auto;
    display: flex; flex-direction: column; gap: 4px;
    scrollbar-width: none;
  }
  .sidebar::-webkit-scrollbar { display: none; }

  .nav-label {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; color: rgba(255,255,255,0.32);
    padding: 12px 10px 5px; margin-top: 4px;
  }
  .nav-section { display: flex; flex-direction: column; gap: 2px; }
  .nav-item {
    display: flex; align-items: center; gap: 9px;
    padding: 7px 10px; border-radius: 7px; border: none; background: none;
    color: rgba(255,255,255,0.65); font-size: 13px; font-family: inherit;
    text-align: left; cursor: pointer; transition: color 0.12s, background 0.12s;
  }
  .nav-item:hover { color: rgba(255,255,255,0.85); background: rgba(255,255,255,0.06); }
  .nav-active { color: rgba(255,255,255,0.95); background: rgba(255,255,255,0.10); font-weight: 500; }

  /* ---- Content ---- */
  .content {
    flex: 1; min-width: 0; overflow-y: auto; padding: 12px;
    scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.10) transparent;
  }
  .content::-webkit-scrollbar { width: 4px; }
  .content::-webkit-scrollbar-track { background: transparent; }
  .content::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.10); border-radius: 2px; }

  /* Grid */
  .file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
  }
  .file-card {
    display: flex; flex-direction: column; border: none; background: none;
    border-radius: 10px; padding: 0; cursor: pointer; overflow: hidden;
    transition: background 0.12s; font-family: inherit; text-align: left;
  }
  .file-card:hover { background: rgba(255,255,255,0.06); }
  .file-thumb {
    aspect-ratio: 1; border-radius: 10px;
    background: rgba(255,255,255,0.04);
    display: flex; align-items: center; justify-content: center;
    color: rgba(255,255,255,0.50); margin: 4px;
    transition: background 0.12s;
  }
  .file-card:hover .file-thumb { background: rgba(255,255,255,0.08); }
  .file-info { padding: 6px 8px 8px; }
  .file-name {
    font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.88);
    display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .file-meta { font-size: 11px; color: rgba(255,255,255,0.40); margin-top: 2px; display: block; }

  /* List */
  .file-list { display: flex; flex-direction: column; gap: 1px; }
  .list-row {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 10px; border-radius: 6px; border: none; background: none;
    cursor: pointer; font-family: inherit; text-align: left; transition: background 0.10s;
  }
  .list-row:hover { background: rgba(255,255,255,0.06); }
  .list-icon { display: flex; color: rgba(255,255,255,0.50); flex-shrink: 0; }
  .list-name {
    flex: 1; font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.85);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .list-meta { font-size: 11px; color: rgba(255,255,255,0.35); flex-shrink: 0; width: 80px; text-align: right; }
  .list-size {
    font-size: 11px; color: rgba(255,255,255,0.30); flex-shrink: 0; width: 60px; text-align: right;
    font-family: "SF Mono", "JetBrains Mono", monospace;
  }

  /* ---- AI Sidebar ---- */
  .ai-sidebar {
    flex-shrink: 0;
    border-left: 1px solid rgba(255,255,255,0.06);
    display: flex; flex-direction: column;
    overflow: hidden;
  }

  .ai-section { padding: 14px 14px; display: flex; flex-direction: column; gap: 3px; }
  .ai-section-label {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; color: rgba(255,255,255,0.35);
    padding: 0 6px 8px;
  }
  .ai-action-btn {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 10px; border-radius: 8px; border: none; background: none;
    color: rgba(255,255,255,0.65); font-size: 13px; font-family: inherit;
    text-align: left; cursor: pointer; transition: color 0.12s, background 0.12s;
  }
  .ai-action-btn:hover { color: rgba(255,255,255,0.95); background: rgba(255,255,255,0.07); }

  .ai-activity-item { display: flex; align-items: flex-start; gap: 10px; padding: 7px 10px; }
  .ai-act-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
  .ai-act-done { background: #30D158; }
  .ai-act-pending { background: #FF9F0A; animation: pulse-dot 1.6s ease-in-out infinite; }
  @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  .ai-act-text { font-size: 13px; color: rgba(255,255,255,0.55); line-height: 1.45; }

  /* AI Chat */
  .ai-chat-area {
    flex: 1; overflow-y: auto; padding: 10px;
    display: flex; flex-direction: column; gap: 8px;
    scrollbar-width: none;
  }
  .ai-chat-area::-webkit-scrollbar { display: none; }
  .ai-msg { display: flex; align-items: flex-end; gap: 6px; }
  .ai-msg-user { flex-direction: row-reverse; }
  .ai-msg-avatar {
    width: 20px; height: 20px; border-radius: 6px;
    background: linear-gradient(135deg, rgba(10,132,255,0.25), rgba(191,90,242,0.25));
    display: flex; align-items: center; justify-content: center;
    color: #0A84FF; flex-shrink: 0; margin-bottom: 1px;
  }
  .ai-msg-bubble {
    max-width: 85%; padding: 8px 12px;
    font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.85); border-radius: 10px;
  }
  .ai-bubble-user {
    background: rgba(10,132,255,0.15); border: 1px solid rgba(10,132,255,0.18);
    border-radius: 10px 10px 4px 10px;
  }
  .ai-bubble-agent {
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px 10px 10px 4px;
  }
  .ai-typing-bubble { display: flex; align-items: center; gap: 3px; padding: 9px 12px; }
  .ai-typing-dot {
    width: 5px; height: 5px; border-radius: 50%; background: rgba(255,255,255,0.35);
    animation: ai-dot-bounce 1.2s ease-in-out infinite;
  }
  .ai-typing-dot:nth-child(2) { animation-delay: 0.15s; }
  .ai-typing-dot:nth-child(3) { animation-delay: 0.30s; }
  @keyframes ai-dot-bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
    40% { transform: translateY(-3px); opacity: 0.8; }
  }

  /* AI Input — needs to be clearly visible */
  .ai-input-area { margin-top: auto; padding: 12px 12px 14px; }
  .ai-input-row {
    display: flex; align-items: center; gap: 8px;
    border-radius: 12px; padding: 0 8px 0 14px; height: 42px;
    /* Override liquid-glass with stronger border for visibility */
    border: 1px solid rgba(255,255,255,0.18) !important;
    background-color: rgba(255,255,255,0.08) !important;
  }
  .ai-input-row:focus-within {
    border-color: rgba(255,255,255,0.30) !important;
    background-color: rgba(255,255,255,0.12) !important;
  }
  .ai-input {
    flex: 1; background: none; border: none; outline: none;
    font-size: 13px; font-family: inherit; color: rgba(255,255,255,0.85);
  }
  .ai-input::placeholder { color: rgba(255,255,255,0.40); }
  .ai-send-btn {
    width: 28px; height: 28px; border-radius: 50%; border: none;
    background: rgba(255,255,255,0.20); color: rgba(255,255,255,0.80);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; flex-shrink: 0; transition: background 0.12s;
  }
  .ai-send-btn:hover { background: rgba(255,255,255,0.32); }
  .ai-send-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  /* ---- Sidebar settings footer ---- */
  .sb-settings-spacer { flex: 1; min-height: 12px; }
  .sb-settings-trigger {
    display: flex; align-items: center; gap: 7px;
    width: 100%; padding: 8px 10px; border-radius: 7px;
    border: none; background: none;
    color: rgba(255,255,255,0.38); font-size: 12px; font-family: inherit;
    cursor: pointer; transition: background 0.12s, color 0.12s; flex-shrink: 0;
  }
  .sb-settings-trigger:hover { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.70); }
  .sb-settings-active { color: #0A84FF !important; background: rgba(10,132,255,0.10) !important; }
  .sb-settings-panel {
    display: flex; flex-direction: column; gap: 10px;
    padding: 10px; border-radius: 8px;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 4px; flex-shrink: 0;
    animation: sb-in 0.12s ease-out;
  }
  @keyframes sb-in {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .sb-setting-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .sb-setting-label { font-size: 11px; color: rgba(255,255,255,0.45); flex-shrink: 0; }
  .sb-chips { display: flex; gap: 3px; }
  .sb-chip {
    padding: 3px 7px; border-radius: 5px; border: none;
    background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.45);
    font-size: 11px; font-family: inherit; cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .sb-chip:hover { background: rgba(255,255,255,0.10); color: rgba(255,255,255,0.75); }
  .sb-chip-active { background: rgba(10,132,255,0.18) !important; color: #0A84FF !important; }
  .sb-toggle {
    position: relative; width: 30px; height: 17px; border-radius: 9px;
    border: none; cursor: pointer; background: rgba(255,255,255,0.12);
    transition: background 0.15s; flex-shrink: 0; padding: 0;
  }
  .sb-toggle-on { background: rgba(10,132,255,0.55); }
  .sb-toggle-knob {
    position: absolute; top: 2px; left: 2px;
    width: 13px; height: 13px; border-radius: 50%;
    background: rgba(255,255,255,0.75); transition: left 0.15s;
  }
  .sb-toggle-on .sb-toggle-knob { left: 15px; background: white; }
</style>
