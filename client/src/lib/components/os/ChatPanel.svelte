<!-- ChatPanel.svelte — Full-viewport Chat tab with session history sidebar.
     Updated: 2026-03-22 — Added session list sidebar, new chat button,
     reduced glass on bubbles (subtle bg instead of liquid-glass).
-->
<script lang="ts">
  import { onMount, tick } from "svelte";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Mic from "@lucide/svelte/icons/mic";
  import Video from "@lucide/svelte/icons/video";
  import Phone from "@lucide/svelte/icons/phone";
  import Plus from "@lucide/svelte/icons/plus";
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import Search from "@lucide/svelte/icons/search";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import Clock from "@lucide/svelte/icons/clock";
  import SlidersHorizontal from "@lucide/svelte/icons/sliders-horizontal";

  let { onClose }: { onClose: () => void } = $props();

  // --- Sidebar settings state ---
  let sidebarSettingsOpen = $state(false);
  let chatModel = $state<"claude" | "gpt4" | "gemini">("claude");
  let responseStyle = $state<"fast" | "balanced" | "deep">("balanced");
  let memoryEnabled = $state(true);
  let streamEnabled = $state(true);

  type Role = "user" | "agent";
  type Message = { id: string; role: Role; content: string; time: string };
  type Session = { id: string; title: string; preview: string; time: string; messages: Message[] };

  function nowTime() {
    return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  // --- Mock sessions ---
  const SEED_SESSIONS: Session[] = [
    {
      id: "s1", title: "Competitive analysis setup", preview: "I'll set up a complete competitive analysis workspace...", time: "Today",
      messages: [
        { id: "m1", role: "user", content: "Help me set up a competitive analysis workflow", time: "09:14" },
        { id: "m2", role: "agent", content: "I'll set up a complete competitive analysis workspace for you. Here's my plan:\n\n1. Research Setup\n  • Configure web search tool for competitor monitoring\n  • Set up scheduled searches for pricing changes\n  • Create a dedicated memory space for competitive intel\n\n2. Analysis Framework\n  • Build comparison templates (pricing, features, positioning)\n  • Set up automated data collection from 3 sources\n  • Create a summary dashboard Pocket\n\n3. Reporting Pipeline\n  • Weekly digest generation\n  • Slack/Discord alerts for major changes\n  • Monthly trend analysis with charts", time: "09:14" },
      ],
    },
    {
      id: "s2", title: "Soul Protocol spec review", preview: "The memory architecture uses 5 tiers with ACT-R...", time: "Today",
      messages: [
        { id: "m3", role: "user", content: "Review the soul protocol memory architecture", time: "11:30" },
        { id: "m4", role: "agent", content: "The memory architecture uses 5 tiers with ACT-R activation decay:\n\n1. Core Memory — always loaded, persona + human relationship\n2. Episodic — timestamped interactions (10K max)\n3. Semantic — extracted facts (1K max)\n4. Procedural — learned patterns and skills\n5. Knowledge Graph — entity relationships\n\nSignificance gating (LIDA) filters what gets stored. Only interactions scoring above 0.35 become memories.", time: "11:31" },
      ],
    },
    {
      id: "s3", title: "Deploy fixes to staging", preview: "Deployed the auth fix. Tests are passing...", time: "Yesterday",
      messages: [
        { id: "m5", role: "user", content: "Deploy the auth fix to staging", time: "16:42" },
        { id: "m6", role: "agent", content: "Deployed the auth fix to staging. All 14 tests passing. The rate limiter exemption for /_app/ is also live.", time: "16:43" },
      ],
    },
    {
      id: "s4", title: "Brew & Co. inventory alert", preview: "Oat milk is critically low — only 2 cartons...", time: "Yesterday",
      messages: [
        { id: "m7", role: "user", content: "What's low in inventory?", time: "08:15" },
        { id: "m8", role: "agent", content: "Oat milk is critically low — only 2 cartons left. I've notified the supplier. Croissants are at 12 (need to reorder by 4pm). Cold brew keg has 1 remaining. Everything else looks good for today.", time: "08:15" },
      ],
    },
    {
      id: "s5", title: "Launch timeline planning", preview: "Here's the 4-week plan: Week 1-2 prep...", time: "3 days ago",
      messages: [
        { id: "m9", role: "user", content: "Plan the launch timeline", time: "14:00" },
        { id: "m10", role: "agent", content: "Here's the 4-week plan:\n\n1. Week 1-2: Prep (README, RFCs, docs audit)\n2. Week 3: Launch (Monday GitHub, Tuesday HN, Wed-Fri Reddit + Twitter)\n3. Week 4: Monitor metrics, engage community, plan next phase\n\nSuccess metrics: 100+ HN upvotes, 50+ GitHub stars, 1-3 interested DMs.", time: "14:01" },
      ],
    },
  ];

  let sessions = $state<Session[]>([...SEED_SESSIONS]);
  let activeSessionId = $state<string>("s1");
  let searchQuery = $state("");

  let activeSession = $derived(sessions.find(s => s.id === activeSessionId) || sessions[0]);
  let messages = $derived(activeSession?.messages || []);

  let filteredSessions = $derived(
    searchQuery.trim() === ""
      ? sessions
      : sessions.filter(s =>
          s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.preview.toLowerCase().includes(searchQuery.toLowerCase())
        )
  );

  let inputValue = $state("");
  let isTyping = $state(false);
  let messagesEl: HTMLDivElement | null = null;

  const MOCK_RESPONSES = [
    "Got it. I'm on it — I'll update you when this is done.",
    "Great idea. Let me research that and come back with a structured plan.",
    "Sure, I'll configure that right now. You should see the results in a few seconds.",
    "I've noted that. Want me to create a Pocket for this or add it to an existing one?",
    "Interesting. I'll analyze that and give you a detailed breakdown shortly.",
  ];

  async function scrollToBottom() {
    await tick();
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function sendMessage() {
    const text = inputValue.trim();
    if (!text || isTyping || !activeSession) return;
    inputValue = "";

    activeSession.messages = [...activeSession.messages,
      { id: `m${Date.now()}`, role: "user", content: text, time: nowTime() },
    ];
    await scrollToBottom();

    isTyping = true;
    await scrollToBottom();
    await new Promise((r) => setTimeout(r, 800));

    activeSession.messages = [...activeSession.messages, {
      id: `m${Date.now() + 1}`, role: "agent",
      content: MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)],
      time: nowTime(),
    }];
    isTyping = false;
    await scrollToBottom();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  function newChat() {
    const id = `s${Date.now()}`;
    const session: Session = {
      id, title: "New conversation", preview: "", time: "Just now", messages: [],
    };
    sessions = [session, ...sessions];
    activeSessionId = id;
  }

  function deleteSession(id: string) {
    sessions = sessions.filter(s => s.id !== id);
    if (activeSessionId === id) {
      activeSessionId = sessions[0]?.id || "";
    }
  }

  function renderMarkdown(text: string): string {
    const lines = text.split("\n");
    const out: string[] = [];
    for (const line of lines) {
      if (/^\s+[•·-]\s/.test(line)) { out.push(`<div class="md-bullet">${inlineMd(line.replace(/^\s+[•·-]\s/, ""))}</div>`); continue; }
      if (/^\d+\.\s/.test(line)) { out.push(`<div class="md-numbered">${inlineMd(line)}</div>`); continue; }
      if (line.trim() === "") { out.push('<div class="md-gap"></div>'); continue; }
      out.push(`<div class="md-line">${inlineMd(line)}</div>`);
    }
    return out.join("");
  }

  function inlineMd(text: string): string {
    return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  // Resizable sidebar
  let sidebarW = $state(260);
  let sidebarDragging = $state(false);
  let sidebarDragStart = { mx: 0, w: 0 };
  function onSidebarResize(e: PointerEvent) {
    e.preventDefault();
    sidebarDragging = true;
    sidebarDragStart = { mx: e.clientX, w: sidebarW };
    window.addEventListener("pointermove", onSidebarMove);
    window.addEventListener("pointerup", onSidebarUp);
  }
  function onSidebarMove(e: PointerEvent) {
    sidebarW = Math.max(200, Math.min(400, sidebarDragStart.w + (e.clientX - sidebarDragStart.mx)));
  }
  function onSidebarUp() {
    sidebarDragging = false;
    window.removeEventListener("pointermove", onSidebarMove);
    window.removeEventListener("pointerup", onSidebarUp);
  }

  let visible = $state(false);
  onMount(() => { scrollToBottom(); requestAnimationFrame(() => { visible = true; }); });
</script>

<div class={visible ? "chat-panel chat-visible liquid-glass glass-noise" : "chat-panel liquid-glass glass-noise"}>
  <div class="chat-body">
    <!-- Session history sidebar -->
    <aside class="session-sidebar" style="width:{sidebarW}px">
      <div class="sidebar-header">
        <button class="new-chat-btn" onclick={newChat}>
          <Plus size={14} strokeWidth={2} />
          <span>New Chat</span>
        </button>
      </div>

      <div class="search-row">
        <Search size={13} strokeWidth={1.8} />
        <input
          class="search-input" type="text" placeholder="Search chats..."
          bind:value={searchQuery} autocomplete="off" spellcheck="false"
        />
      </div>

      <div class="session-list">
        {#each filteredSessions as session (session.id)}
          <div
            class={session.id === activeSessionId ? "session-item session-active" : "session-item"}
            onclick={() => { activeSessionId = session.id; }}
            role="button"
            tabindex="0"
          >
            <div class="session-content">
              <span class="session-title">{session.title}</span>
              <span class="session-preview">{session.preview}</span>
            </div>
            <div class="session-meta">
              <span class="session-time">{session.time}</span>
              <button
                class="session-delete"
                onclick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                title="Delete"
              >
                <Trash2 size={12} strokeWidth={1.8} />
              </button>
            </div>
          </div>
        {/each}
      </div>

      <!-- Sidebar settings footer -->
      <div class="sb-settings-spacer"></div>
      {#if sidebarSettingsOpen}
        <div class="sb-settings-panel">
          <div class="sb-setting-row">
            <span class="sb-setting-label">Model</span>
            <div class="sb-chips">
              <button class={chatModel === "claude" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => chatModel = "claude"}>Claude</button>
              <button class={chatModel === "gpt4" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => chatModel = "gpt4"}>GPT-4</button>
              <button class={chatModel === "gemini" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => chatModel = "gemini"}>Gemini</button>
            </div>
          </div>
          <div class="sb-setting-row">
            <span class="sb-setting-label">Style</span>
            <div class="sb-chips">
              <button class={responseStyle === "fast" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => responseStyle = "fast"}>Fast</button>
              <button class={responseStyle === "balanced" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => responseStyle = "balanced"}>Balanced</button>
              <button class={responseStyle === "deep" ? "sb-chip sb-chip-active" : "sb-chip"} onclick={() => responseStyle = "deep"}>Deep</button>
            </div>
          </div>
          <div class="sb-setting-row">
            <span class="sb-setting-label">Memory</span>
            <button class={memoryEnabled ? "sb-toggle sb-toggle-on" : "sb-toggle"} onclick={() => memoryEnabled = !memoryEnabled}>
              <span class="sb-toggle-knob"></span>
            </button>
          </div>
          <div class="sb-setting-row">
            <span class="sb-setting-label">Streaming</span>
            <button class={streamEnabled ? "sb-toggle sb-toggle-on" : "sb-toggle"} onclick={() => streamEnabled = !streamEnabled}>
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

    <div class="sidebar-resize" onpointerdown={onSidebarResize}></div>

    <!-- Main chat area -->
    <main class="chat-main">
      <div class="messages-area" bind:this={messagesEl} aria-live="polite">
        <div class="messages-inner">
          {#if messages.length === 0}
            <div class="empty-chat">
              <img class="empty-avatar" src="/paw-avatar.png" alt="" />
              <p class="empty-text">Start a new conversation</p>
            </div>
          {:else}
            {#each messages as msg (msg.id)}
              {#if msg.role === "user"}
                <div class="msg msg-user">
                  <div class="user-bubble">{msg.content}</div>
                </div>
              {:else}
                <div class="msg msg-agent">
                  <img class="agent-avatar" src="/paw-avatar.png" alt="" />
                  <div class="agent-card">
                    <div class="md-content">{@html renderMarkdown(msg.content)}</div>
                  </div>
                </div>
              {/if}
            {/each}

            {#if isTyping}
              <div class="msg msg-agent">
                <img class="agent-avatar" src="/paw-avatar.png" alt="" />
                <div class="agent-card typing-card">
                  <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
                </div>
              </div>
            {/if}
          {/if}
        </div>
      </div>

      <footer class="input-footer">
        <div class="input-pill liquid-glass">
          <img class="input-avatar" src="/paw-avatar.png" alt="" aria-hidden="true" />
          <input
            class="chat-input" type="text" placeholder="Type your message..."
            bind:value={inputValue} onkeydown={handleKeydown}
            disabled={isTyping} autocomplete="off" spellcheck="false"
          />
          <span class="input-action"><Mic size={16} strokeWidth={1.8} /></span>
          <span class="input-action"><Video size={16} strokeWidth={1.8} /></span>
          <span class="input-action"><Phone size={16} strokeWidth={1.8} /></span>
          <button class="send-btn" onclick={sendMessage} disabled={!inputValue.trim() || isTyping}>
            <ArrowUp size={16} strokeWidth={2} />
          </button>
        </div>
      </footer>
    </main>
  </div>
</div>

<style>
  .chat-panel {
    position: fixed;
    top: 32px; left: 0; right: 0; bottom: 0;
    z-index: 50; display: flex; flex-direction: column;
    overflow: hidden; opacity: 0; transition: opacity 200ms ease;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .chat-visible { opacity: 1; }

  .chat-body { display: flex; flex: 1; min-height: 0; }

  /* ---- Session sidebar ---- */
  .session-sidebar {
    flex-shrink: 0;
    border-right: 1px solid rgba(255,255,255,0.06);
    display: flex; flex-direction: column;
    overflow: hidden;
  }

  .sidebar-header {
    padding: 10px 10px 6px;
    flex-shrink: 0;
  }

  .new-chat-btn {
    display: flex; align-items: center; gap: 7px;
    width: 100%; padding: 8px 12px;
    border-radius: 8px; border: none;
    background: rgba(10,132,255,0.12);
    color: #0A84FF; font-size: 13px; font-weight: 500;
    font-family: inherit; cursor: pointer;
    transition: background 0.12s;
  }
  .new-chat-btn:hover { background: rgba(10,132,255,0.20); }

  .search-row {
    display: flex; align-items: center; gap: 8px;
    margin: 4px 10px 8px; padding: 6px 10px;
    border-radius: 8px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.35);
  }
  .search-input {
    flex: 1; background: none; border: none; outline: none;
    font-size: 12px; font-family: inherit;
    color: rgba(255,255,255,0.80);
  }
  .search-input::placeholder { color: rgba(255,255,255,0.30); }

  .session-list {
    flex: 1; overflow-y: auto; padding: 0 6px 8px;
    display: flex; flex-direction: column; gap: 2px;
    scrollbar-width: none;
  }
  .session-list::-webkit-scrollbar { display: none; }

  .session-item {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 8px; padding: 10px 10px;
    border-radius: 8px; border: none; background: none;
    cursor: pointer; font-family: inherit; text-align: left;
    transition: background 0.12s;
    width: 100%;
  }
  .session-item:hover { background: rgba(255,255,255,0.06); }
  .session-active { background: rgba(255,255,255,0.10); }

  .session-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .session-title {
    font-size: 13px; font-weight: 500; color: rgba(255,255,255,0.85);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .session-preview {
    font-size: 11px; color: rgba(255,255,255,0.38);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  .session-meta {
    display: flex; flex-direction: column; align-items: flex-end; gap: 4px;
    flex-shrink: 0;
  }
  .session-time {
    font-size: 10px; color: rgba(255,255,255,0.30);
  }
  .session-delete {
    opacity: 0; width: 20px; height: 20px; border-radius: 4px;
    border: none; background: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    color: rgba(255,255,255,0.35); transition: opacity 0.12s, color 0.12s;
  }
  .session-item:hover .session-delete { opacity: 1; }
  .session-delete:hover { color: rgba(255,100,90,0.90); background: rgba(255,70,60,0.12); }

  /* Resize handle */
  .sidebar-resize {
    width: 5px; flex-shrink: 0; cursor: col-resize;
    position: relative; z-index: 5; margin: 0 -2px;
    transition: background 0.15s;
  }
  .sidebar-resize:hover { background: rgba(255,255,255,0.08); }

  /* ---- Main chat ---- */
  .chat-main {
    flex: 1; min-width: 0; display: flex; flex-direction: column;
  }

  .messages-area {
    flex: 1; overflow-y: auto; padding: 24px 16px;
    display: flex; justify-content: center;
    scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.10) transparent;
  }
  .messages-area::-webkit-scrollbar { width: 4px; }
  .messages-area::-webkit-scrollbar-track { background: transparent; }
  .messages-area::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.10); border-radius: 2px; }

  .messages-inner {
    width: 100%; max-width: 720px;
    display: flex; flex-direction: column; gap: 18px;
  }

  /* Empty state */
  .empty-chat {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 12px;
    padding-top: 20vh;
  }
  .empty-avatar { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; opacity: 0.6; }
  .empty-text { font-size: 14px; color: rgba(255,255,255,0.35); margin: 0; }

  /* Messages — reduced glass, subtle backgrounds */
  .msg { display: flex; gap: 10px; }
  .msg-user { justify-content: flex-end; }
  .msg-agent { align-items: flex-start; }

  .agent-avatar {
    width: 26px; height: 26px; border-radius: 50%;
    object-fit: cover; flex-shrink: 0; margin-top: 2px;
  }

  .user-bubble {
    max-width: 70%;
    padding: 10px 16px;
    border-radius: 18px 18px 6px 18px;
    font-size: 14px; line-height: 1.55;
    color: rgba(255,255,255,0.90);
    /* Subtle bg — no liquid-glass */
    background: rgba(10,132,255,0.12);
    border: 1px solid rgba(10,132,255,0.15);
  }

  .agent-card {
    flex: 1; max-width: 100%;
    padding: 14px 18px;
    border-radius: 14px;
    font-size: 14px; line-height: 1.6;
    color: rgba(255,255,255,0.85);
    /* Subtle bg — no liquid-glass */
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
  }

  :global(.md-content .md-line) { margin: 0; }
  :global(.md-content .md-gap) { height: 8px; }
  :global(.md-content .md-numbered) { margin: 2px 0; padding-left: 8px; }
  :global(.md-content .md-bullet) { margin: 1px 0; padding-left: 24px; position: relative; }
  :global(.md-content .md-bullet::before) { content: "•"; position: absolute; left: 12px; color: rgba(255,255,255,0.50); }
  :global(.md-content strong) { font-weight: 600; color: rgba(255,255,255,0.95); }

  .typing-card {
    display: flex; align-items: center; gap: 4px;
    padding: 14px 18px; width: auto;
  }
  .typing-dot {
    display: inline-block; width: 6px; height: 6px; border-radius: 50%;
    background: rgba(255,255,255,0.40);
    animation: typing-bounce 1.2s ease-in-out infinite;
  }
  .typing-dot:nth-child(2) { animation-delay: 0.18s; }
  .typing-dot:nth-child(3) { animation-delay: 0.36s; }
  @keyframes typing-bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40% { transform: translateY(-4px); opacity: 0.85; }
  }

  /* Input footer */
  .input-footer {
    flex-shrink: 0; padding: 12px 16px 20px;
    display: flex; justify-content: center;
  }
  .input-pill {
    display: flex; align-items: center; gap: 8px;
    height: 52px; padding: 0 10px 0 8px;
    border-radius: 100px;
    width: 100%; max-width: 720px;
  }
  .input-avatar {
    width: 34px; height: 34px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.50);
    flex-shrink: 0; object-fit: cover;
  }
  .chat-input {
    flex: 1; background: none; border: none; outline: none;
    height: 100%; font-size: 14px; font-family: inherit;
    color: rgba(255,255,255,0.85); caret-color: #0A84FF;
  }
  .chat-input::placeholder { color: rgba(255,255,255,0.30); }
  .chat-input:disabled { opacity: 0.5; }

  .input-action {
    display: flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%;
    color: rgba(255,255,255,0.40); cursor: pointer;
    transition: color 0.15s, background 0.15s;
  }
  .input-action:hover { color: rgba(255,255,255,0.75); background: rgba(255,255,255,0.08); }

  .send-btn {
    width: 32px; height: 32px; border-radius: 50%; border: none;
    background: rgba(255,255,255,0.20); color: white;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; flex-shrink: 0; transition: background 0.15s, opacity 0.15s;
  }
  .send-btn:hover:not(:disabled) { background: rgba(255,255,255,0.30); }
  .send-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  /* ---- Sidebar settings footer ---- */
  .sb-settings-spacer { flex: 1; min-height: 8px; }
  .sb-settings-trigger {
    display: flex; align-items: center; gap: 7px;
    width: 100%; padding: 8px 12px; border: none; background: none;
    color: rgba(255,255,255,0.38); font-size: 12px; font-family: inherit;
    cursor: pointer; transition: background 0.12s, color 0.12s; flex-shrink: 0;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .sb-settings-trigger:hover { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.70); }
  .sb-settings-active { color: #0A84FF !important; background: rgba(10,132,255,0.08) !important; }
  .sb-settings-panel {
    display: flex; flex-direction: column; gap: 10px;
    padding: 10px 12px; flex-shrink: 0;
    border-top: 1px solid rgba(255,255,255,0.06);
    animation: sb-in 0.12s ease-out;
  }
  @keyframes sb-in {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .sb-setting-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .sb-setting-label { font-size: 11px; color: rgba(255,255,255,0.45); flex-shrink: 0; }
  .sb-chips { display: flex; gap: 3px; flex-wrap: wrap; justify-content: flex-end; }
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
