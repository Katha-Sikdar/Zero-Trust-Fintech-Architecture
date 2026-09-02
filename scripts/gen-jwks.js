// Builds a JWKS (RSA + EC public keys) from the generated PEMs so Envoy's
// jwt_authn filter can validate tokens locally. Output: envoy/jwks.json
'use strict';
const { createPublicKey } = require('crypto');
const fs = require('fs');
const path = require('path');

const KEYS = path.join(__dirname, '..', 'app', 'keys');
const rsa = createPublicKey(fs.readFileSync(path.join(KEYS, 'rsa-public.pem')))
  .export({ format: 'jwk' });
const ec = createPublicKey(fs.readFileSync(path.join(KEYS, 'ec-public.pem')))
  .export({ format: 'jwk' });

const jwks = {
  keys: [
    { ...rsa, use: 'sig', alg: 'RS256', kid: 'test-key-1' },
    { ...ec, use: 'sig', alg: 'ES256', kid: 'test-key-2' },
  ],
};
const out = path.join(__dirname, '..', 'envoy', 'jwks.json');
fs.writeFileSync(out, JSON.stringify(jwks, null, 2));
console.log('wrote', out);
