<script lang="ts">
  import { onMount, onDestroy, tick as svelteTick } from 'svelte';
  import type { GraphData, GraphNode } from '../lib/graph-data';

  // ─── Props ────────────────────────────────────────────────────────────────
  interface Props {
    graphData: GraphData;
    labels?: {
      title: string;
      stats: string;
      fullscreen: string;
      exitFullscreen: string;
    };
  }
  const { graphData, labels }: Props = $props();

  const uiLabels = {
    title: labels?.title ?? 'Knowledge Graph',
    stats: labels?.stats ?? '{nodes} nodes · {links} links',
    fullscreen: labels?.fullscreen ?? 'Fullscreen',
    exitFullscreen: labels?.exitFullscreen ?? 'Exit fullscreen',
  };

  const statsLabel = uiLabels.stats
    .replace('{nodes}', String(graphData.nodes.length))
    .replace('{links}', String(graphData.links.length));

  // ─── State ────────────────────────────────────────────────────────────────
  let canvasEl: HTMLCanvasElement | undefined = $state();
  let modalCanvasEl: HTMLCanvasElement | undefined = $state();
  let wrapperEl: HTMLDivElement | undefined = $state();
  let modalWrapperEl: HTMLDivElement | undefined = $state();

  let isModalOpen = $state(false);
  let hoveredNodeId: string | null = $state(null);

  // ─── Constants ────────────────────────────────────────────────────────────
  const NODE_RADIUS: Record<string, number> = {
    hub: 14,
    project: 9,
    blog: 9,
    tag: 6,
  };

  const NODE_COLOR: Record<string, string> = {
    hub: '#10b981',
    project: '#60a5fa',
    blog: '#c084fc',
    tag: '#737373',
  };

  let labelColors: Record<string, string> = {
    hub: '#f5f5f5',
    project: '#e2e8f0',
    blog: '#f3e8ff',
    tag: '#a3a3a3',
  };

  // ─── D3 internals ─────────────────────────────────────────────────────────
  type SimNode = GraphNode & { x?: number; y?: number; vx?: number; vy?: number; fx?: number | null; fy?: number | null };
  type SimLink = { source: SimNode; target: SimNode };

  let simNodes: SimNode[] = [];
  let simLinks: SimLink[] = [];
  let simulation: any = null;
  let transform = { x: 0, y: 0, k: 1 };
  let animFrame: number | null = null;
  let ro: ResizeObserver | null = null;
  let cleanupMainInteractions: (() => void) | null = null;
  let cleanupModalInteractions: (() => void) | null = null;
  let d3: any = null;

  // ─── Helpers ──────────────────────────────────────────────────────────────
  function getRadius(type: string) { return NODE_RADIUS[type] ?? 7; }
  function getColor(type: string) { return NODE_COLOR[type] ?? '#737373'; }
  function getLabelColor(type: string) { return labelColors[type] ?? '#a3a3a3'; }
  function dpr() { return window.devicePixelRatio || 1; }

  function readCssVar(name: string, fallback: string) {
    if (typeof window === 'undefined') return fallback;
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function updateThemeColors() {
    const textHero = readCssVar('--text-hero', '#f5f5f5');
    const textHeroSubtle = readCssVar('--text-hero-subtle', '#a3a3a3');
    labelColors = {
      hub: textHero,
      project: textHero,
      blog: textHero,
      tag: textHeroSubtle,
    };
  }

  function hexToRgba(hex: string, alpha: number): string {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function resizeCanvas(canvas: HTMLCanvasElement | undefined, wrapper: HTMLDivElement | undefined) {
    if (!canvas || !wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    const ratio = dpr();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    canvas.style.width = '100%';
    canvas.style.height = '100%';
  }

  function draw() {
    const activeCanvas = isModalOpen ? modalCanvasEl : canvasEl;
    if (!activeCanvas) return;
    const ctx = activeCanvas.getContext('2d');
    if (!ctx) return;

    const ratio = dpr();
    const w = activeCanvas.width / ratio;
    const h = activeCanvas.height / ratio;

    ctx.save();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    const hoveredNode = hoveredNodeId ? simNodes.find((n) => n.id === hoveredNodeId) : null;
    const connectedNodeIds = new Set<string>();
    if (hoveredNode) {
      connectedNodeIds.add(hoveredNode.id);
      for (const link of simLinks) {
        if (link.source.id === hoveredNode.id) connectedNodeIds.add(link.target.id);
        if (link.target.id === hoveredNode.id) connectedNodeIds.add(link.source.id);
      }
    }

    // Draw links
    ctx.lineWidth = hoveredNode ? 0.7 : 0.8;
    for (const link of simLinks) {
      const s = link.source;
      const t = link.target;
      if (s.x == null || s.y == null || t.x == null || t.y == null) continue;
      const srcColor = getColor(s.type);
      const isHoveredEdge = hoveredNode ? (s.id === hoveredNode.id || t.id === hoveredNode.id) : false;
      const alpha = hoveredNode ? (isHoveredEdge ? 0.45 : 0.08) : 0.18;
      ctx.strokeStyle = hexToRgba(srcColor, alpha);
      if (isHoveredEdge) ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.stroke();
      if (isHoveredEdge) ctx.lineWidth = 0.7;
    }

    // Draw nodes + labels
    for (const node of simNodes) {
      if (node.x == null || node.y == null) continue;
      const r = getRadius(node.type);
      const color = getColor(node.type);
      const isHovered = hoveredNode ? node.id === hoveredNode.id : false;
      const isConnected = hoveredNode ? connectedNodeIds.has(node.id) : true;
      const nodeAlpha = hoveredNode ? (isConnected ? 1 : 0.35) : 1;

      if (node.type === 'hub') {
        ctx.shadowColor = color;
        ctx.shadowBlur = isHovered ? 20 : 14;
      }

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = nodeAlpha;
      ctx.fill();

      if (node.type === 'hub') {
        ctx.strokeStyle = hexToRgba(color, 0.4);
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.shadowColor = 'transparent';
      }

      const fontSize = node.type === 'hub' ? 11 : node.type === 'tag' ? 9 : 10;
      const weight = node.type === 'hub' ? '600' : '400';
      ctx.font = `${weight} ${fontSize}px "IBM Plex Sans", sans-serif`;
      ctx.fillStyle = getLabelColor(node.type);
      ctx.globalAlpha = hoveredNode ? (isConnected ? 1 : 0.3) : 1;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(node.label, node.x, node.y + r + 3);
      ctx.globalAlpha = 1;
    }

    ctx.restore();
  }

  function renderLoop() {
    draw();
    animFrame = requestAnimationFrame(renderLoop);
  }

  function tuneForViewport(wrapper: HTMLDivElement) {
    if (!simulation || !d3) return;
    const { width, height } = wrapper.getBoundingClientRect();
    const compact = Math.min(width, height) < 520;

    const linkForce = simulation.force('link');
    const chargeForce = simulation.force('charge');
    const collisionForce = simulation.force('collision');

    if (linkForce) {
      linkForce
        .distance((l: any) => {
          const s = l.source as SimNode;
          const t = l.target as SimNode;
          if (compact) {
            return (s.type === 'hub' || t.type === 'hub') ? 60 : (s.type === 'tag' || t.type === 'tag') ? 48 : 56;
          }
          return (s.type === 'hub' || t.type === 'hub') ? 74 : (s.type === 'tag' || t.type === 'tag') ? 54 : 66;
        })
        .strength(compact ? 0.62 : 0.58);
    }

    chargeForce?.strength(compact ? -185 : -155);
    collisionForce?.radius((d: any) => getRadius((d as SimNode).type) + (compact ? 13 : 11));
    simulation.force('x', d3.forceX(width / 2).strength(compact ? 0.03 : 0.02));
    simulation.force('y', d3.forceY(height / 2).strength(compact ? 0.03 : 0.02));
  }

  function settleLayout(ticks = 65, alpha = 0.55) {
    if (!simulation) return;
    simulation.stop();
    for (let i = 0; i < ticks; i += 1) simulation.tick();
    simulation.alpha(alpha).restart();
  }

  // ─── Interaction ──────────────────────────────────────────────────────────
  function getNodeAtPoint(px: number, py: number): SimNode | null {
    const sx = (px - transform.x) / transform.k;
    const sy = (py - transform.y) / transform.k;
    for (const node of simNodes) {
      if (node.x == null || node.y == null) continue;
      const r = getRadius(node.type) + 5;
      const dx = sx - node.x;
      const dy = sy - node.y;
      if (dx * dx + dy * dy <= r * r) return node;
    }
    return null;
  }

  function canvasCoords(e: MouseEvent | Touch, canvas: HTMLCanvasElement): { x: number; y: number } {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function screenToSimulationPoint(px: number, py: number) {
    return {
      x: (px - transform.x) / transform.k,
      y: (py - transform.y) / transform.k,
    };
  }

  async function initSimulation() {
    d3 = await import('d3');

    simNodes = graphData.nodes.map((n) => ({ ...n }));
    const nodeById = new Map(simNodes.map((n) => [n.id, n]));
    simLinks = graphData.links
      .map((l) => ({
        source: nodeById.get(l.source)!,
        target: nodeById.get(l.target)!,
      }))
      .filter((l) => l.source && l.target);

    simulation = d3.forceSimulation(simNodes as any)
      .force('link', d3.forceLink(simLinks).id((d: any) => d.id).distance((l: any) => {
        const s = l.source as SimNode;
        const t = l.target as SimNode;
        return (s.type === 'hub' || t.type === 'hub') ? 95 : (s.type === 'tag' || t.type === 'tag') ? 65 : 85;
      }).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('collision', d3.forceCollide().radius((d: any) => getRadius((d as SimNode).type) + 16))
      .alphaDecay(0.022);
  }

  function attachInteractions(canvas: HTMLCanvasElement) {
    if (!d3 || !simulation) return;

    let draggedNode: SimNode | null = null;
    let dragDistance = 0;

    const zoomBehavior = d3.zoom().scaleExtent([0.25, 5]).filter((event: any) => {
      if (event.type === 'mousedown') {
        const { x, y } = canvasCoords(event, canvas);
        return !getNodeAtPoint(x, y);
      }
      return !event.button;
    }).on('zoom', (event: any) => {
      transform = { x: event.transform.x, y: event.transform.y, k: event.transform.k };
    });

    d3.select(canvas).call(zoomBehavior);

    const onMouseMove = (e: MouseEvent) => {
      if (draggedNode) {
        const { x, y } = canvasCoords(e, canvas);
        const p = screenToSimulationPoint(x, y);
        draggedNode.fx = p.x;
        draggedNode.fy = p.y;
        dragDistance += Math.hypot(e.movementX ?? 0, e.movementY ?? 0);
        hoveredNodeId = draggedNode.id;
        canvas.style.cursor = 'grabbing';
        return;
      }

      const { x, y } = canvasCoords(e, canvas);
      const node = getNodeAtPoint(x, y);
      if (node) {
        hoveredNodeId = node.id;
        canvas.style.cursor = 'grab';
      } else {
        hoveredNodeId = null;
        canvas.style.cursor = 'grab';
      }
    };

    const onMouseDown = (e: MouseEvent) => {
      const { x, y } = canvasCoords(e, canvas);
      const node = getNodeAtPoint(x, y);
      if (!node) return;
      e.preventDefault();
      e.stopPropagation();
      draggedNode = node;
      dragDistance = 0;
      const p = screenToSimulationPoint(x, y);
      draggedNode.fx = p.x;
      draggedNode.fy = p.y;
      simulation.alphaTarget(0.35).restart();
      canvas.style.cursor = 'grabbing';
    };

    const onMouseUp = () => {
      if (!draggedNode) return;
      draggedNode.fx = null;
      draggedNode.fy = null;
      draggedNode = null;
      simulation.alphaTarget(0);
      canvas.style.cursor = 'grab';
    };

    const onMouseLeave = () => {
      if (!draggedNode) hoveredNodeId = null;
    };

    const onClick = (e: MouseEvent) => {
      if (dragDistance > 3) {
        dragDistance = 0;
        return;
      }
      const { x, y } = canvasCoords(e, canvas);
      const node = getNodeAtPoint(x, y);
      if (node?.href) {
        if (isModalOpen) closeModal();
        window.location.href = node.href;
      }
      dragDistance = 0;
    };

    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('mouseleave', onMouseLeave);
    canvas.addEventListener('click', onClick);

    return () => {
      d3.select(canvas).on('.zoom', null);
      canvas.removeEventListener('mousedown', onMouseDown);
      canvas.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      canvas.removeEventListener('click', onClick);
    };
  }

  async function openModal() {
    isModalOpen = true;
    hoveredNodeId = null;
    await svelteTick();
    if (modalCanvasEl && modalWrapperEl) {
      resizeCanvas(modalCanvasEl, modalWrapperEl);
      cleanupModalInteractions?.();
      cleanupModalInteractions = attachInteractions(modalCanvasEl) ?? null;
      updateCenter(modalWrapperEl);
      tuneForViewport(modalWrapperEl);
      simulation.alpha(0.3).restart();
    }
  }

  function closeModal() {
    isModalOpen = false;
    hoveredNodeId = null;
    cleanupModalInteractions?.();
    cleanupModalInteractions = null;
    svelteTick().then(() => {
      if (canvasEl && wrapperEl) {
        resizeCanvas(canvasEl, wrapperEl);
        cleanupMainInteractions?.();
        cleanupMainInteractions = attachInteractions(canvasEl) ?? null;
        updateCenter(wrapperEl);
        tuneForViewport(wrapperEl);
        simulation.alpha(0.3).restart();
      }
    });
  }

  function updateCenter(wrapper: HTMLDivElement) {
    if (!simulation || !d3) return;
    const { width, height } = wrapper.getBoundingClientRect();
    simulation.force('center', d3.forceCenter(width / 2, height / 2));
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────
  onMount(() => {
    updateThemeColors();

    const themeObserver = new MutationObserver(() => {
      updateThemeColors();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'class'],
    });

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        observer.disconnect();
        initSimulation().then(() => {
          if (canvasEl && wrapperEl) {
            resizeCanvas(canvasEl, wrapperEl);
            cleanupMainInteractions?.();
            cleanupMainInteractions = attachInteractions(canvasEl) ?? null;
            updateCenter(wrapperEl);
            tuneForViewport(wrapperEl);
            settleLayout();
            renderLoop();
          }
        });

        ro = new ResizeObserver(() => {
          if (!isModalOpen) {
            resizeCanvas(canvasEl, wrapperEl);
            if (wrapperEl) {
              updateCenter(wrapperEl);
              tuneForViewport(wrapperEl);
            }
            simulation?.alpha(0.1).restart();
          }
        });
        if (wrapperEl) ro.observe(wrapperEl);
      }
    }, { threshold: 0.1 });

    if (wrapperEl) observer.observe(wrapperEl);

    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isModalOpen) closeModal();
    };

    const handleViewportResize = () => {
      const activeCanvas = isModalOpen ? modalCanvasEl : canvasEl;
      const activeWrapper = isModalOpen ? modalWrapperEl : wrapperEl;
      if (!activeCanvas || !activeWrapper) return;
      resizeCanvas(activeCanvas, activeWrapper);
      updateCenter(activeWrapper);
      tuneForViewport(activeWrapper);
      simulation?.alpha(0.1).restart();
    };

    window.addEventListener('resize', handleViewportResize);
    window.addEventListener('keydown', handleKeydown);

    return () => {
      window.removeEventListener('resize', handleViewportResize);
      window.removeEventListener('keydown', handleKeydown);
      observer.disconnect();
      themeObserver.disconnect();
    };
  });

  onDestroy(() => {
    if (typeof window === 'undefined') return;
    if (animFrame !== null) cancelAnimationFrame(animFrame);
    simulation?.stop();
    cleanupMainInteractions?.();
    cleanupModalInteractions?.();
    ro?.disconnect();
  });

</script>

<div class="graph-wrapper">
  <div class="graph-header">
    <h3 class="graph-title">{uiLabels.title}</h3>
    <button
      class="maximize-btn"
      onclick={openModal}
      aria-label={uiLabels.fullscreen}
      title={uiLabels.fullscreen}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 3 21 3 21 9"></polyline>
        <polyline points="9 21 3 21 3 15"></polyline>
        <line x1="21" y1="3" x2="14" y2="10"></line>
        <line x1="3" y1="21" x2="10" y2="14"></line>
      </svg>
    </button>
  </div>

  <div bind:this={wrapperEl} class="graph-canvas-wrap">
    <canvas bind:this={canvasEl} class="graph-canvas"></canvas>
  </div>
</div>

{#if isModalOpen}
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={closeModal}>
    <div class="modal-content" onclick={(e) => e.stopPropagation()} bind:this={modalWrapperEl}>
      <canvas bind:this={modalCanvasEl} class="graph-canvas"></canvas>

      <div class="modal-header">
        <h3 class="modal-title">{uiLabels.title}</h3>
        <p class="modal-stats">{statsLabel}</p>
      </div>

      <button class="close-btn" onclick={closeModal} aria-label={uiLabels.exitFullscreen}>
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>

      <div class="legend modal-legend">
        <span class="legend-dot" style="background:#10b981"></span><span class="legend-label">Hub</span>
        <span class="legend-dot" style="background:#60a5fa"></span><span class="legend-label">Project</span>
        <span class="legend-dot" style="background:#c084fc"></span><span class="legend-label">Blog</span>
        <span class="legend-dot" style="background:#737373"></span><span class="legend-label">Tag</span>
      </div>
    </div>
  </div>
{/if}

<style>
  .graph-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 280px;
    background: transparent;
  }

  @media (min-width: 1024px) {
    .graph-wrapper {
      min-height: 240px;
    }
  }

  .graph-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    min-height: 3.5rem;
    padding: 1.5rem 1.5rem 0.7rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border-subtle);
    backdrop-filter: blur(4px);
  }

  .graph-title {
    margin: 0;
    font-size: 0.75rem;
    font-weight: 700;
    line-height: 1;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .graph-canvas-wrap {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .graph-canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
  }

  .graph-canvas:active {
    cursor: grabbing;
  }

  .maximize-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    opacity: 0.7;
    cursor: pointer;
    transition: opacity 0.2s, color 0.2s;
    padding: 0;
  }

  .maximize-btn:hover {
    opacity: 1;
    color: var(--text-primary);
  }

  .legend {
    position: absolute;
    bottom: 0;
    left: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    pointer-events: none;
  }

  .legend-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .legend-label {
    font-size: 9px;
    font-family: var(--font-mono);
    color: var(--text-hero-subtle);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 4px;
  }

  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(8px);
    z-index: 5000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .modal-content {
    position: relative;
    width: 100%;
    max-width: 1200px;
    height: 85vh;
    background: var(--surface-hero);
    border: 1px solid var(--border-hero);
    border-radius: 1rem;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    z-index: 5001;
  }

  @media (min-width: 640px) {
    .modal-overlay {
      padding: 2rem;
    }
  }

  .modal-header {
    position: absolute;
    top: 1.5rem;
    left: 1.5rem;
    padding: 0;
    border: none;
    background: transparent;
    backdrop-filter: none;
    pointer-events: none;
  }

  .modal-title {
    font-size: 0.75rem;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-hero-subtle);
    margin: 0;
  }

  .modal-stats {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-hero-subtle);
    margin: 0.25rem 0 0 0;
    opacity: 0.8;
  }

  .close-btn {
    position: absolute;
    top: 1.5rem;
    right: 1.5rem;
    background: transparent;
    border: 1px solid color-mix(in srgb, var(--border-hero) 65%, transparent);
    color: var(--text-hero-subtle);
    cursor: pointer;
    padding: 0.5rem;
    border-radius: 50%;
    display: flex;
    transition: background 0.2s, color 0.2s;
  }

  .close-btn:hover {
    background: color-mix(in srgb, var(--surface-hero) 88%, transparent);
    color: var(--text-hero);
  }

  .modal-legend {
    bottom: 1.5rem;
    left: 1.5rem;
  }

</style>
