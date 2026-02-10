<script lang="ts">
  import { onMount } from 'svelte';

  export let id: string | undefined;

  type YtMusicAnalysis = {
    id: string;
    source: 'ytmusic';
    title: string;
    artist: string;
    album?: string | null;
    albumArtUrl?: string | null;
    trackUrl?: string | null;
    lyricsUrl?: string | null;
    background: { tldr: string; notes: { title: string; body: string }[] };
    vocabulary: { term: string; literal: string; meaning: string; cefr?: string | null; usage?: string[] | null }[];
    updatedAt: string;
  };

  let loading = true;
  let error: string | null = null;
  let analysis: YtMusicAnalysis | null = null;

  const apiOrigin = import.meta.env.PUBLIC_API_ORIGIN || '';

  function getIdFallback(): string | null {
    try {
      const u = new URL(window.location.href);
      return u.searchParams.get('id');
    } catch {
      return null;
    }
  }

  async function load(): Promise<void> {
    const resolvedId = id ?? getIdFallback();
    if (!resolvedId) {
      error = 'Missing id';
      loading = false;
      return;
    }

    try {
      const base = apiOrigin ? apiOrigin.replace(/\/$/, '') : '';
      const res = await fetch(`${base}/api/ytmusic/${encodeURIComponent(resolvedId)}/analysis`, {
        headers: { accept: 'application/json' },
      });
      if (!res.ok) {
        error = res.status === 404 ? 'Not found' : `HTTP ${res.status}`;
        loading = false;
        return;
      }
      const json = (await res.json()) as { data?: YtMusicAnalysis };
      if (!json?.data?.id) {
        error = 'Invalid response';
        loading = false;
        return;
      }
      analysis = json.data;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void load();
  });
</script>

{#if loading}
  <section class="rounded-xl border border-neutral-200 bg-white p-6">
    <h2 class="text-sm font-semibold text-neutral-900">Loading…</h2>
    <p class="mt-2 text-sm text-neutral-700">Fetching analysis from the API.</p>
  </section>
{:else if error}
  <section class="rounded-xl border border-neutral-200 bg-white p-6">
    <h2 class="text-sm font-semibold text-neutral-900">Could not load note</h2>
    <p class="mt-2 text-sm text-neutral-700">{error}</p>
  </section>
{:else if analysis}
  <header class="flex items-start gap-5">
    <div class="w-20 h-20 rounded-xl bg-neutral-900 shrink-0 overflow-hidden">
      {#if analysis.albumArtUrl}
        <img src={analysis.albumArtUrl} alt="" class="w-20 h-20 object-cover" loading="lazy" />
      {/if}
    </div>
    <div class="min-w-0">
      <div class="text-xs font-bold uppercase tracking-widest text-neutral-400">Lyric Note</div>
      <h1 class="mt-2 text-2xl font-semibold text-neutral-900">{analysis.title}</h1>
      <div class="mt-1 text-sm text-neutral-600">{analysis.artist}</div>
      <div class="mt-3 flex flex-wrap gap-2">
        {#if analysis.trackUrl}
          <a
            class="text-xxs font-mono rounded-full border border-neutral-200 px-3 py-1 hover:bg-neutral-50"
            href={analysis.trackUrl}
          >
            OPEN TRACK
          </a>
        {/if}
        {#if analysis.lyricsUrl}
          <a
            class="text-xxs font-mono rounded-full border border-neutral-200 px-3 py-1 hover:bg-neutral-50"
            href={analysis.lyricsUrl}
          >
            READ LYRICS
          </a>
        {/if}
      </div>
      <div class="mt-2 text-xxs font-mono text-neutral-400">
        Updated {new Date(analysis.updatedAt).toLocaleString('en-US')}
      </div>
    </div>
  </header>

  <section class="rounded-xl border border-neutral-200 bg-white p-6">
    <h2 class="text-xs font-bold uppercase tracking-widest text-neutral-400">Background</h2>
    <p class="mt-3 text-sm text-neutral-800 leading-relaxed">{analysis.background.tldr}</p>

    {#if analysis.background.notes?.length}
      <div class="mt-5 grid gap-4">
        {#each analysis.background.notes as n (n.title)}
          <div class="rounded-lg border border-neutral-200 p-4">
            <div class="text-sm font-semibold text-neutral-900">{n.title}</div>
            <p class="mt-2 text-sm text-neutral-700 leading-relaxed">{n.body}</p>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  {#if analysis.vocabulary?.length}
    <section class="rounded-xl border border-neutral-200 bg-white p-6">
      <h2 class="text-xs font-bold uppercase tracking-widest text-neutral-400">Vocabulary</h2>
      <div class="mt-4 grid gap-3">
        {#each analysis.vocabulary as v (v.term)}
          <div class="rounded-lg border border-neutral-200 p-4">
            <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <div class="text-sm font-semibold text-neutral-900">{v.term}</div>
              {#if v.cefr}
                <div class="text-xxs font-mono text-neutral-500">{v.cefr}</div>
              {/if}
            </div>
            <div class="mt-2 text-sm text-neutral-800">
              <span class="text-neutral-500">Literal:</span> {v.literal}
            </div>
            <div class="mt-1 text-sm text-neutral-800">
              <span class="text-neutral-500">Meaning:</span> {v.meaning}
            </div>
            {#if v.usage?.length}
              <ul class="mt-2 list-disc pl-5 text-sm text-neutral-700">
                {#each v.usage as u (u)}
                  <li>{u}</li>
                {/each}
              </ul>
            {/if}
          </div>
        {/each}
      </div>
    </section>
  {/if}
{/if}
