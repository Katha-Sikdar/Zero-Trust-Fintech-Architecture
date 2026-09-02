// Standalone assertions for the authorization truth table (no test runner, no
// external deps). Run: node app/test/authz.test.js
'use strict';
const assert = require('assert');
const { authorize } = require('../src/decisions');

const cust = { sub: 'u001', role: 'customer' };
const admin = { sub: 'u000', role: 'admin' };
let n = 0; const ok = (c, m) => { assert.ok(c, m); n++; };

// --- app-layer enforcement (S3/S5 style) ---
ok(authorize(cust, { owner: 'u001' }, 'app').allow, 'owner reads own object');
ok(!authorize(cust, { owner: 'u002' }, 'app').allow, 'BOLA: customer denied on another owner');
ok(authorize(admin, { owner: 'u050' }, 'app').allow, 'admin override reads any object');
ok(!authorize(cust, { role: 'admin' }, 'app').allow, 'BFLA: customer denied on admin function');
ok(authorize(admin, { role: 'admin' }, 'app').allow, 'admin allowed on admin function');
ok(!authorize(null, { owner: 'u001' }, 'app').allow, 'no principal denied');
assert.strictEqual(authorize(cust, { owner: 'u002' }, 'app').reason, 'not_owner');
assert.strictEqual(authorize(cust, { role: 'admin' }, 'app').reason, 'wrong_role');

// --- baseline: no authz means the BOLA/BFLA attacks SUCCEED (by design) ---
ok(authorize(cust, { owner: 'u002' }, 'none').allow, 'baseline S0: BOLA not blocked');
ok(authorize(cust, { role: 'admin' }, 'none').allow, 'baseline S0: BFLA not blocked');

// --- delegated: gateway/OPA already decided; reaching app == allow ---
assert.strictEqual(authorize(cust, { owner: 'u002' }, 'delegated').layer, 'sidecar');

console.log(`authz truth table: ${n} assertions passed`);
