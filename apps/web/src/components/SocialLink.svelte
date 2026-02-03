<script lang="ts">
  export let label: string
  export let href: string
</script>

<a
  class="flex items-center justify-between rounded-xl border border-neutral-200 bg-white px-4 py-3 text-sm font-medium text-neutral-900 transition hover:border-neutral-900"
  href={href}
  rel="noreferrer"
  target="_blank"
>
  <span>{label}</span>
  <span aria-hidden="true" class="text-neutral-400">→</span>
</a>
