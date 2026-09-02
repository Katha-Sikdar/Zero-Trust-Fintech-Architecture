// Deterministic JWT corpus generator. k6 cannot perform RSA/EC signing, so all
// tokens — benign and malicious — are minted here (real signatures) and written
// to loadgen/tokens.json for the load scripts to consume. Versioned + seeded =
// reproducible attack corpus (proposal Section 5.3).
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

// jsonwebtoken lives in app/node_modules (installed by `npm i` in app/), not
// next to this script, so resolve it from there rather than from scripts/.
const appRequire = createRequire(path.join(__dirname, '..', 'app', 'package.json'));
const jwt = appRequire('jsonwebtoken');

const KEYS = path.join(__dirname, '..', 'app', 'keys');
const rsaPriv = fs.readFileSync(path.join(KEYS, 'rsa-private.pem'));
const rsaPub = fs.readFileSync(path.join(KEYS, 'rsa-public.pem'));
const ecPriv = fs.readFileSync(path.join(KEYS, 'ec-private.pem'));

// a second RSA key the server does NOT trust (wrong-signature attack)
const rogue = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const now = Math.floor(Date.now() / 1000);

function valid(sub, role, alg) {
  const key = alg === 'ES256' ? ecPriv : rsaPriv;
  const kid = alg === 'ES256' ? 'test-key-2' : 'test-key-1';
  return jwt.sign({ sub, role, iss: 'zta-testbed' }, key,
    { algorithm: alg, keyid: kid, expiresIn: '15m' });
}

const out = {
  meta: { minted: now, seed: 42 },

  // --- benign principals (used by benign traffic + as the "own resource" case)
  valid_rs256: {},
  valid_es256: {},

  // --- API2 Broken Authentication attack tokens ---------------------------
  attacks: {
    // alg:none — unsigned token asserting admin. A correct verifier pins the
    // algorithm and rejects this.
    alg_none: b64({ alg: 'none', typ: 'JWT' }) + '.' +
              b64({ sub: 'u000', role: 'admin', iss: 'zta-testbed', exp: now + 900 }) + '.',

    // key confusion: RSA public key used as an HS256 secret. Rejected because
    // the server pins RS256/ES256 and never treats the public key as a secret.
    key_confusion: jwt.sign({ sub: 'u000', role: 'admin', iss: 'zta-testbed' },
                            rsaPub, { algorithm: 'HS256', expiresIn: '15m' }),

    // expired token (valid signature, exp in the past)
    expired: jwt.sign({ sub: 'u001', role: 'customer', iss: 'zta-testbed' },
                      rsaPriv, { algorithm: 'RS256', keyid: 'test-key-1', expiresIn: -60 }),

    // signed by an untrusted key
    wrong_signature: jwt.sign({ sub: 'u000', role: 'admin', iss: 'zta-testbed' },
                              rogue.privateKey, { algorithm: 'RS256', expiresIn: '15m' }),

    // tampered payload on a real token (signature no longer matches)
    tampered: (() => {
      const t = valid('u001', 'customer', 'RS256').split('.');
      t[1] = b64({ sub: 'u001', role: 'admin', iss: 'zta-testbed', exp: now + 900 });
      return t.join('.');
    })(),

  },
};

for (let i = 0; i < 11; i++) {
  const uid = 'u' + String(i).padStart(3, '0');
  const role = i === 0 ? 'admin' : 'customer';
  out.valid_rs256[uid] = valid(uid, role, 'RS256');
  out.valid_es256[uid] = valid(uid, role, 'ES256');
}

const dest = path.join(__dirname, '..', 'loadgen', 'tokens.json');
fs.writeFileSync(dest, JSON.stringify(out, null, 2));
console.log('wrote', dest, '-', Object.keys(out.attacks).length, 'attack tokens,',
            Object.keys(out.valid_rs256).length, 'benign principals');
