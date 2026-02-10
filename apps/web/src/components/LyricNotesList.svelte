<script lang="ts">
  export type SavedLyricNote = {
    id: string;
    title: string;
    artist: string;
    noteUrl: string;
    albumArtUrl?: string | null;
    savedAt: string;
  };

  export type SavedLyricNotesPage = {
    items: SavedLyricNote[];
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
  };

  export let initial: SavedLyricNotesPage;

  let data: SavedLyricNotesPage = initial;
  let loading = false;
  let error: string | null = null;

  let sectionEl: HTMLElement | null = null;

  const apiOrigin = import.meta.env.PUBLIC_API_ORIGIN || '';

  function buildHref(page: number): string {
    const u = new URL(window.location.href);
    u.searchParams.set('page', String(page));
    // Ensure stable ordering for readability.
    if (u.searchParams.get('page') === '1') u.searchParams.delete('page');
    return u.pathname + (u.searchParams.toString() ? `?${u.searchParams.toString()}` : '');
  }

  async function loadPage(page: number): Promise<void> {
    if (loading) return;
    loading = true;
    error = null;
    try {
      const base = apiOrigin ? apiOrigin.replace(/\/$/, '') : '';
      const res = await fetch(`${base}/api/ytmusic/saved?page=${encodeURIComponent(String(page))}`, {
        headers: { accept: 'application/json' },
      });
      if (!res.ok) {
        error = `HTTP ${res.status}`;
        return;
      }
      const json = (await res.json()) as { data?: SavedLyricNotesPage };
      if (!json?.data) {
        error = 'Invalid response';
        return;
      }
      data = json.data;

      // Replace history entry so paging doesn't spam the back button.
      const href = buildHref(data.page);
      window.history.replaceState({}, '', href);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load';
    } finally {
      loading = false;
    }
  }
</script>

<section bind:this={sectionEl} class="rounded-xl border border-neutral-200 bg-white p-6" style="overflow-anchor: none;">
  <div class="flex items-baseline justify-between gap-6">
    <h2 class="text-xs font-bold uppercase tracking-widest text-neutral-400">All ({data.total || data.items.length})</h2>
    <div class="flex items-center gap-2 text-xxs font-mono text-neutral-500">
      <span>Page {data.page} / {Math.max(1, data.totalPages || 1)}</span>
      <span class="text-neutral-300">·</span>
      <span>{data.pageSize}/page</span>
    </div>
  </div>

  {#if error}
    <p class="mt-3 text-sm text-neutral-700">Could not load page: {error}</p>
  {:else if !data.items.length}
    <p class="mt-3 text-sm text-neutral-700">No tracks processed yet.</p>
  {:else}
    <div class="mt-4 grid gap-3">
      {#each data.items as t (t.id)}
        <a href={`/lyrics/${encodeURIComponent(t.id)}`} class="flex items-center gap-4 rounded-lg border border-neutral-200 p-3 hover:bg-neutral-50">
          <div class="w-12 h-12 rounded-lg bg-neutral-900 overflow-hidden shrink-0">
            {#if t.albumArtUrl}
              <img src={t.albumArtUrl} alt="" class="w-12 h-12 object-cover" loading="lazy" />
            {/if}
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-neutral-900 line-clamp-1">{t.title}</div>
            <div class="text-xs text-neutral-600 mt-1 line-clamp-1">{t.artist}</div>
            <div class="text-xxs font-mono text-neutral-400 mt-2">
              Saved {new Date(t.savedAt).toLocaleString('en-US')}
            </div>
          </div>
        </a>
      {/each}
    </div>
  {/if}

  <div class="mt-5 flex items-center justify-between">
    {#if data.page > 1}
      <a
        class="text-xxs font-mono rounded-full border border-neutral-200 px-3 py-1 hover:bg-neutral-50"
        href={`/lyrics?page=${encodeURIComponent(String(data.page - 1))}`}
        aria-disabled={loading}
        on:click|preventDefault={() => loadPage(data.page - 1)}
      >
        {loading ? '…' : 'PREV'}
      </a>
    {:else}
      <span />
    {/if}

    {#if data.page < data.totalPages}
      <a
        class="text-xxs font-mono rounded-full border border-neutral-200 px-3 py-1 hover:bg-neutral-50"
        href={`/lyrics?page=${encodeURIComponent(String(data.page + 1))}`}
        aria-disabled={loading}
        on:click|preventDefault={() => loadPage(data.page + 1)}
      >
        {loading ? '…' : 'NEXT'}
      </a>
    {:else}
      <span />
    {/if}
  </div>
</section>
