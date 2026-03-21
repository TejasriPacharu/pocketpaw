<!-- WebLogin.svelte — Login form for web/browser users who access PocketPaw remotely.
     Created: 2026-03-21
     Shown when running in a browser (not Tauri) and no server-injected token is found.
     The user pastes their access token; this component validates it against the backend
     and calls onLogin(token) on success so the parent can proceed with store initialization.
-->
<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as Card from "$lib/components/ui/card";
  import { API_PREFIX } from "$lib/api/config";

  let { onLogin }: { onLogin: (token: string) => void } = $props();

  let token = $state("");
  let loading = $state(false);

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();

    const trimmed = token.trim();
    if (!trimmed) {
      toast.error("Please enter your access token.");
      return;
    }

    loading = true;
    try {
      const res = await fetch(`${API_PREFIX}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: trimmed }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message = body?.detail ?? body?.message ?? "Invalid token. Check and try again.";
        toast.error(message);
        return;
      }

      // Token is valid and session cookie is now set — hand off to parent.
      onLogin(trimmed);
    } catch {
      toast.error("Could not reach PocketPaw. Make sure the backend is running.");
    } finally {
      loading = false;
    }
  }
</script>

<div class="flex min-h-dvh items-center justify-center bg-background p-4">
  <Card.Root class="w-full max-w-sm">
    <Card.Header>
      <Card.Title>Connect to PocketPaw</Card.Title>
      <Card.Description>
        Enter your access token to open the dashboard.
      </Card.Description>
    </Card.Header>

    <form onsubmit={handleSubmit}>
      <Card.Content class="flex flex-col gap-4">
        <div class="flex flex-col gap-1.5">
          <Label for="token-input">Access token</Label>
          <Input
            id="token-input"
            type="password"
            placeholder="Paste your token here"
            bind:value={token}
            disabled={loading}
            autocomplete="current-password"
          />
          <p class="text-xs text-muted-foreground">
            Find your token at <code class="font-mono">~/.pocketpaw/access_token</code>
          </p>
        </div>
      </Card.Content>

      <Card.Footer>
        <Button type="submit" class="w-full" disabled={loading}>
          {loading ? "Connecting..." : "Connect"}
        </Button>
      </Card.Footer>
    </form>
  </Card.Root>
</div>
