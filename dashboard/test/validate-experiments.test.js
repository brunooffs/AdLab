// ─────────────────────────────────────────────────────────────────────────────
//  validate-experiments.test.js — the dashboard's experiment parameters are
//  validated before they ever become a spawn() argv (see server.js's own
//  comments on why: argv-only spawning means there's no shell-injection
//  surface regardless, but a bad value should still fail clearly rather than
//  silently doing the wrong thing). This locks in that behavior.
// ─────────────────────────────────────────────────────────────────────────────
const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

const { validateParams, buildClickstreamArgs, EXPERIMENTS } = require(path.join(__dirname, '..', 'server.js'))

const clickstreamSchema = EXPERIMENTS.find((e) => e.id === 'clickstream').params

test('validateParams: fills in defaults for omitted fields', () => {
  const out = validateParams(clickstreamSchema, {})
  assert.equal(out.events, 500)
  assert.equal(out.rate, 10)
  assert.equal(out.users, 500)
  assert.equal(out.hotAd, '')
  assert.equal(out.buckets, 1)
})

test('validateParams: accepts valid values', () => {
  const out = validateParams(clickstreamSchema, { events: 250, rate: 25, hotAd: 'ad_hot_1', buckets: 4 })
  assert.equal(out.events, 250)
  assert.equal(out.hotAd, 'ad_hot_1')
})

test('validateParams: rejects a number below its minimum', () => {
  assert.throws(() => validateParams(clickstreamSchema, { events: 0 }), /events must be >= 1/)
})

test('validateParams: rejects a number above its maximum', () => {
  assert.throws(() => validateParams(clickstreamSchema, { rate: 99999 }), /rate must be <= 1000/)
})

test('validateParams: rejects a non-numeric value for a number field', () => {
  assert.throws(() => validateParams(clickstreamSchema, { events: 'not-a-number' }))
})

test('validateParams: rejects a hotAd value that fails the pattern (shell metacharacters)', () => {
  assert.throws(() => validateParams(clickstreamSchema, { hotAd: '; rm -rf /' }), /hotAd has an invalid format/)
})

test('validateParams: accepts an empty hotAd (optional field)', () => {
  const out = validateParams(clickstreamSchema, { hotAd: '' })
  assert.equal(out.hotAd, '')
})

test('buildClickstreamArgs: builds the exact argv produce.sh expects', () => {
  const args = buildClickstreamArgs({ events: 250, rate: 25, users: 500, hotAd: 'ad_hot_1', buckets: 4 })
  assert.deepEqual(args, ['250', '25', '--users', '500', '--hot-ad', 'ad_hot_1', '--buckets', '4'])
})

test('buildClickstreamArgs: omits --hot-ad and --buckets when not set', () => {
  const args = buildClickstreamArgs({ events: 100, rate: 10, users: 500, hotAd: '', buckets: 1 })
  assert.deepEqual(args, ['100', '10', '--users', '500'])
})

test('buildClickstreamArgs: never produces a single string (argv-only, no shell surface)', () => {
  const args = buildClickstreamArgs({ events: 1, rate: 1, users: 1, hotAd: 'x', buckets: 1 })
  for (const a of args) assert.equal(typeof a, 'string')
  assert.ok(Array.isArray(args))
})

test('validateParams: a param marked float:true is NOT truncated to an integer', () => {
  // Regression test: validateParams originally Math.trunc()'d every number
  // param unconditionally, which was correct for events/rate/buckets but
  // silently rounded duplicateRate: 0.3 down to 0 — the --duplicate-rate
  // flag then never made it into the built argv at all, with no error
  // anywhere to indicate why. float:true is the fix; this guards it.
  const out = validateParams(clickstreamSchema, { duplicateRate: 0.3 })
  assert.equal(out.duplicateRate, 0.3)
})

test('validateParams: params without float:true still truncate (no regression)', () => {
  const out = validateParams(clickstreamSchema, { events: 250.9, rate: 25.4, buckets: 3.99 })
  assert.equal(out.events, 250)
  assert.equal(out.rate, 25)
  assert.equal(out.buckets, 3)
})

test('buildClickstreamArgs: includes --dedup and --duplicate-rate when set', () => {
  const args = buildClickstreamArgs({ events: 300, rate: 20, users: 500, hotAd: '', buckets: 1, dedup: true, duplicateRate: 0.25 })
  assert.deepEqual(args, ['300', '20', '--users', '500', '--dedup', '--duplicate-rate', '0.25'])
})

test('buildClickstreamArgs: omits dedup flags when dedup is false and duplicateRate is 0', () => {
  const args = buildClickstreamArgs({ events: 300, rate: 20, users: 500, hotAd: '', buckets: 1, dedup: false, duplicateRate: 0 })
  assert.deepEqual(args, ['300', '20', '--users', '500'])
})
