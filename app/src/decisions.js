// Pure, dependency-free security-decision logic. Kept separate from server.js
// so the object/function-level authorization truth table can be unit-tested
// without booting Express or installing crypto libraries.
'use strict';

// authorize(principal, need, authMode) -> { allow, layer, reason? }
//   principal: { sub, role } | null
//   need:      { owner?: uid, role?: 'admin' }
//   authMode:  'none' | 'app' | 'delegated'
function authorize(principal, need, authMode) {
  if (authMode === 'none') return { allow: true, layer: 'none' };
  if (authMode === 'delegated') return { allow: true, layer: 'sidecar' };
  if (!principal) return { allow: false, layer: 'app', reason: 'no_principal' };
  if (need.role && principal.role !== need.role)
    return { allow: false, layer: 'app', reason: 'wrong_role' };
  if (need.owner && principal.sub !== need.owner && principal.role !== 'admin')
    return { allow: false, layer: 'app', reason: 'not_owner' };
  return { allow: true, layer: 'app' };
}

module.exports = { authorize };
