<!-- TopBar.svelte — Transparent top navigation bar for the Agent OS.
     Updated: 2026-03-25 — Figma-style collaboration presence bar showing online team members.
-->
<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import Home from "@lucide/svelte/icons/home";
  import Users from "@lucide/svelte/icons/users";

  type Tab = "pockets" | "files" | "chat";

  let {
    activeTab,
    onTabChange,
    onLogoClick,
    onPlusClick,
    onAvatarClick,
    onHome,
  }: {
    activeTab: Tab | null;
    onTabChange: (tab: Tab) => void;
    onLogoClick: () => void;
    onPlusClick: () => void;
    onAvatarClick: () => void;
    onHome: () => void;
  } = $props();

  const TABS: { id: Tab; label: string }[] = [
    { id: "pockets", label: "Pockets" },
    { id: "files", label: "Files" },
    { id: "chat", label: "Chat" },
  ];

  // --- Collaboration presence (Figma-style) ---
  type Presence = {
    id: string; name: string; initials: string; color: string;
    kind: "human" | "agent"; location: string;
    cursor?: boolean;
  };

  const ONLINE_PRESENCE: Presence[] = [
    { id: "robert", name: "Robert", initials: "RK", color: "#FF6B35", kind: "human", location: "NexWrk HQ", cursor: true },
    { id: "diana", name: "Diana", initials: "DR", color: "#E040FB", kind: "human", location: "NexWrk Events" },
    { id: "cfo", name: "CFO", initials: "CF", color: "#30D158", kind: "agent", location: "Revenue analysis" },
    { id: "cmo", name: "CMO", initials: "CM", color: "#0A84FF", kind: "agent", location: "Guest reviews" },
  ];

  let showPresenceTooltip = $state<string | null>(null);
  let presenceDropdownOpen = $state(false);
</script>

<header class="topbar">
  <!-- Left: Logo -->
  <div class="topbar-left">
    <button class="logo-btn" onclick={onLogoClick} aria-label="PocketPaw menu" aria-haspopup="true">
      <img class="logo-paw" src="/paw-avatar.png" alt="" aria-hidden="true" />
      <span class="logo-text">PocketPaw</span>
    </button>
  </div>

  <!-- Center: Home + Navigation tabs -->
  <nav class="topbar-center" aria-label="Main navigation">
    <button
      class={activeTab === null ? "tab-btn tab-home tab-active liquid-glass" : "tab-btn tab-home"}
      onclick={onHome}
      aria-label="Home"
      title="Home"
    >
      <Home size={14} strokeWidth={2} />
    </button>
    {#each TABS as tab}
      <button
        class={activeTab === tab.id ? "tab-btn tab-active liquid-glass" : "tab-btn"}
        onclick={() => onTabChange(tab.id)}
        aria-current={activeTab === tab.id ? "page" : undefined}
      >
        {tab.label}
      </button>
    {/each}
  </nav>

  <!-- Right: Presence + Actions -->
  <div class="topbar-right">
    <!-- Figma-style collaboration presence -->
    <div class="relative flex items-center mr-1.5">
      <!-- Avatar row — click to open dropdown -->
      <button
        class="flex items-center cursor-pointer hover:opacity-90 transition-opacity"
        onclick={() => { presenceDropdownOpen = !presenceDropdownOpen; }}
      >
        {#each ONLINE_PRESENCE as person}
          <div class="relative" style="margin-left:-4px">
            <div
              class={`w-6 h-6 ${person.kind === 'human' ? 'rounded-full' : 'rounded-md'} flex items-center justify-center text-[8px] font-bold text-white border-[1.5px] border-black/60 relative`}
              style="background:{person.color}"
            >
              {person.initials}
            </div>
            {#if person.cursor}
              <div class="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full" style="background:{person.color}; box-shadow: 0 0 4px {person.color}80"></div>
            {/if}
          </div>
        {/each}
        <div class="w-6 h-6 rounded-full flex items-center justify-center text-[8px] font-bold text-white/40 bg-white/[0.08] border-[1.5px] border-black/60" style="margin-left:-4px">
          <Plus size={10} strokeWidth={2.5} />
        </div>
      </button>

      <!-- Dropdown panel -->
      {#if presenceDropdownOpen}
        <!-- Backdrop -->
        <div class="fixed inset-0 z-40" onclick={() => { presenceDropdownOpen = false; }}></div>

        <div class="absolute top-8 right-0 z-50 w-72 rounded-xl border border-white/10 shadow-2xl overflow-hidden" style="background:rgba(30,30,28,0.96); backdrop-filter:blur(20px)">
          <!-- Header -->
          <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-white/[0.06]">
            <span class="text-[12px] font-semibold text-white/80">Collaborators</span>
            <span class="text-[10px] text-white/30">{ONLINE_PRESENCE.length} online</span>
          </div>

          <!-- Online members -->
          <div class="py-1.5">
            {#each ONLINE_PRESENCE as person}
              <div class="flex items-center gap-2.5 px-3.5 py-2 hover:bg-white/[0.04] transition-colors cursor-default">
                <div class="relative shrink-0">
                  <div
                    class={`w-8 h-8 ${person.kind === 'human' ? 'rounded-full' : 'rounded-lg'} flex items-center justify-center text-[10px] font-bold text-white`}
                    style="background:{person.color}"
                  >
                    {person.initials}
                  </div>
                  <div class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-[1.5px] border-[#1e1e1c] bg-[#30D158]"></div>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-1.5">
                    <span class="text-[12px] font-medium text-white/85">{person.name}</span>
                    {#if person.kind === "agent"}
                      <span class="text-[8px] font-bold text-white/30 bg-white/[0.06] px-1.5 py-0.5 rounded uppercase">Agent</span>
                    {/if}
                  </div>
                  <span class="text-[10px] text-white/35">{person.location}</span>
                </div>
                {#if person.cursor}
                  <div class="w-2 h-2 rounded-full animate-pulse" style="background:{person.color}; box-shadow: 0 0 6px {person.color}60"></div>
                {/if}
              </div>
            {/each}
          </div>

          <!-- Offline section -->
          <div class="border-t border-white/[0.06] py-1.5">
            <div class="px-3.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white/20">Offline</div>
            <div class="flex items-center gap-2.5 px-3.5 py-2 cursor-default">
              <div class="w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold text-white opacity-40" style="background:#30D158">RS</div>
              <div class="flex-1 min-w-0">
                <span class="text-[12px] font-medium text-white/40">Rohit</span>
                <span class="text-[10px] text-white/20 block">Last seen 1h ago</span>
              </div>
            </div>
            <div class="flex items-center gap-2.5 px-3.5 py-2 cursor-default">
              <div class="w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold text-white opacity-40" style="background:#FEBC2E">RR</div>
              <div class="flex-1 min-w-0">
                <span class="text-[12px] font-medium text-white/40">Richie</span>
                <span class="text-[10px] text-white/20 block">Last seen 3h ago</span>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="border-t border-white/[0.06] p-2">
            <button class="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-[12px] font-medium text-[#0A84FF] hover:bg-[#0A84FF]/10 transition-colors">
              <Plus size={14} strokeWidth={2} />
              Invite to workspace
            </button>
            <button class="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-[12px] font-medium text-white/50 hover:bg-white/[0.04] transition-colors">
              <Users size={14} strokeWidth={1.8} />
              Manage team
            </button>
          </div>
        </div>
      {/if}
    </div>

    <div class="w-px h-4 bg-white/10 mx-1"></div>

    <button class="plus-btn" onclick={onPlusClick} aria-label="Open command palette" title="Command Palette (⌘K)">
      <Plus size={14} strokeWidth={2} />
    </button>
    <button class="avatar-btn" onclick={onAvatarClick} aria-label="User menu" aria-haspopup="true">
      <span class="avatar-initial">P</span>
    </button>
  </div>
</header>

<style>
  .topbar {
    position: relative;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 32px;
    padding: 0 12px;
    background: transparent;
  }

  /* ---- Logo ---- */
  .topbar-left {
    display: flex;
    align-items: center;
    flex: 1;
  }

  .logo-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: none;
    padding: 4px 6px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s ease;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
  }

  .logo-btn:hover {
    background: rgba(255, 255, 255, 0.07);
  }

  .logo-paw {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    object-fit: cover;
  }

  .logo-text {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.85);
    letter-spacing: -0.01em;
  }

  /* ---- Tabs: glass pill on active ---- */
  .topbar-center {
    display: flex;
    align-items: center;
    gap: 6px;
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }

  .tab-btn {
    background: none;
    border: none;
    padding: 4px 14px;
    border-radius: 100px;
    font-size: 13px;
    font-weight: 400;
    font-family: inherit;
    color: rgba(255, 255, 255, 0.60);
    cursor: pointer;
    transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease,
                box-shadow 0.2s ease, backdrop-filter 0.2s ease;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    position: relative;
    border: 1px solid transparent;
  }

  .tab-btn:hover {
    color: rgba(255, 255, 255, 0.85);
  }

  /* Active tab: glass pill capsule */
  .tab-active {
    color: rgba(255, 255, 255, 0.95);
    font-weight: 500;
    /* liquid-glass class handles glass effect */
  }

  /* ---- Right actions ---- */
  .topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    justify-content: flex-end;
  }

  .plus-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 50%;
    color: rgba(255, 255, 255, 0.70);
    cursor: pointer;
    transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }

  .plus-btn:hover {
    color: rgba(255, 255, 255, 0.95);
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.22);
  }

  .avatar-btn {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    background: linear-gradient(135deg, #0A84FF 0%, #5B5BD6 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
    padding: 0;
    overflow: hidden;
  }

  .avatar-btn:hover {
    transform: scale(1.08);
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.45);
  }

  .avatar-initial {
    font-size: 10px;
    font-weight: 600;
    color: white;
    text-shadow: none;
    line-height: 1;
  }
</style>
