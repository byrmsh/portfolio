<script lang="ts">
  export let title: string
  export let value: string
  export let meta: string
  export let accent: boolean = false
</script>

<div class={`rounded-xl border p-4 ${accent ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-neutral-200 bg-white text-neutral-900'}`}>
  <div class="text-xs font-semibold uppercase tracking-widest text-neutral-500">
    {title}
  </div>
  <div class="mt-2 text-2xl font-semibold">
    {value}
  </div>
  <div class="mt-1 text-xs text-neutral-500">
    {meta}
  </div>
</div>
