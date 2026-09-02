// ZTA FinTech testbed — labelled mixed-stream load driver.
//
// Open-loop (constant-arrival-rate) generator that mixes benign traffic with
// the OWASP attack corpus at a controlled offered load. Every request is tagged
// with ground truth and scored into a per-risk confusion matrix. One k6 run =
// one (scenario, load-level) cell of the experiment; scripts/run-sweep.sh
// iterates load levels around the measured elbow (lambda*).
//
// Env:
//   BASE_URL        target (default http://localhost:8081  = gateway plaintext)
//   LOAD_RPS        offered requests/sec (open loop)          default 100
//   DURATION        steady-state duration                     default 60s
//   ATTACK_FRACTION share of requests drawn from attacks      default 0.4
//   JWT_ALG         RS256 | ES256 (benign token algorithm)    default RS256
//   SCENARIO        label written into the summary            default S?
//   WARMUP          V8/JIT warm-up before measurement         default 10s
import http from 'k6/http';
import { sleep } from 'k6';
import { textSummary } from './lib/k6-summary.js';
import { RISKS, CELLS } from './lib/metrics.js';
import { api2Attack, api2Benign } from './attacks/api2_auth.js';
import { bolaAttack, bflaAttack, authzBenign } from './attacks/api1_api5_authz.js';
import { api4Attack, api4Benign } from './attacks/api4_resource.js';
import { api8Attack, api8Benign } from './attacks/api8_misconfig.js';
import { a10Probe } from './attacks/a10_failopen.js';

const BASE = __ENV.BASE_URL || 'http://localhost:8081';
const RPS = parseInt(__ENV.LOAD_RPS || '100', 10);
const DURATION = __ENV.DURATION || '60s';
const WARMUP = __ENV.WARMUP || '10s';
const ATTACK_FRACTION = parseFloat(__ENV.ATTACK_FRACTION || '0.4');
const ALG = __ENV.JWT_ALG || 'RS256';
const SCENARIO = __ENV.SCENARIO || 'S?';

export const options = {
  discardResponseBodies: true,
  // k6 defaults stop at p(95); the elbow analysis keys off p99, so ask for it
  // explicitly or handleSummary writes p99_ms: null and the fit degrades to NaN.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    warmup: {
      executor: 'constant-arrival-rate',
      rate: Math.max(10, Math.floor(RPS / 2)), timeUnit: '1s',
      duration: WARMUP, preAllocatedVUs: 50, maxVUs: 2000,
      exec: 'warm', tags: { phase: 'warmup' }, gracefulStop: '5s',
    },
    measure: {
      executor: 'constant-arrival-rate',
      rate: RPS, timeUnit: '1s', duration: DURATION,
      preAllocatedVUs: 100, maxVUs: 4000,
      startTime: WARMUP, exec: 'mixed', tags: { phase: 'measure' },
    },
  },
  // fail the run only on infrastructure faults, never on attacks being served —
  // that is the signal we are measuring, not a test failure.
  thresholds: { 'http_req_failed{phase:warmup}': ['rate<0.5'] },
};

let counter = 0;

// benign-only during warmup (steady-state prep, discarded)
export function warm() {
  api2Benign(BASE, ALG);
}

// one labelled request per iteration
export function mixed() {
  const i = counter++;
  const attack = (Math.abs(hash(i)) % 1000) / 1000 < ATTACK_FRACTION;
  if (!attack) {
    // rotate benign coverage across risks
    switch (i % 5) {
      case 0: api2Benign(BASE, ALG); break;
      case 1: authzBenign(BASE, ALG); break;
      case 2: api4Benign(BASE, ALG); break;
      case 3: api8Benign(BASE, ALG); break;
      default: api2Benign(BASE, ALG);
    }
    return;
  }
  // rotate attacks across the five in-scope risks
  switch (i % 6) {
    case 0: api2Attack(BASE, ALG, i); break;
    case 1: bolaAttack(BASE, ALG); break;
    case 2: bflaAttack(BASE, ALG); break;
    case 3: api4Attack(BASE, ALG); break;
    case 4: api8Attack(BASE, ALG); break;
    default: a10Probe(BASE, ALG); break;
  }
}

// deterministic hash so attack/benign split is reproducible per iteration
function hash(n) { let h = n * 2654435761; h ^= h >> 15; return h | 0; }

export function handleSummary(data) {
  const m = data.metrics;
  const val = (name) => (m[name] && m[name].values && (m[name].values.count ?? 0)) || 0;
  const matrix = {};
  for (const r of RISKS) {
    const cells = {};
    for (const c of CELLS) cells[c] = val(`cm_${r}_${c}`);
    const tp = cells.tp, fp = cells.fp, tn = cells.tn, fn = cells.fn;
    const attacks = tp + fn, benign = tn + fp;
    matrix[r] = {
      ...cells,
      block_rate: attacks ? tp / attacks : null,          // recall on attacks
      false_positive_rate: benign ? fp / benign : null,   // benign wrongly blocked
      attacks_sent: attacks, benign_sent: benign,
      p95_latency_ms: (m[`lat_${r}`] && m[`lat_${r}`].values['p(95)']) || null,
    };
  }
  const out = {
    scenario: SCENARIO, load_rps: RPS, jwt_alg: ALG,
    duration: DURATION, attack_fraction: ATTACK_FRACTION,
    http_reqs: val('http_reqs'),
    p50_ms: (m.http_req_duration && m.http_req_duration.values.med) || null,
    p95_ms: (m.http_req_duration && m.http_req_duration.values['p(95)']) || null,
    p99_ms: (m.http_req_duration && m.http_req_duration.values['p(99)']) || null,
    dropped_iterations: val('dropped_iterations'),
    matrix,
    ts: new Date().toISOString(),
  };
  const path = `results/summary_${SCENARIO}_rps${RPS}_${ALG}.json`;
  const stdout = textSummary(data, { indent: ' ', enableColors: false });
  return { [path]: JSON.stringify(out, null, 2), stdout: stdout + `\n[written] ${path}\n` };
}
