import { serve } from '@hono/node-server'
import { Hono } from 'hono'

const app = new Hono()

app.get('/', (c) => {
  return c.text('Hello Hono!')
})

app.get('/health', (c) => {
  return c.json({ data: { status: 'ok' }, meta: { ts: new Date().toISOString() } })
})

app.get('/api/status', (c) => {
  return c.json({
    data: {
      api: 'ok',
      uptimeSeconds: Math.floor(process.uptime()),
      timestamp: new Date().toISOString()
    },
    meta: { source: 'placeholder' }
  })
})

app.get('/api/jobs', (c) => {
  return c.json({
    data: [],
    meta: { count: 0 }
  })
})

const port = Number(process.env.PORT ?? 3000)
serve({ fetch: app.fetch, port })

export default app
