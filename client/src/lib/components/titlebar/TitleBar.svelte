<!--
  TitleBar.svelte — Custom window chrome for the PocketPaw desktop app
  Modified: 2026-03-21 — Removed top-level Tauri import (crashes in web mode);
    window controls and drag region are hidden in web mode via platformStore.isWeb
-->
<script lang="ts">
  import { platformStore } from "$lib/stores";
  import { PanelLeft } from "@lucide/svelte";
  import WindowControls from "./WindowControls.svelte";
  import SessionTitle from "./SessionTitle.svelte";
  import ModelBadge from "./ModelBadge.svelte";
  import QuickActions from "./QuickActions.svelte";
  import ConnectionBadge from "./ConnectionBadge.svelte";
  import AgentProgressBar from "./AgentProgressBar.svelte";
  import WorkspaceTabs from "./WorkspaceTabs.svelte";

  let { onToggleSidebar, showTabs = true }: { onToggleSidebar?: () => void; showTabs?: boolean } = $props();

  const isMac = $derived(platformStore.desktopOS === "macos");

  const headerClass = $derived(
    isMac
      ? "relative flex w-full shrink-0 items-center h-[38px] border-b border-border bg-background/80"
      : platformStore.desktopOS === "windows"
        ? "relative flex w-full shrink-0 items-center h-[32px] border-b border-border bg-background/80"
        : "relative flex w-full shrink-0 items-center h-[34px] border-b border-border bg-background/80",
  );

  const leftZoneClass = $derived(
    isMac && !platformStore.isWeb ? "flex items-center pl-[76px]" : "flex items-center pl-2",
  );

  async function startDrag(e: MouseEvent) {
    // Drag region is only meaningful in Tauri; browsers manage their own window
    if (platformStore.isWeb) return;
    const target = e.target as HTMLElement;
    if (target.closest("button") || target.closest("input") || target.closest("a")) return;
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().startDragging();
    } catch {
      // not in Tauri context
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<header
  class={headerClass}
  onmousedown={startDrag}
  data-tauri-drag-region={!platformStore.isWeb || undefined}
>
  <!-- Left zone: sidebar toggle (+ macOS traffic light inset) -->

  <!-- Center zone: workspace tabs + session title + model badge -->
  <div class="flex w-full justify-between">
    <div class={leftZoneClass}>
      {#if onToggleSidebar}
        <button
          onclick={onToggleSidebar}
          class="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors duration-100 hover:bg-foreground/10 hover:text-foreground @[pointer:coarse]:h-9 @[pointer:coarse]:w-9"
        >
          <PanelLeft class="h-4 w-4" strokeWidth={1.75} />
        </button>
      {/if}
    </div>
    <WorkspaceTabs visible={showTabs} />

    <!-- Right zone: window controls (desktop only — browser provides its own chrome) -->
    <div class="flex items-center gap-0.5 pr-0.5">
      {#if !platformStore.isWeb && !isMac}
        <WindowControls platform={platformStore.desktopOS} />
      {/if}
    </div>
  </div>
</header>
