<script lang="ts">
  import { onMount } from 'svelte';
  import { fade, scale } from 'svelte/transition';

  export type FlashcardItem = {
    id: string;
    term: string;
    exampleDe: string;
    literalEn: string;
    meaningEn: string;
    exampleEn: string;
    memoryHint?: string | null;
    cefr?: string | null;
  };

  type Labels = {
    title: string;
    flipHint: string;
    tapHint: string;
    rateHint: string;
    knownHint: string;
    reviewHint: string;
    round: string;
    completed: string;
    completedSub: string;
    remaining: string;
    reset: string;
  };

  export let trackId: string;
  export let items: FlashcardItem[] = [];
  export let labels: Labels;

  const SWIPE_THRESHOLD = 96;
  const DRAG_DEADZONE = 8;
  const HARD_CEFR_MIN = 3; // B1+
  const HARD_ONLY_MIN_COUNT = 6;
  const storageKey = `lyrics:flashcards:v1:${trackId}`;

  let deck: FlashcardItem[] = [];
  let reviewQueue: FlashcardItem[] = [];
  let top: FlashcardItem | null = null;
  let mastered = new Set<string>();
  let isFlipped = false;
  let round = 1;
  let completed = false;

  let dragX = 0;
  let dragging = false;
  let animatingOut = false;
  let pointerId: number | null = null;
  let activePointerEl: HTMLButtonElement | null = null;
  let startX = 0;
  let movedX = 0;
  let suppressClick = false;

  const format = (template: string, vars: Record<string, string | number>): string =>
    template.replaceAll(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? `{${key}}`));

  function primaryTranslation(item: FlashcardItem): string {
    const literal = (item.literalEn || '').trim();
    const meaning = (item.meaningEn || '').trim();
    return literal || meaning;
  }

  function visibleMemoryHint(item: FlashcardItem): string | null {
    const hint = (item.memoryHint || '').trim();
    if (!hint) return null;
    // Hide subjective mnemonics; keep objective morphology/etymology style hints.
    if (/^(sounds like|think of)\b/i.test(hint)) return null;
    return hint;
  }

  function cefrScore(cefr?: string | null): number | null {
    if (!cefr) return null;
    const normalized = cefr.trim().toUpperCase();
    const map: Record<string, number> = {
      A1: 1,
      A2: 2,
      B1: 3,
      B2: 4,
      C1: 5,
      C2: 6,
    };
    return map[normalized] ?? null;
  }

  function prioritizeItems(source: FlashcardItem[]): FlashcardItem[] {
    const hard: FlashcardItem[] = [];
    const easy: FlashcardItem[] = [];
    for (const item of source) {
      const score = cefrScore(item.cefr);
      if (score === null || score >= HARD_CEFR_MIN) hard.push(item);
      else easy.push(item);
    }

    if (!hard.length) return source;
    if (hard.length >= Math.min(HARD_ONLY_MIN_COUNT, source.length)) return hard;
    return [...hard, ...easy];
  }

  function loadMastered(): Set<string> {
    if (typeof localStorage === 'undefined') return new Set();
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw) as { masteredIds?: string[] };
      if (!Array.isArray(parsed?.masteredIds)) return new Set();
      return new Set(parsed.masteredIds.filter((x) => typeof x === 'string' && x));
    } catch {
      return new Set();
    }
  }

  function saveMastered(): void {
    if (typeof localStorage === 'undefined') return;
    const payload = {
      masteredIds: Array.from(mastered),
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(storageKey, JSON.stringify(payload));
  }

  function initializeDeck(): void {
    deck = prioritizeItems(items.filter((item) => !mastered.has(item.id)));
    reviewQueue = [];
    round = 1;
    completed = deck.length === 0;
    isFlipped = false;
    dragX = 0;
    dragging = false;
    animatingOut = false;
    pointerId = null;
  }

  function removeTopCard(): FlashcardItem | null {
    if (!deck.length) return null;
    const [card] = deck;
    deck = deck.slice(1);
    return card;
  }

  function maybeAdvanceRound(): void {
    if (deck.length > 0) return;
    if (reviewQueue.length > 0) {
      deck = reviewQueue;
      reviewQueue = [];
      round += 1;
      isFlipped = false;
      dragX = 0;
      return;
    }
    completed = true;
  }

  function decide(direction: 'known' | 'review'): void {
    if (animatingOut) return;
    if (!isFlipped) return;
    const card = top;
    if (!card) return;

    animatingOut = true;
    dragX = direction === 'known' ? 220 : -220;

    setTimeout(() => {
      const removed = removeTopCard();
      if (!removed) {
        animatingOut = false;
        return;
      }

      if (direction === 'known') {
        mastered.add(removed.id);
        saveMastered();
      } else {
        reviewQueue = [...reviewQueue, removed];
      }

      isFlipped = false;
      dragX = 0;
      dragging = false;
      movedX = 0;
      suppressClick = false;
      animatingOut = false;
      maybeAdvanceRound();
    }, 180);
  }

  function onPointerDown(event: PointerEvent): void {
    if (!isFlipped || animatingOut) return;
    event.preventDefault();
    pointerId = event.pointerId;
    activePointerEl = event.currentTarget as HTMLButtonElement;
    activePointerEl?.setPointerCapture(event.pointerId);
    startX = event.clientX;
    movedX = 0;
    suppressClick = false;
    dragging = true;
  }

  function onPointerMove(event: PointerEvent): void {
    if (!dragging || pointerId !== event.pointerId) return;
    event.preventDefault();
    const delta = event.clientX - startX;
    dragX = delta;
    movedX = Math.max(movedX, Math.abs(delta));
    if (movedX >= DRAG_DEADZONE) suppressClick = true;
  }

  function onPointerUp(event: PointerEvent): void {
    if (!dragging || pointerId !== event.pointerId) return;
    event.preventDefault();
    if (activePointerEl?.hasPointerCapture(event.pointerId)) {
      activePointerEl.releasePointerCapture(event.pointerId);
    }
    activePointerEl = null;
    dragging = false;
    pointerId = null;

    if (dragX >= SWIPE_THRESHOLD) {
      decide('known');
      return;
    }
    if (dragX <= -SWIPE_THRESHOLD) {
      decide('review');
      return;
    }
    dragX = 0;
  }

  function onPointerCancel(event: PointerEvent): void {
    if (pointerId !== event.pointerId) return;
    if (activePointerEl?.hasPointerCapture(event.pointerId)) {
      activePointerEl.releasePointerCapture(event.pointerId);
    }
    activePointerEl = null;
    dragging = false;
    pointerId = null;
    dragX = 0;
    movedX = 0;
    suppressClick = false;
  }

  function toggleFlip(): void {
    if (animatingOut) return;
    isFlipped = !isFlipped;
    dragX = 0;
  }

  function handleCardClick(): void {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (dragging || animatingOut) return;
    toggleFlip();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (completed) return;
    if (
      event.key === 'ArrowRight' ||
      event.key === '4' ||
      event.code === 'Digit4' ||
      event.code === 'Numpad4'
    ) {
      if (!isFlipped) return;
      event.preventDefault();
      decide('known');
      return;
    }
    if (
      event.key === 'ArrowLeft' ||
      event.key === '2' ||
      event.code === 'Digit2' ||
      event.code === 'Numpad2'
    ) {
      if (!isFlipped) return;
      event.preventDefault();
      decide('review');
      return;
    }
    if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault();
      toggleFlip();
    }
  }

  function resetProgress(): void {
    mastered = new Set();
    saveMastered();
    initializeDeck();
  }

  // Keep this dependency explicit so Svelte updates when deck changes.
  $: top = deck.length ? deck[0] : null;
  $: rotate = Math.max(-16, Math.min(16, dragX / 14));
  $: overlayRight = Math.max(0, Math.min(1, dragX / 140));
  $: overlayLeft = Math.max(0, Math.min(1, -dragX / 140));

  onMount(() => {
    mastered = loadMastered();
    initializeDeck();
    window.addEventListener('keydown', handleKeydown);
    return () => window.removeEventListener('keydown', handleKeydown);
  });
</script>

<section
  class="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] p-6 pb-12 [overflow-anchor:none]"
>
  <div class="flex items-baseline justify-between gap-4">
    <h2 class="text-xs font-bold uppercase tracking-widest text-[var(--text-muted)]">{labels.title}</h2>
    <div class="text-xxs font-mono text-[var(--text-subtle)]">
      {format(labels.remaining, { count: deck.length + reviewQueue.length })}
    </div>
  </div>

  <div class="relative mx-auto mb-8 mt-10 h-[390px] w-full max-w-[360px] select-none sm:h-[430px]">
    {#if completed}
      <div class="absolute inset-0 flex items-center justify-center">
        <div class="w-full rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <div class="text-sm font-semibold text-emerald-900">{labels.completed}</div>
          <p class="mt-1 text-sm text-emerald-800">{labels.completedSub}</p>
          <button
            class="mt-3 text-xxs font-mono text-emerald-900 underline decoration-emerald-400 underline-offset-4"
            type="button"
            on:click={resetProgress}
          >
            {labels.reset}
          </button>
        </div>
      </div>
    {:else if top}
      {#if deck.length > 1}
        <div
          class="absolute inset-x-3 inset-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)]"
        ></div>
      {/if}
      {#if deck.length > 2}
        <div
          class="absolute inset-x-6 inset-y-6 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-3)]"
        ></div>
      {/if}
      {#key top.id}
        <button
          in:scale={{ start: 0.97, duration: 140 }}
          out:fade={{ duration: 90 }}
          class="absolute inset-0 h-full w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface)] p-5 text-left shadow-sm transition-transform duration-200 sm:p-6"
          class:cursor-grab={isFlipped}
          class:cursor-pointer={!isFlipped}
          type="button"
          on:click={handleCardClick}
          on:pointerdown={onPointerDown}
          on:pointermove={onPointerMove}
          on:pointerup={onPointerUp}
          on:pointercancel={onPointerCancel}
          style={`transform: translateX(${dragX}px) rotate(${rotate}deg); touch-action: pan-y;`}
          aria-label={labels.flipHint}
        >
          <div
            class="pointer-events-none absolute inset-0 rounded-2xl bg-emerald-200 transition-opacity duration-150"
            style={`opacity:${overlayRight};`}
          ></div>
          <div
            class="pointer-events-none absolute inset-0 rounded-2xl bg-rose-200 transition-opacity duration-150"
            style={`opacity:${overlayLeft};`}
          ></div>

          {#if isFlipped}
            <div
              class="pointer-events-none absolute inset-y-0 right-4 z-20 flex items-center text-xxs font-bold uppercase tracking-wider text-emerald-900 transition-opacity duration-150"
              style={`opacity:${overlayRight};`}
            >
              {labels.knownHint}
            </div>
            <div
              class="pointer-events-none absolute inset-y-0 left-4 z-20 flex items-center text-xxs font-bold uppercase tracking-wider text-rose-900 transition-opacity duration-150"
              style={`opacity:${overlayLeft};`}
            >
              {labels.reviewHint}
            </div>
          {/if}

          {#if !isFlipped}
            <div class="relative z-10 flex h-full flex-col">
              <div class="flex items-start justify-between gap-4">
                <div class="text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">{top.term}</div>
                {#if top.cefr}
                  <div
                    class="rounded-full border border-[var(--border-strong)] px-2 py-1 text-xxs font-mono text-[var(--text-body)]"
                  >
                    {top.cefr}
                  </div>
                {/if}
              </div>
              <p class="mt-5 text-base leading-relaxed text-[var(--text-primary)]">{top.exampleDe}</p>
              <div class="mt-auto text-xxs font-mono text-[var(--text-subtle)]">{labels.flipHint}</div>
            </div>
          {:else}
            <div class="relative z-10 flex h-full flex-col">
              <div class="flex items-start justify-between gap-4">
                <div class="text-xl font-semibold text-[var(--text-primary)] sm:text-2xl">
                  {primaryTranslation(top)}
                </div>
                {#if top.cefr}
                  <div
                    class="rounded-full border border-[var(--border-strong)] px-2 py-1 text-xxs font-mono text-[var(--text-body)]"
                  >
                    {top.cefr}
                  </div>
                {/if}
              </div>
              <p class="mt-5 text-base leading-relaxed text-[var(--text-primary)]">{top.exampleEn}</p>
              {#if visibleMemoryHint(top)}
                <div class="mt-4 space-y-1 text-sm text-[var(--text-body)]">
                  {#if visibleMemoryHint(top)}
                    <p class="text-[var(--text-subtle)]">{visibleMemoryHint(top)}</p>
                  {/if}
                </div>
              {/if}
              <div class="mt-auto text-xxs font-mono text-[var(--text-subtle)]">{labels.rateHint}</div>
            </div>
          {/if}
        </button>
      {/key}
    {/if}
  </div>

  <div class="hidden items-center justify-center gap-2 text-xxs text-[var(--text-subtle)] sm:flex">
    <kbd class="rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >←</kbd
    >
    <kbd class="rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >2</kbd
    >
    <span class="font-sans">{labels.reviewHint}</span>
    <kbd
      class="ml-2 rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >→</kbd
    >
    <kbd class="rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >4</kbd
    >
    <span class="font-sans">{labels.knownHint}</span>
    <kbd
      class="ml-2 rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >Space</kbd
    >
    <kbd class="rounded border border-[var(--border-strong)] px-1.5 py-0.5 font-mono text-[10px] leading-none"
      >Enter</kbd
    >
    <span class="font-sans">{labels.tapHint}</span>
  </div>
</section>
