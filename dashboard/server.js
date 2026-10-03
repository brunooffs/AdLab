#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
//  dashboard/server.js — local control panel for AdLab. Zero dependencies:
//  only Node's built-in http/net/child_process/fs modules.
//
//  Usage:  node dashboard/server.js          (binds 127.0.0.1:4400)
//          PORT=4401 node dashboard/server.js
//
//  It starts/stops/resets the stack by calling the SAME scripts you'd run by
//  hand (./start.sh, ./stop.sh, ./reset.sh) — it has no logic of its own for
//  bringing services up or down, so it can never drift from them.
//
//  Security (this binds a port that can run `docker compose ... down -v`,
//  so it is deliberately conservative):
//    - Binds 127.0.0.1 only — never reachable from the network.
//    - State-changing requests (POST /api/action) are rejected unless the
//      Host header matches this server AND, when an Origin header is present,
//      it also matches. This stops a malicious page open in another tab from
//      driving the dashboard via a cross-origin fetch() (the browser sends
//      Origin on cross-origin requests; a page can't fake same-origin).
//    - The action payload is never a shell string. `profiles` is validated,
//      one item at a time, against the fixed PROFILES list below (kept in
//      sync with start.sh's own VALID list) before it is placed in an argv
//      array passed to spawn() with no shell involved — there is no string
//      concatenation an attacker could inject into.
//    - `reset` additionally requires {"confirm":"RESET"} in the JSON body,
//      on top of --yes already being passed to reset.sh.
//    - Only one action runs at a time; a second request gets 409.
// ─────────────────────────────────────────────────────────────────────────────
'use strict';

const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = Number(process.env.PORT || 4400);
const HOST = '127.0.0.1';
const REPO_ROOT = path.resolve(__dirname, '..');
const HTML_PATH = path.join(__dirname, 'dashboard.html');

// Kept in sync BY HAND with the `VALID` list in start.sh. If you add a profile
// there, add it here too — the dashboard has no way to discover it automatically
// because it never parses docker-compose.yml (that would be another thing that
// could drift; a hardcoded, reviewed list is the safer trade-off here).
const PROFILES = ['gateway', 'streaming', 'analytics', 'observability', 'extras'];

// ── Spark control (independent of the single-run lock below) ───────────────
// Spark is architecturally different from every other action here: start.sh,
// produce.sh etc. are bounded and finish; the streaming job is meant to keep
// running indefinitely. Gating it behind the same `current` lock that every
// other action shares would mean starting Spark permanently blocks running
// the Clickstream experiment for as long as Spark stays up — exactly the
// opposite of what's wanted. So Spark gets its own independent tracking
// lane (`sparkRun`, mirroring `current`'s shape) and its own status source
// of truth: polling the Spark Master's own REST API, not just "is the
// container running" (a running container says nothing about whether the
// streaming job was ever submitted — this was the actual confusion that
// prompted building this).
const SPARK_MASTER_UI = 'http://localhost:8081';

// `/json/` is the Spark Standalone Master's own status endpoint — confirmed
// directly against a real running cluster (not assumed). An earlier version
// of this function used `/api/v1/applications`, the Spark *History Server*'s
// REST path — a component this project never deploys — which 404s as HTML,
// not JSON. That version was only ever tested against a mock server that
// encoded the same wrong assumption, so the "test" never actually caught it;
// real evidence from a live cluster is what caught it.
async function sparkAppStatus() {
  try {
    const res = await fetch(`${SPARK_MASTER_UI}/json/`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return { reachable: false, running: false };
    const data = await res.json();
    const running = (data.activeapps || []).find((a) => a.state === 'RUNNING');
    if (running) {
      return { reachable: true, running: true, appId: running.id, name: running.name, startTime: running.submitdate };
    }
    return { reachable: true, running: false };
  } catch {
    return { reachable: false, running: false };
  }
}

// Matches the Spark Master UI's own "(kill)" link exactly: a plain HTML
// <form method="POST" action="app/kill/"> with id/terminate as hidden
// fields — form-urlencoded BODY data, not a query string. The previous
// version sent them as a query string on the POST, which was never actually
// confirmed against the real form markup, only assumed.
async function sparkAppKill(appId) {
  try {
    const body = new URLSearchParams({ id: appId, terminate: 'true' });
    const res = await fetch(`${SPARK_MASTER_UI}/app/kill/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      signal: AbortSignal.timeout(5000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ── ArgoCD status (read-only) ───────────────────────────────────────────────
// K8s/ArgoCD is optional and external to this repo's own automation — most
// clones of this project will never have kubectl or a cluster at all, and
// that has to render as a calm "not configured", not an error. Status only,
// deliberately: a sync/rollback button would be a real action needing the
// same confirmation rigor as Spark's Start/Stop, and that's a separate,
// later addition, not bundled in here.
//
// Every kubectl call gets an explicit timeout — confirmed directly (see the
// commit introducing this) that spawn()'s own `timeout` option genuinely
// kills a hung process rather than trusting it always returns, the same
// class of bug just found and fixed in the agent's Gemini calls.
const KUBECTL_TIMEOUT_MS = 5000;

function runKubectl(args) {
  return new Promise((resolve) => {
    let out = '';
    let err = '';
    let settled = false;
    const settle = (result) => { if (!settled) { settled = true; resolve(result); } };
    let child;
    try {
      child = spawn('kubectl', args, { timeout: KUBECTL_TIMEOUT_MS });
    } catch (e) {
      return settle({ ok: false, error: e.message });
    }

    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', (e) => {
      settle({ ok: false, error: e.code === 'ENOENT' ? 'kubectl not found on PATH' : e.message });
    });
    child.on('close', (code, signal) => {
      if (signal === 'SIGTERM' || signal === 'SIGKILL') return settle({ ok: false, error: 'kubectl timed out' });
      if (code !== 0) return settle({ ok: false, error: (err.trim() || `kubectl exited ${code}`).slice(0, 200) });
      settle({ ok: true, out });
    });

    // The hard guarantee: this resolves the caller's request no later than
    // the deadline, full stop — independent of whether the child (or any
    // grandchild it may have spawned, e.g. an exec-based credential plugin)
    // actually finishes exiting. Confirmed directly that relying on the
    // close event alone isn't safe: a process whose stdout/stderr stay held
    // open by an orphaned grandchild never fires 'close' at all, no matter
    // how hard the direct child is killed. Best-effort cleanup still happens
    // in the background; the dashboard just never waits on it.
    setTimeout(() => {
      try { child.kill('SIGKILL'); } catch { /* already gone */ }
      settle({ ok: false, error: 'kubectl timed out' });
    }, KUBECTL_TIMEOUT_MS + 500);
  });
}

async function argocdStatus() {
  const ctxResult = await runKubectl(['config', 'current-context']);
  if (!ctxResult.ok) {
    return { available: false, reason: ctxResult.error };
  }
  const context = ctxResult.out.trim();

  const appResult = await runKubectl(['get', 'application', 'adlab', '-n', 'argocd', '-o', 'json']);
  if (!appResult.ok) {
    // kubectl itself works (we have a context) but the Application isn't
    // there — a real, common state (no cluster up, or ArgoCD never
    // installed on whatever context is current), not a crash.
    return { available: true, context, appFound: false, reason: appResult.error };
  }

  let app;
  try {
    app = JSON.parse(appResult.out);
  } catch {
    return { available: true, context, appFound: false, reason: 'could not parse kubectl output' };
  }

  return {
    available: true,
    context,
    appFound: true,
    sync: app.status?.sync?.status || 'Unknown',
    health: app.status?.health?.status || 'Unknown',
    revision: app.status?.sync?.revision ? app.status.sync.revision.slice(0, 7) : null,
  };
}

let sparkRun = null; // { id, buffer:[], subscribers:Set, done:null|{code} } — independent of `current`

function startSparkRun() {
  const id = String(Date.now());
  const run = { id, buffer: [], subscribers: new Set(), done: null };
  sparkRun = run;
  const child = spawn('./spark.sh', [], { cwd: REPO_ROOT, env: process.env });
  const push = (chunk) => {
    const text = chunk.toString();
    run.buffer.push(text);
    if (run.buffer.length > 4000) run.buffer.shift();
    for (const res of run.subscribers) writeSSE(res, 'line', text);
  };
  child.stdout.on('data', push);
  child.stderr.on('data', push);
  child.on('close', (code) => {
    run.done = { code };
    for (const res of run.subscribers) { writeSSE(res, 'done', { code }); res.end(); }
    run.subscribers.clear();
  });
  child.on('error', (e) => {
    run.done = { code: -1 };
    const msg = `\n[dashboard] failed to start: ${e.message}\n`;
    run.buffer.push(msg);
    for (const res of run.subscribers) { writeSSE(res, 'line', msg); writeSSE(res, 'done', { code: -1 }); res.end(); }
    run.subscribers.clear();
  });
  return run;
}

// ── Experiments registry ────────────────────────────────────────────────────
// Data-driven on purpose: the front end fetches this and builds the form from
// it, so adding a new experiment means appending one object here — no route
// or HTML changes needed. Each experiment maps to one script under the repo
// root; params are validated (type, range, pattern) before ever reaching
// spawn(), which is called with an argv array (never a shell string), so
// there is no injection surface regardless.
const EXPERIMENTS = [
  {
    id: 'clickstream',
    label: 'Clickstream producer',
    description: 'Generates ad click events into the "clickstream" Kafka topic via producer.py.',
    requiresProfiles: ['streaming'],
    cmd: './produce.sh',
    params: [
      { name: 'events', label: 'Events', type: 'number', default: 500, min: 1, max: 100000 },
      { name: 'rate', label: 'Rate (events/s)', type: 'number', default: 10, min: 1, max: 1000 },
      { name: 'users', label: 'Simulated users', type: 'number', default: 500, min: 1, max: 50000 },
      { name: 'hotAd', label: 'Hot ad id (optional)', type: 'text', default: '', pattern: '^[A-Za-z0-9_-]{0,64}$' },
      { name: 'buckets', label: 'Hot-ad salt buckets', type: 'number', default: 1, min: 1, max: 32 },
      { name: 'dedup', label: 'Redis dedup (drop repeats seen within 5 min)', type: 'boolean', default: false },
      { name: 'duplicateRate', label: 'Deliberate duplicate rate (0-1, demonstrates dedup)', type: 'number', float: true, default: 0, min: 0, max: 1, step: 0.05 },
    ],
  },
  {
    id: 'agent',
    label: 'Campaign analyst (AI agent)',
    description: 'Read-only agent: asks Gemini your question, which calls AdLab\'s own metrics/advertiser endpoints as tools and answers from the real data. Nothing it does can write or change anything.',
    requiresProfiles: [],
    cmd: './run_agent.sh',
    params: [
      { name: 'question', label: 'Question', type: 'text', default: "What's trending right now, and is there anything interesting about it?", pattern: '^.{1,500}$' },
    ],
  },
];

// Turns validated params into the argv for produce.sh: EVENTS RATE [flags...]
// (produce.sh itself forwards trailing flags straight to producer.py).
function buildClickstreamArgs(p) {
  const args = [String(p.events), String(p.rate), '--users', String(p.users)];
  if (p.hotAd) args.push('--hot-ad', p.hotAd);
  if (p.buckets > 1) args.push('--buckets', String(p.buckets));
  if (p.dedup) args.push('--dedup');
  if (p.duplicateRate > 0) args.push('--duplicate-rate', String(p.duplicateRate));
  return args;
}
function buildAgentArgs(p) {
  return [p.question];
}
const EXPERIMENT_BUILDERS = { clickstream: buildClickstreamArgs, agent: buildAgentArgs };

// ── Tutorials registry ──────────────────────────────────────────────────────
// Same data-driven shape as EXPERIMENTS: one entry per chapter, so adding a
// chapter later is "add a .md file, add one line here" — no route changes.
// `available: false` chapters render as a locked placeholder instead of 404ing;
// use that for chapters blocked on other work (see the .md files' own notes).
const TUTORIALS = [
  { id: '00', title: 'Setup and mental model', file: '00-setup-and-mental-model.md', available: true },
  { id: '01', title: 'Containers and Compose as a mini-datacenter', file: '01-containers-and-compose.md', available: true },
  { id: '02', title: 'PostgreSQL and Prisma: the system of record', file: '02-postgres-and-prisma.md', available: true },
  { id: '03', title: 'Redis: caching and its failure modes', file: '03-redis.md', available: true },
  { id: '04', title: 'Kafka: topics, partitions, consumer groups', file: '04-kafka.md', available: true },
  { id: '05', title: 'Spark Structured Streaming: watermarks', file: '05-spark-watermarks.md', available: true },
  { id: '06', title: 'Elasticsearch and Kibana: indexing and search', file: '06-elasticsearch-kibana.md', available: true },
  { id: '07', title: 'CQRS: commands, events, projections', file: '07-cqrs.md', available: true },
  { id: '08', title: 'Kong: the gateway', file: '08-kong.md', available: true },
  { id: '09', title: 'Observability: metrics, traces, dashboards', file: '09-observability.md', available: true },
  { id: '10', title: 'Kubernetes and Kustomize', file: '10-kubernetes.md', available: true },
  { id: '11', title: 'GitOps with ArgoCD', file: '11-gitops-argocd.md', available: true },
  { id: '12', title: 'CI/CD with GitHub Actions', file: '12-cicd.md', available: true },
  { id: '13', title: 'Capstone: debug a broken system', file: '13-capstone.md', available: false },
];
const TUTORIAL_DIR = path.join(REPO_ROOT, 'tutorial', 'chapters');

// Validates `input` against `schema`, one field at a time. Throws with a
// message naming the offending field — never trusts the caller's shape.
function validateParams(schema, input) {
  const out = {};
  for (const p of schema) {
    let v = input == null ? undefined : input[p.name];
    if (v === undefined || v === null || v === '') v = p.default;
    if (p.type === 'number') {
      v = Number(v);
      if (!Number.isFinite(v)) throw new Error(`${p.name} must be a number`);
      if (p.min !== undefined && v < p.min) throw new Error(`${p.name} must be >= ${p.min}`);
      if (p.max !== undefined && v > p.max) throw new Error(`${p.name} must be <= ${p.max}`);
      v = p.float ? v : Math.trunc(v);  // integer by default; set float:true for genuine fractional params
    } else if (p.type === 'text') {
      v = String(v);
      if (p.pattern && !new RegExp(p.pattern).test(v)) throw new Error(`${p.name} has an invalid format`);
    } else if (p.type === 'boolean') {
      v = !!v;
    } else {
      throw new Error(`unknown param type for ${p.name}`);
    }
    out[p.name] = v;
  }
  return out;
}

// The service manifest: what to show, and how to tell if it's up. This mirrors
// status.sh's checks. `profile: null` means "core" — started by every ./start.sh
// call, no profile flag needed.
const SERVICES = [
  { id: 'postgres', label: 'PostgreSQL', profile: null, port: 5432 },
  { id: 'redis', label: 'Redis', profile: null, port: 6379 },
  { id: 'mongodb', label: 'MongoDB', profile: null, port: 27017 },
  { id: 'elasticsearch', label: 'Elasticsearch', profile: null, port: 9200, url: 'http://localhost:9200' },
  { id: 'api', label: 'API', profile: null, port: 3000, url: 'http://localhost:3000/docs' },
  { id: 'kong', label: 'Kong', profile: 'gateway', port: 8000, url: 'http://localhost:8000' },
  { id: 'kafka', label: 'Kafka', profile: 'streaming', port: 9092 },
  { id: 'kafka-ui', label: 'Kafka UI', profile: 'streaming', port: 8080, url: 'http://localhost:8080' },
  { id: 'spark-master', label: 'Spark master', profile: 'streaming', port: 8081, url: 'http://localhost:8081' },
  { id: 'spark-worker', label: 'Spark worker', profile: 'streaming', port: 8082 },
  { id: 'kibana', label: 'Kibana', profile: 'analytics', port: 5601, url: 'http://localhost:5601' },
  { id: 'prometheus', label: 'Prometheus', profile: 'observability', port: 9090, url: 'http://localhost:9090' },
  { id: 'grafana', label: 'Grafana', profile: 'observability', port: 3001, url: 'http://localhost:3001' },
  { id: 'tempo', label: 'Tempo', profile: 'observability', port: 3200, url: 'http://localhost:3200' },
  { id: 'cassandra', label: 'Cassandra', profile: 'extras', port: 9042 },
  { id: 'keycloak', label: 'Keycloak', profile: 'extras', port: 8180, url: 'http://localhost:8180' },
];

// ── Origin/Host guard ──────────────────────────────────────────────────────
function sameOrigin(req) {
  const wantHost = `${HOST}:${PORT}`;
  const wantHostAlt = `localhost:${PORT}`;
  const host = req.headers.host || '';
  if (host !== wantHost && host !== wantHostAlt) return false;
  const origin = req.headers.origin;
  if (origin) {
    if (origin !== `http://${wantHost}` && origin !== `http://${wantHostAlt}`) return false;
  }
  return true;
}

// ── docker compose ps, parsed defensively (JSON array OR one-object-per-line) ─
function dockerComposePs() {
  return new Promise((resolve) => {
    const args = ['compose'];
    for (const p of PROFILES) args.push('--profile', p);
    args.push('--profile', 'tools', 'ps', '--format', 'json');
    const child = spawn('docker', args, { cwd: REPO_ROOT });
    let out = '';
    let err = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', () => resolve({ ok: false, error: 'docker not found on PATH', containers: [] }));
    child.on('close', () => {
      const trimmed = out.trim();
      if (!trimmed) return resolve({ ok: true, containers: [] });
      let containers = [];
      try {
        const parsed = JSON.parse(trimmed);
        containers = Array.isArray(parsed) ? parsed : [parsed];
      } catch {
        // Compose v2 sometimes prints one JSON object per line instead of an array.
        containers = trimmed.split('\n').filter(Boolean).map((line) => {
          try { return JSON.parse(line); } catch { return null; }
        }).filter(Boolean);
      }
      if (!containers.length && err.trim()) {
        return resolve({ ok: false, error: err.trim().slice(0, 300), containers: [] });
      }
      resolve({ ok: true, containers });
    });
  });
}

// ── plain TCP reachability probe — works for every service, HTTP or not ────
function probePort(port, timeoutMs = 800) {
  return new Promise((resolve) => {
    const sock = net.connect({ host: '127.0.0.1', port, timeout: timeoutMs });
    const done = (up) => { sock.destroy(); resolve(up); };
    sock.on('connect', () => done(true));
    sock.on('timeout', () => done(false));
    sock.on('error', () => done(false));
  });
}

async function buildStatus() {
  const compose = await dockerComposePs();
  const byName = new Map();
  for (const c of compose.containers) {
    const name = c.Name || c.Names || c.Service;
    if (name) byName.set(String(name).replace(/^\//, ''), c);
  }
  const services = await Promise.all(SERVICES.map(async (svc) => {
    const c = byName.get(svc.id);
    const reachable = await probePort(svc.port);
    let state = 'stopped';       // no container, port closed
    if (c) {
      const s = String(c.State || c.Status || '').toLowerCase();
      const h = String(c.Health || '').toLowerCase();
      if (h === 'unhealthy') state = 'unhealthy';
      else if (s.includes('running') || s.includes('up')) state = reachable ? 'up' : 'starting';
      else if (s.includes('exited') || s.includes('dead')) state = 'exited';
      else state = 'starting';
    } else if (reachable) {
      state = 'up'; // container name didn't match, but the port answers — still report it accurately
    }
    return { ...svc, state, container: c ? (c.Status || c.State || '') : null };
  }));
  return { dockerOk: compose.ok, dockerError: compose.error || null, services };
}

// ── run management: one at a time, output buffered + streamed via SSE ──────
let current = null; // { id, cmd, label, buffer:[], subscribers:Set, done:null|{code} }

function startRun(label, cmd, args) {
  const id = String(Date.now());
  const run = { id, label, buffer: [], subscribers: new Set(), done: null };
  current = run;
  const child = spawn(cmd, args, { cwd: REPO_ROOT, env: process.env });
  const push = (chunk) => {
    const text = chunk.toString();
    run.buffer.push(text);
    if (run.buffer.length > 4000) run.buffer.shift();
    for (const res of run.subscribers) writeSSE(res, 'line', text);
  };
  child.stdout.on('data', push);
  child.stderr.on('data', push);
  child.on('close', (code) => {
    run.done = { code };
    for (const res of run.subscribers) { writeSSE(res, 'done', { code }); res.end(); }
    run.subscribers.clear();
  });
  child.on('error', (e) => {
    run.done = { code: -1 };
    const msg = `\n[dashboard] failed to start: ${e.message}\n`;
    run.buffer.push(msg);
    for (const res of run.subscribers) { writeSSE(res, 'line', msg); writeSSE(res, 'done', { code: -1 }); res.end(); }
    run.subscribers.clear();
  });
  return run;
}

function writeSSE(res, event, data) {
  const payload = typeof data === 'string' ? data : JSON.stringify(data);
  res.write(`event: ${event}\ndata: ${payload.replace(/\n/g, '\\n')}\n\n`);
}

// ── HTTP layer ──────────────────────────────────────────────────────────────
function sendJSON(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req, limit = 65536) {
  return new Promise((resolve, reject) => {
    let data = '';
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) { reject(new Error('body too large')); req.destroy(); return; }
      data += chunk;
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || HOST}`);

  if (req.method === 'GET' && url.pathname === '/') {
    fs.readFile(HTML_PATH, (err, buf) => {
      if (err) return sendJSON(res, 500, { error: 'dashboard.html not found next to server.js' });
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Length': buf.length });
      res.end(buf);
    });
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/status') {
    const status = await buildStatus();
    status.run = current ? { id: current.id, label: current.label, running: !current.done, code: current.done ? current.done.code : null } : null;
    return sendJSON(res, 200, status);
  }

  if (req.method === 'GET' && url.pathname === '/api/logs') {
    const id = url.searchParams.get('run');
    if (!current || current.id !== id) return sendJSON(res, 404, { error: 'no such run' });
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    });
    for (const line of current.buffer) writeSSE(res, 'line', line);
    if (current.done) { writeSSE(res, 'done', current.done); return res.end(); }
    current.subscribers.add(res);
    req.on('close', () => current && current.subscribers.delete(res));
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/tutorials') {
    // Strip `file` from what the client sees — it's a server-side detail, not
    // something the front end should ever construct itself.
    const list = TUTORIALS.map(({ id, title, available, blockedOn }) => ({ id, title, available, blockedOn }));
    return sendJSON(res, 200, { chapters: list });
  }

  if (req.method === 'GET' && url.pathname === '/api/tutorials/chapter') {
    const id = url.searchParams.get('id');
    const chapter = TUTORIALS.find((c) => c.id === id);
    if (!chapter) return sendJSON(res, 404, { error: 'unknown chapter' });
    if (!chapter.available) return sendJSON(res, 404, { error: 'chapter not written yet', blockedOn: chapter.blockedOn || null });
    // `chapter.file` is server-controlled (from the fixed TUTORIALS array above,
    // never from the request), so there is no path-traversal surface here even
    // though we don't separately sanitize `id`.
    fs.readFile(path.join(TUTORIAL_DIR, chapter.file), 'utf8', (err, text) => {
      if (err) return sendJSON(res, 500, { error: 'chapter file missing on disk: ' + chapter.file });
      res.writeHead(200, { 'Content-Type': 'text/markdown; charset=utf-8' });
      res.end(text);
    });
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/experiments') {
    return sendJSON(res, 200, { experiments: EXPERIMENTS });
  }

  if (req.method === 'POST' && url.pathname === '/api/experiment') {
    if (!sameOrigin(req)) return sendJSON(res, 403, { error: 'rejected: Host/Origin did not match this server' });
    if (current && !current.done) return sendJSON(res, 409, { error: `an action is already running: ${current.label}` });

    let body;
    try { body = JSON.parse((await readBody(req)) || '{}'); }
    catch { return sendJSON(res, 400, { error: 'invalid JSON body' }); }

    const exp = EXPERIMENTS.find((e) => e.id === body.id);
    if (!exp) return sendJSON(res, 400, { error: `unknown experiment: ${body.id}` });

    let params;
    try { params = validateParams(exp.params, body.params); }
    catch (e) { return sendJSON(res, 400, { error: e.message }); }

    const args = EXPERIMENT_BUILDERS[exp.id](params);
    const run = startRun(`${exp.label}: ${args.join(' ')}`, exp.cmd, args);
    return sendJSON(res, 202, { runId: run.id });
  }

  if (req.method === 'GET' && url.pathname === '/api/spark/status') {
    const status = await sparkAppStatus();
    status.managedByDashboard = !!(sparkRun && !sparkRun.done);
    return sendJSON(res, 200, status);
  }

  if (req.method === 'GET' && url.pathname === '/api/argocd/status') {
    return sendJSON(res, 200, await argocdStatus());
  }

  if (req.method === 'POST' && url.pathname === '/api/spark/start') {
    if (!sameOrigin(req)) return sendJSON(res, 403, { error: 'rejected: Host/Origin did not match this server' });
    if (sparkRun && !sparkRun.done) return sendJSON(res, 409, { error: 'Spark was already started from this dashboard' });
    const status = await sparkAppStatus();
    if (status.running) return sendJSON(res, 409, { error: 'a Spark application is already running (started outside the dashboard?)' });
    const run = startSparkRun();
    return sendJSON(res, 202, { runId: run.id });
  }

  if (req.method === 'POST' && url.pathname === '/api/spark/stop') {
    if (!sameOrigin(req)) return sendJSON(res, 403, { error: 'rejected: Host/Origin did not match this server' });
    const status = await sparkAppStatus();
    if (!status.running) return sendJSON(res, 400, { error: 'no Spark application is currently running' });
    const ok = await sparkAppKill(status.appId);
    if (!ok) return sendJSON(res, 502, { error: 'failed to reach Spark Master to stop the application' });
    return sendJSON(res, 202, { stopped: status.appId });
  }

  if (req.method === 'GET' && url.pathname === '/api/spark/logs') {
    const id = url.searchParams.get('run');
    if (!sparkRun || sparkRun.id !== id) return sendJSON(res, 404, { error: 'no such run' });
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    });
    for (const line of sparkRun.buffer) writeSSE(res, 'line', line);
    if (sparkRun.done) { writeSSE(res, 'done', sparkRun.done); return res.end(); }
    sparkRun.subscribers.add(res);
    req.on('close', () => sparkRun && sparkRun.subscribers.delete(res));
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/action') {
    if (!sameOrigin(req)) return sendJSON(res, 403, { error: 'rejected: Host/Origin did not match this server' });
    if (current && !current.done) return sendJSON(res, 409, { error: `an action is already running: ${current.label}` });

    let body;
    try { body = JSON.parse((await readBody(req)) || '{}'); }
    catch { return sendJSON(res, 400, { error: 'invalid JSON body' }); }

    const action = body.action;
    if (action === 'start') {
      const requested = Array.isArray(body.profiles) ? body.profiles : [];
      const profiles = [];
      for (const p of requested) {
        if (!PROFILES.includes(p)) return sendJSON(res, 400, { error: `unknown profile: ${p}` });
        profiles.push(p);
      }
      const run = startRun(profiles.length ? `start.sh ${profiles.join(' ')}` : 'start.sh (core)', './start.sh', profiles);
      return sendJSON(res, 202, { runId: run.id });
    }
    if (action === 'stop') {
      const run = startRun('stop.sh', './stop.sh', []);
      return sendJSON(res, 202, { runId: run.id });
    }
    if (action === 'reset') {
      if (body.confirm !== 'RESET') return sendJSON(res, 400, { error: 'reset requires {"confirm":"RESET"} — this deletes all data' });
      const run = startRun('reset.sh --yes', './reset.sh', ['--yes']);
      return sendJSON(res, 202, { runId: run.id });
    }
    return sendJSON(res, 400, { error: `unknown action: ${action}` });
  }

  sendJSON(res, 404, { error: 'not found' });
});

// Only actually bind a socket when run directly (`node server.js`). When
// this file is `require()`d — by the unit tests, for its pure functions —
// nothing here should open a real listener.
if (require.main === module) {
  server.listen(PORT, HOST, () => {
    console.log(`AdLab dashboard: http://${HOST}:${PORT}  (bound to ${HOST} only — not reachable from the network)`);
  });
}

// Exported for dashboard/test/*.test.js — pure functions only, no side effects.
module.exports = { validateParams, buildClickstreamArgs, EXPERIMENTS, PROFILES };
