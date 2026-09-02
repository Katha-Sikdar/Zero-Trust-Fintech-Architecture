// Loads the pre-minted token corpus (see scripts/mint-tokens.js) once, shared
// across VUs. k6 cannot sign RSA/EC, so tokens are minted offline for
// determinism.
import { SharedArray } from 'k6/data';

const data = new SharedArray('corpus', () => [JSON.parse(open('../tokens.json'))]);
export const TOKENS = data[0];

export function bearer(t) { return { Authorization: `Bearer ${t}` }; }

// benign token for a given user, algorithm chosen by scenario (RS256 default)
export function validToken(uid, alg) {
  return (alg === 'ES256' ? TOKENS.valid_es256 : TOKENS.valid_rs256)[uid];
}
