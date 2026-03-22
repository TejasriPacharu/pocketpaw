<!-- +page.svelte — The Agent OS desktop. State hub for all OS UI interactions.
     Updated: 2026-03-22 — Pinned desktop widgets from Pockets.
     Home screen shows wallpaper + pinned widgets + expandable chat pill.
-->
<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import TopBar from "$lib/components/os/TopBar.svelte";
  import ChatPill from "$lib/components/os/ChatPill.svelte";
  import ChatPanel from "$lib/components/os/ChatPanel.svelte";
  import FilesPanel from "$lib/components/os/FilesPanel.svelte";
  import PocketsPanel from "$lib/components/os/PocketsPanel.svelte";
  import CommandPalette from "$lib/components/os/CommandPalette.svelte";
  import LogoMenu from "$lib/components/os/LogoMenu.svelte";
  import UserMenu from "$lib/components/os/UserMenu.svelte";
  import DesktopWidgets, { type PinnedWidget } from "$lib/components/os/DesktopWidgets.svelte";
  import ControlCenter from "$lib/components/os/ControlCenter.svelte";

  type Tab = "pockets" | "files" | "chat";

  // --- OS state ---
  let chatOpen = $state(false);
  let paletteOpen = $state(false);
  let logoMenuOpen = $state(false);
  let userMenuOpen = $state(false);
  let controlCenterOpen = $state(false);
  let activeTab = $state<Tab | null>(null);

  // --- Pinned desktop widgets ---
  const WIDGETS_KEY = "paw-os-pinned-widgets";

  let pinnedWidgets = $state<PinnedWidget[]>([]);

  function loadPinnedWidgets() {
    try {
      const saved = localStorage.getItem(WIDGETS_KEY);
      if (saved) pinnedWidgets = JSON.parse(saved);
    } catch {}

    // Seed with defaults if empty
    if (pinnedWidgets.length === 0) {
      pinnedWidgets = [
        { id: "dw1", name: "Agent Crew", pocketName: "Mission Control", icon: "users", color: "#30D158", x: 0, y: 0, w: 1, h: 1 },
        { id: "dw2", name: "Cost Tracker", pocketName: "Mission Control", icon: "dollar-sign", color: "#0A84FF", x: 1, y: 0, w: 1, h: 1 },
        { id: "dw3", name: "Active Tasks", pocketName: "Mission Control", icon: "list-todo", color: "#FF9F0A", x: 2, y: 0, w: 2, h: 1 },
        { id: "dw4", name: "Activity Feed", pocketName: "Mission Control", icon: "activity", color: "#5E5CE6", x: 0, y: 1, w: 3, h: 1 },
        { id: "dw5", name: "Soul State", pocketName: "Mission Control", icon: "brain", color: "#BF5AF2", x: 3, y: 0, w: 1, h: 1 },
        { id: "dw6", name: "System", pocketName: "Infrastructure", icon: "cpu", color: "#64D2FF", x: 3, y: 1, w: 1, h: 1 },
        { id: "dw7", name: "Competitors", pocketName: "Research", icon: "globe", color: "#FF453A", x: 2, y: 1, w: 2, h: 1 },
      ];
      savePinnedWidgets();
    }
  }

  function savePinnedWidgets() {
    try { localStorage.setItem(WIDGETS_KEY, JSON.stringify(pinnedWidgets)); } catch {}
  }

  function unpinWidget(id: string) {
    pinnedWidgets = pinnedWidgets.filter(w => w.id !== id);
    savePinnedWidgets();
  }

  function pinWidget(name: string, pocketName: string, icon: string, color: string) {
    // Don't duplicate
    if (pinnedWidgets.some(w => w.name === name && w.pocketName === pocketName)) return;
    pinnedWidgets = [...pinnedWidgets, {
      id: `dw${Date.now()}`, name, pocketName, icon, color,
      x: pinnedWidgets.length % 4, y: Math.floor(pinnedWidgets.length / 4),
      w: 1, h: 1,
    }];
    savePinnedWidgets();
  }

  function handleOpenPocket(pocketName: string) {
    activeTab = "pockets";
  }

  // --- Dropdown management ---
  function openLogoMenu() {
    logoMenuOpen = true;
    userMenuOpen = false;
    paletteOpen = false;
  }

  function openUserMenu() {
    userMenuOpen = true;
    logoMenuOpen = false;
    paletteOpen = false;
  }

  function togglePalette() {
    paletteOpen = !paletteOpen;
    if (paletteOpen) {
      logoMenuOpen = false;
      userMenuOpen = false;
    }
  }

  function handleTabChange(tab: Tab) {
    if (activeTab === tab) {
      activeTab = null;
      if (tab === "chat") chatOpen = false;
    } else {
      activeTab = tab;
      if (tab === "chat") chatOpen = true;
    }
  }

  function handleGlobalKeydown(e: KeyboardEvent) {
    const isMeta = e.metaKey || e.ctrlKey;
    if (isMeta && e.key === "k") {
      e.preventDefault();
      togglePalette();
    }
    if (e.key === "Escape") {
      if (controlCenterOpen) { controlCenterOpen = false; return; }
      if (paletteOpen) { paletteOpen = false; return; }
      if (logoMenuOpen) { logoMenuOpen = false; return; }
      if (userMenuOpen) { userMenuOpen = false; return; }
    }
  }

  onMount(() => {
    loadPinnedWidgets();
    window.addEventListener("keydown", handleGlobalKeydown);
  });

  onDestroy(() => {
    window.removeEventListener("keydown", handleGlobalKeydown);
  });
</script>

<!-- Top navigation bar: always visible -->
<TopBar
  {activeTab}
  onTabChange={handleTabChange}
  onLogoClick={openLogoMenu}
  onPlusClick={togglePalette}
  onAvatarClick={openUserMenu}
  onHome={() => { activeTab = null; chatOpen = false; }}
/>

<!-- Home state: pinned widgets + chat pill -->
{#if activeTab === null}
  <DesktopWidgets
    widgets={pinnedWidgets}
    onUnpin={unpinWidget}
    onOpenPocket={handleOpenPocket}
  />
  <ChatPill />
{/if}

<!-- Full-viewport tab panels -->
{#if activeTab === "pockets"}
  <PocketsPanel />
{/if}

{#if activeTab === "files"}
  <FilesPanel />
{/if}

{#if activeTab === "chat"}
  <ChatPanel onClose={() => { chatOpen = false; activeTab = null; }} />
{/if}

<!-- Command palette overlay (⌘K) -->
{#if paletteOpen}
  <CommandPalette onClose={() => { paletteOpen = false; }} />
{/if}

<!-- Logo dropdown menu -->
{#if logoMenuOpen}
  <LogoMenu
    onClose={() => { logoMenuOpen = false; }}
    onOpenControlCenter={() => { controlCenterOpen = true; }}
  />
{/if}

<!-- User dropdown menu -->
{#if userMenuOpen}
  <UserMenu onClose={() => { userMenuOpen = false; }} />
{/if}

<!-- Control Center panel -->
{#if controlCenterOpen}
  <ControlCenter onClose={() => { controlCenterOpen = false; }} />
{/if}
