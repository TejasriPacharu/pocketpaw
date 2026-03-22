<!-- ControlCenter.svelte — Quick-access tools & config panel for the Agent OS.
     Created: 2026-03-23 — 2-column grid of system tools with badges,
     system stats bar (CPU/RAM/Disk/Bat), and version info.
-->
<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import FolderOpen from "@lucide/svelte/icons/folder-open";
  import Camera from "@lucide/svelte/icons/camera";
  import Bell from "@lucide/svelte/icons/bell";
  import Crosshair from "@lucide/svelte/icons/crosshair";
  import Wand2 from "@lucide/svelte/icons/wand-2";
  import Fingerprint from "@lucide/svelte/icons/fingerprint";
  import Brain from "@lucide/svelte/icons/brain";
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import HeartPulse from "@lucide/svelte/icons/heart-pulse";
  import Radio from "@lucide/svelte/icons/radio";
  import Plug from "@lucide/svelte/icons/plug";
  import Settings from "@lucide/svelte/icons/settings";
  import OctagonX from "@lucide/svelte/icons/octagon-x";
  import Cpu from "@lucide/svelte/icons/cpu";

  let { onClose }: { onClose: () => void } = $props();
  let panelEl: HTMLDivElement | null = null;

  function handleGlobalClick(e: MouseEvent) {
    if (panelEl && !panelEl.contains(e.target as Node)) onClose();
  }

  onMount(() => { setTimeout(() => { window.addEventListener("mousedown", handleGlobalClick); }, 50); });
  onDestroy(() => { window.removeEventListener("mousedown", handleGlobalClick); });

  function handleAction(action: string) {
    console.log("[ControlCenter]", action);
    onClose();
  }

  type ToolItem = {
    id: string;
    label: string;
    icon: any;
    badge?: string;
    badgeColor?: string;
    danger?: boolean;
  };

  const TOOLS: ToolItem[] = [
    { id: "files", label: "Files", icon: FolderOpen },
    { id: "screenshot", label: "Screenshot", icon: Camera },
    { id: "reminders", label: "Reminders", icon: Bell },
    { id: "intentions", label: "Intentions", icon: Crosshair },
    { id: "skills", label: "Skills", icon: Wand2, badge: "8", badgeColor: "#C4813D" },
    { id: "identity", label: "Identity", icon: Fingerprint },
    { id: "memory", label: "Memory", icon: Brain },
    { id: "audit", label: "Audit", icon: ShieldCheck },
    { id: "health", label: "Health", icon: HeartPulse, badge: "●", badgeColor: "#30D158" },
    { id: "channels", label: "Channels", icon: Radio, badge: "1", badgeColor: "#0A84FF" },
    { id: "mcp", label: "MCP", icon: Plug, badge: "BETA", badgeColor: "#30D158" },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  // Mock system stats
  const stats = [
    { label: "CPU", value: "3%", color: "#30D158" },
    { label: "RAM", value: "82%", color: "#FF9F0A" },
    { label: "Disk", value: "13%", color: "#30D158" },
    { label: "Bat", value: "87%", color: "#30D158" },
  ];
</script>

<div class="cc-panel liquid-glass" bind:this={panelEl} role="dialog" aria-label="Control Center">
  <!-- Section header -->
  <div class="cc-header">
    <span class="cc-title">Tools & Config</span>
  </div>

  <!-- 2-column tool grid -->
  <div class="cc-grid">
    {#each TOOLS as tool}
      {@const Icon = tool.icon}
      <button class="cc-item" onclick={() => handleAction(tool.id)}>
        <span class="cc-icon"><Icon size={18} strokeWidth={1.6} /></span>
        <span class="cc-label">{tool.label}</span>
        {#if tool.badge}
          <span class="cc-badge" style="background:{tool.badgeColor}20;color:{tool.badgeColor}">
            {tool.badge}
          </span>
        {/if}
      </button>
    {/each}
  </div>

  <!-- Panic button -->
  <button class="cc-panic" onclick={() => handleAction("panic")}>
    <OctagonX size={16} strokeWidth={1.8} />
    <span>Panic</span>
  </button>

  <div class="cc-divider"></div>

  <!-- System stats bar -->
  <div class="cc-stats">
    {#each stats as stat}
      <div class="cc-stat">
        <span class="cc-stat-label">{stat.label}</span>
        <span class="cc-stat-value" style="color:{stat.color}">{stat.value}</span>
      </div>
    {/each}
  </div>

  <div class="cc-divider"></div>

  <!-- Version info -->
  <div class="cc-footer">
    <span class="cc-version">v0.4.9</span>
    <button class="cc-link" onclick={() => handleAction("release-notes")}>Release notes</button>
  </div>
</div>

<style>
  .cc-panel {
    position: fixed;
    top: 36px;
    left: 12px;
    width: 300px;
    border-radius: 14px;
    padding: 12px;
    z-index: 900;
    animation: cc-in 0.14s ease-out;
    background-color: rgba(0, 0, 0, 0.60) !important;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.4);
  }

  @keyframes cc-in {
    from { opacity: 0; transform: translateY(-6px) scale(0.97); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .cc-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 2px 6px 10px;
  }
  .cc-title {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; color: rgba(255,255,255,0.40);
  }

  /* 2-column grid */
  .cc-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px;
  }

  .cc-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 10px;
    border-radius: 8px; border: none; background: none;
    color: rgba(255,255,255,0.75);
    font-size: 13px; font-family: inherit;
    text-align: left; cursor: pointer;
    transition: background 0.12s, color 0.12s;
    position: relative;
  }
  .cc-item:hover {
    background: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.95);
  }

  .cc-icon {
    display: flex; align-items: center;
    color: rgba(255,255,255,0.50);
    flex-shrink: 0;
  }
  .cc-item:hover .cc-icon { color: rgba(255,255,255,0.80); }

  .cc-label { flex: 1; }

  .cc-badge {
    font-size: 10px; font-weight: 600;
    padding: 1px 6px; border-radius: 10px;
    flex-shrink: 0;
  }

  /* Panic */
  .cc-panic {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 10px; margin-top: 2px;
    border-radius: 8px; border: none; background: none;
    color: rgba(255,100,90,0.80);
    font-size: 13px; font-family: inherit;
    text-align: left; cursor: pointer;
    transition: background 0.12s, color 0.12s;
    width: 100%;
  }
  .cc-panic:hover {
    background: rgba(255,70,60,0.12);
    color: rgba(255,100,90,1);
  }

  .cc-divider {
    height: 1px; background: rgba(255,255,255,0.08);
    margin: 8px 0;
  }

  /* System stats */
  .cc-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
    padding: 4px 0;
  }
  .cc-stat {
    display: flex; flex-direction: column;
    align-items: center; gap: 2px;
    padding: 6px 0;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
  }
  .cc-stat-label {
    font-size: 11px; color: rgba(255,255,255,0.40);
  }
  .cc-stat-value {
    font-size: 14px; font-weight: 600;
    font-family: "SF Mono", "JetBrains Mono", monospace;
  }

  /* Footer */
  .cc-footer {
    display: flex; flex-direction: column;
    align-items: center; gap: 2px;
    padding: 6px 0 2px;
  }
  .cc-version {
    font-size: 12px; color: rgba(255,255,255,0.30);
    font-family: "SF Mono", "JetBrains Mono", monospace;
  }
  .cc-link {
    font-size: 11px; color: rgba(255,255,255,0.25);
    background: none; border: none; cursor: pointer;
    font-family: inherit;
    transition: color 0.12s;
    text-decoration: underline;
    text-decoration-color: rgba(255,255,255,0.12);
  }
  .cc-link:hover { color: rgba(255,255,255,0.60); }
</style>
