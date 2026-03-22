<!-- LogoMenu.svelte — Dropdown from the PocketPaw logo.
     Updated: 2026-03-22 — Lucide icons, darker glass bg, glass opacity slider.
-->
<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import Info from "@lucide/svelte/icons/info";
  import Heart from "@lucide/svelte/icons/heart";
  import Settings from "@lucide/svelte/icons/settings";
  import ImageIcon from "@lucide/svelte/icons/image";
  import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
  import Blend from "@lucide/svelte/icons/blend";

  let { onClose, onOpenControlCenter }: { onClose: () => void; onOpenControlCenter?: () => void } = $props();
  let menuEl: HTMLDivElement | null = null;

  // --- Glass opacity control ---
  const GLASS_KEY = "paw-os-glass-opacity";
  let glassOpacity = $state(38); // default 38%

  function loadGlass() {
    try {
      const saved = localStorage.getItem(GLASS_KEY);
      if (saved) glassOpacity = parseInt(saved, 10);
    } catch {}
  }

  function applyGlass(value: number) {
    document.documentElement.style.setProperty(
      "--glass-opacity-override",
      `${value}%`
    );
    // Update the liquid-glass CSS variable directly
    const style = document.createElement("style");
    style.id = "glass-opacity-style";
    // Remove old one
    document.getElementById("glass-opacity-style")?.remove();
    style.textContent = `.liquid-glass { background-color: color-mix(in srgb, var(--c-glass) ${value}%, transparent) !important; }`;
    document.head.appendChild(style);
  }

  function handleGlassChange(e: Event) {
    const val = parseInt((e.target as HTMLInputElement).value, 10);
    glassOpacity = val;
    applyGlass(val);
    try { localStorage.setItem(GLASS_KEY, String(val)); } catch {}
  }

  // --- Menu logic ---
  function handleGlobalClick(e: MouseEvent) {
    if (menuEl && !menuEl.contains(e.target as Node)) onClose();
  }

  onMount(() => {
    loadGlass();
    applyGlass(glassOpacity);
    setTimeout(() => { window.addEventListener("mousedown", handleGlobalClick); }, 50);
  });
  onDestroy(() => { window.removeEventListener("mousedown", handleGlobalClick); });

  function handleAction(action: string) {
    if (action === "preferences" && onOpenControlCenter) {
      onClose();
      onOpenControlCenter();
      return;
    }
    console.log("[LogoMenu] action:", action);
    onClose();
  }

  // Glass presets
  function setGlassPreset(val: number) {
    glassOpacity = val;
    applyGlass(val);
    try { localStorage.setItem(GLASS_KEY, String(val)); } catch {}
  }
</script>

<div class="logo-menu liquid-glass" bind:this={menuEl} role="menu" aria-label="PocketPaw menu">
  <div class="menu-header">
    <span class="menu-app-name">PocketPaw</span>
    <span class="menu-version">v0.4.4</span>
  </div>

  <div class="menu-divider"></div>

  <button class="menu-item" role="menuitem" onclick={() => handleAction("about")}>
    <span class="menu-icon"><Info size={15} strokeWidth={1.8} /></span>
    About PocketPaw
  </button>

  <button class="menu-item soul-item" role="menuitem" onclick={() => handleAction("soul-status")}>
    <span class="menu-icon"><Heart size={15} strokeWidth={1.8} /></span>
    Soul Status
    <span class="soul-badge">Active</span>
  </button>

  <button class="menu-item" role="menuitem" onclick={() => handleAction("preferences")}>
    <span class="menu-icon"><Settings size={15} strokeWidth={1.8} /></span>
    Preferences
  </button>

  <button class="menu-item" role="menuitem" onclick={() => handleAction("wallpaper")}>
    <span class="menu-icon"><ImageIcon size={15} strokeWidth={1.8} /></span>
    Change Wallpaper
  </button>

  <div class="menu-divider"></div>

  <!-- Glass opacity control -->
  <div class="glass-control">
    <div class="glass-label">
      <Blend size={14} strokeWidth={1.8} />
      <span>Glass</span>
      <span class="glass-value">{glassOpacity}%</span>
    </div>
    <input
      type="range"
      min="10"
      max="80"
      step="1"
      value={glassOpacity}
      oninput={handleGlassChange}
      class="glass-slider"
    />
    <div class="glass-presets">
      <button class={glassOpacity <= 20 ? "preset-btn preset-active" : "preset-btn"} onclick={() => setGlassPreset(15)}>Clear</button>
      <button class={glassOpacity > 20 && glassOpacity <= 45 ? "preset-btn preset-active" : "preset-btn"} onclick={() => setGlassPreset(38)}>Default</button>
      <button class={glassOpacity > 45 && glassOpacity <= 65 ? "preset-btn preset-active" : "preset-btn"} onclick={() => setGlassPreset(55)}>Dark</button>
      <button class={glassOpacity > 65 ? "preset-btn preset-active" : "preset-btn"} onclick={() => setGlassPreset(75)}>Solid</button>
    </div>
  </div>

  <div class="menu-divider"></div>

  <button class="menu-item menu-item-danger" role="menuitem" onclick={() => handleAction("restart")}>
    <span class="menu-icon"><RotateCcw size={15} strokeWidth={1.8} /></span>
    Restart Agent
  </button>
</div>

<style>
  .logo-menu {
    position: fixed;
    top: 36px;
    left: 12px;
    width: 240px;
    border-radius: 12px;
    box-shadow: 0 16px 56px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.4);
    padding: 6px;
    z-index: 900;
    animation: menu-appear 0.12s ease-out;
    background-color: rgba(0, 0, 0, 0.55) !important;
  }

  @keyframes menu-appear {
    from { opacity: 0; transform: translateY(-4px) scale(0.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .menu-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 12px 6px;
  }
  .menu-app-name { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.90); }
  .menu-version {
    font-size: 10px; color: rgba(255,255,255,0.40);
    background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 8px;
    font-family: "SF Mono", "JetBrains Mono", monospace;
  }
  .menu-divider { height: 1px; background: rgba(255,255,255,0.08); margin: 4px 0; }

  .menu-item {
    display: flex; align-items: center; gap: 10px;
    width: 100%; padding: 8px 12px; background: none; border: none;
    border-radius: 8px; color: rgba(255,255,255,0.75);
    font-size: 13px; font-family: inherit; text-align: left; cursor: pointer;
    transition: background 0.12s, color 0.12s;
  }
  .menu-item:hover { background: rgba(255,255,255,0.10); color: rgba(255,255,255,0.95); }

  .menu-icon { display: flex; align-items: center; color: rgba(255,255,255,0.55); flex-shrink: 0; }
  .menu-item:hover .menu-icon { color: rgba(255,255,255,0.80); }

  .soul-item { position: relative; }
  .soul-badge {
    margin-left: auto; font-size: 10px; font-weight: 500;
    color: #30D158; background: rgba(48,209,88,0.12);
    padding: 2px 7px; border-radius: 6px;
  }
  .menu-item-danger { color: rgba(255,100,90,0.80); }
  .menu-item-danger:hover { background: rgba(255,70,60,0.12); color: rgba(255,100,90,1); }
  .menu-item-danger .menu-icon { color: rgba(255,100,90,0.60); }
  .menu-item-danger:hover .menu-icon { color: rgba(255,100,90,0.90); }

  /* ---- Glass control ---- */
  .glass-control {
    padding: 8px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .glass-label {
    display: flex; align-items: center; gap: 7px;
    color: rgba(255,255,255,0.55); font-size: 12px; font-weight: 500;
  }
  .glass-value {
    margin-left: auto;
    font-size: 11px;
    font-family: "SF Mono", "JetBrains Mono", monospace;
    color: rgba(255,255,255,0.40);
  }

  .glass-slider {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 4px;
    border-radius: 2px;
    background: rgba(255,255,255,0.12);
    outline: none;
    cursor: pointer;
  }
  .glass-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: rgba(255,255,255,0.85);
    border: none;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    cursor: pointer;
    transition: transform 0.1s;
  }
  .glass-slider::-webkit-slider-thumb:hover {
    transform: scale(1.15);
  }
  .glass-slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: rgba(255,255,255,0.85);
    border: none;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    cursor: pointer;
  }

  .glass-presets {
    display: flex; gap: 4px;
  }
  .preset-btn {
    flex: 1;
    padding: 4px 0;
    border-radius: 5px;
    border: none;
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.50);
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.12s, color 0.12s;
  }
  .preset-btn:hover {
    background: rgba(255,255,255,0.12);
    color: rgba(255,255,255,0.80);
  }
  .preset-active {
    background: rgba(10,132,255,0.18);
    color: #0A84FF;
  }
  .preset-active:hover {
    background: rgba(10,132,255,0.25);
    color: #3da1ff;
  }
</style>
