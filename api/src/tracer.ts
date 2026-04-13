// ─────────────────────────────────────────────────────────────────────────────
//  tracer.ts — OpenTelemetry SDK initialisation
//  Must be the FIRST import in index.ts
// ─────────────────────────────────────────────────────────────────────────────

import { NodeSDK } from '@opentelemetry/sdk-node'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node'

const TEMPO_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://tempo:4318'
const SERVICE_NAME   = process.env.OTEL_SERVICE_NAME || 'adlab-api'

const sdk = new NodeSDK({
  serviceName: SERVICE_NAME,

  traceExporter: new OTLPTraceExporter({
    url: `${TEMPO_ENDPOINT}/v1/traces`,
  }),

  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-http': {
        enabled: true,
        ignoreIncomingRequestHook: (req) => {
          const url = req.url || ''
          return url === '/health' || url === '/metrics'
        },
      },
      '@opentelemetry/instrumentation-fastify': { enabled: true },
      '@opentelemetry/instrumentation-pg':      { enabled: true },
      '@opentelemetry/instrumentation-ioredis': { enabled: true },
      '@opentelemetry/instrumentation-grpc':    { enabled: false },
      '@opentelemetry/instrumentation-fs':      { enabled: false },
    }),
  ],
})

sdk.start()
console.log(`[OTel] Tracing started → ${TEMPO_ENDPOINT} (service: ${SERVICE_NAME}) - tracer.ts:39`)

process.on('SIGTERM', () => {
  sdk.shutdown()
    .then(() => console.log('[OTel] Shut down - tracer.ts:43'))
    .catch(console.error)
})

export { sdk }
