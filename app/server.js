// ZTA FinTech API target.
//
// A single service whose SECURITY BEHAVIOUR is chosen entirely by environment
// variables, so that scenarios S0..S6 in the proposal are the same binary with
// different config. Every response carries an x-enforced-by header naming the
// layer that made the security decision, and an x-decision header (allow|deny)
// so the k6 harness can build a ground-truth confusion matrix without parsing
// bodies.
'use strict';

const express = require('express');
const jwt = require('jsonwebtoken');
const fs = require('fs');
const path = require('path');
const client = require('prom-client');

const config = require('./src/config');
const { accounts, users } = require('./src/data');
const Pool = require('./src/pool');
const { authorize: authorizeFn } = require('./src/decisions');

const KEYS = path.join(__dirname, 'keys');
const rsaPub = safeRead(path.join(KEYS, 'rsa-public.pem'));
const ecPub = safeRead(path.join(KEYS, 'ec-public.pem'));
const hmac = safeRead(path.join(KEYS, 'hmac.key'));
function safeRead(p) { try { return fs.readFileSync(p); } catch { return null; } }

const pubForAlg = (alg) => (alg === 'ES256' ? ecPub : alg === 'HS256' ? hmac : rsaPub);
const pool = config.offloadCrypto ? new Pool(config.workerPoolSize) : null;

// ---------------------------------------------------------------- metrics
const register = new client.Registry();
client.collectDefaultMetrics({ register, prefix: 'app_' });
const httpHist = new client.Histogram({
  name: 'app_request_duration_seconds',
  help: 'request latency',
  labelNames: ['route', 'code', 'decision'],
  buckets: [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5],
  registers: [register],
});
const decisionCtr = new client.Counter({
  name: 'app_security_decision_total',
  help: 'security decisions by layer and outcome',
  labelNames: ['layer', 'decision', 'reason'],
  registers: [register],
});
const failOpenCtr = new client.Counter({
  name: 'app_fail_open_total',
  help: 'requests admitted to business logic without a completed security decision',
  registers: [register],
});

// ---------------------------------------------------------------- helpers
function burnCpu(ms) {                     // deterministic busy-work
  const end = process.hrtime.bigint() + BigInt(ms) * 1000000n;
  let x = 0;
  while (process.hrtime.bigint() < end) { x += Math.sqrt(x + 1); }
  return x;
}

function decodePayloadHeader(req) {
  const raw = req.headers[config.jwtPayloadHeader];
  if (!raw) return null;
  try { return JSON.parse(Buffer.from(raw, 'base64url').toString('utf8')); }
  catch { try { return JSON.parse(raw); } catch { return null; } }
}

async function verifyToken(req) {
  const h = req.headers['authorization'] || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : null;
  if (!token) return { ok: false, reason: 'missing_token' };
  const algs = [config.jwtAlg];            // pinned: rejects alg:none & confusion
  const key = pubForAlg(config.jwtAlg);
  try {
    const payload = pool
      ? await pool.verify(token, key, algs).then((m) => { if (!m.ok) throw new Error(m.error); return m.payload; })
      : jwt.verify(token, key, { algorithms: algs });
    return { ok: true, payload };
  } catch (e) {
    return { ok: false, reason: 'invalid_token:' + e.message.slice(0, 40) };
  }
}

// Resolve the effective principal for this request given the JWT enforcement
// point. Returns { principal, layer, denied?, reason? }.
async function authenticate(req) {
  if (config.jwtMode === 'none') {
    return { principal: users[req.headers['x-debug-sub']] || null, layer: 'none' };
  }
  if (config.jwtMode === 'delegated') {
    // Envoy/Istio validated the JWT and injected the payload. If the header is
    // absent we must decide: fail closed (deny) — the correct posture. A10 tests
    // whether, under saturation, this path is reachable without the header.
    const p = decodePayloadHeader(req);
    if (!p) { decisionCtr.inc({ layer: 'sidecar', decision: 'deny', reason: 'no_verified_claims' });
              return { denied: true, layer: 'sidecar', reason: 'no_verified_claims' }; }
    return { principal: { sub: p.sub, role: p.role || 'customer' }, layer: 'sidecar' };
  }
  // app-layer
  const v = await verifyToken(req);
  if (!v.ok) { decisionCtr.inc({ layer: 'app', decision: 'deny', reason: v.reason });
               return { denied: true, layer: 'app', reason: v.reason }; }
  return { principal: { sub: v.payload.sub, role: v.payload.role || 'customer' }, layer: 'app' };
}

// Object/function-level authorization (pure logic in src/decisions.js so the
// truth table is unit-tested independently of Express).
function authorize(principal, need) {
  return authorizeFn(principal, need, config.authMode);
}

// ---------------------------------------------------------------- app
const app = express();
app.use(express.json());

app.get('/health', (_req, res) => res.json({ ok: true, scenario: config.scenario }));
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

// Issue a token (convenience; the k6 corpus normally forges its own).
app.post('/login', (req, res) => {
  const uid = (req.body && req.body.sub) || 'u001';
  const u = users[uid];
  if (!u) return res.status(404).json({ error: 'no such user' });
  const key = config.jwtAlg === 'ES256' ? safeRead(path.join(KEYS, 'ec-private.pem'))
            : config.jwtAlg === 'HS256' ? hmac
            : safeRead(path.join(KEYS, 'rsa-private.pem'));
  const token = jwt.sign({ sub: u.sub, role: u.role }, key,
    { algorithm: config.jwtAlg, expiresIn: '15m', keyid: 'test-key-1' });
  res.json({ token });
});

// Wrap a protected handler with the two enforcement stages + timing.
function protect(needFn, handler) {
  return async (req, res) => {
    const start = process.hrtime.bigint();
    const route = req.route ? req.route.path : req.path;
    let decision = 'allow';
    let admittedWithoutAuthn = false;

    const authn = await authenticate(req);
    if (authn.denied) {
      decision = 'deny';
      finish(res, 401, { error: 'unauthenticated', reason: authn.reason }, authn.layer, decision);
      return record(start, route, 401, decision);
    }
    if (config.jwtMode !== 'none' && !authn.principal) admittedWithoutAuthn = true;

    const need = needFn(req);
    const az = authorize(authn.principal, need);
    if (!az.allow) {
      decision = 'deny';
      decisionCtr.inc({ layer: az.layer, decision: 'deny', reason: az.reason || 'authz' });
      finish(res, 403, { error: 'forbidden', reason: az.reason }, az.layer, decision);
      return record(start, route, 403, decision);
    }

    if (admittedWithoutAuthn) failOpenCtr.inc();
    decisionCtr.inc({ layer: az.layer, decision: 'allow', reason: 'ok' });
    burnCpu(config.businessCpuMs);
    const body = handler(req, authn.principal);
    finish(res, body.code || 200, body.json, az.layer, decision);
    record(start, route, body.code || 200, decision);
  };
}

function finish(res, code, json, layer, decision) {
  res.set('x-enforced-by', layer);
  res.set('x-decision', decision);
  res.status(code).json(json);
}
function record(start, route, code, decision) {
  const sec = Number(process.hrtime.bigint() - start) / 1e9;
  httpHist.observe({ route, code: String(code), decision }, sec);
}

// ---- protected resources (BOLA / BFLA / business flow) ----
app.get('/accounts/:id',
  protect(
    (req) => ({ owner: accounts[req.params.id] && accounts[req.params.id].owner }),
    (req) => {
      const a = accounts[req.params.id];
      if (!a) return { code: 404, json: { error: 'not found' } };
      return { code: 200, json: { id: a.id, balanceMinor: a.balanceMinor, currency: a.currency } };
    }));

app.get('/accounts/:id/transactions',
  protect(
    (req) => ({ owner: accounts[req.params.id] && accounts[req.params.id].owner }),
    (req) => {
      const a = accounts[req.params.id];
      if (!a) return { code: 404, json: { error: 'not found' } };
      return { code: 200, json: { id: a.id, transactions: a.transactions } };
    }));

app.post('/transfers',
  protect(
    (req) => ({ owner: accounts[(req.body || {}).from] && accounts[(req.body || {}).from].owner }),
    (req) => {
      const { from, to, amountMinor } = req.body || {};
      if (!accounts[from] || !accounts[to]) return { code: 404, json: { error: 'unknown account' } };
      return { code: 200, json: { from, to, amountMinor, status: 'accepted' } };
    }));

// Function-level: admin only (BFLA target).
app.delete('/admin/users/:id',
  protect(
    () => ({ role: 'admin' }),
    (req) => ({ code: 200, json: { deleted: req.params.id } })));

const server = app.listen(config.port, () => {
  console.log(`[zta-api] scenario=${config.scenario} jwt=${config.jwtMode}/${config.jwtAlg} ` +
              `authz=${config.authMode} offload=${config.offloadCrypto} :${config.port}`);
});
server.keepAliveTimeout = 65000;
