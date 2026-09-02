// Deterministic synthetic account data. No real PII (proposal ethics section).
'use strict';
const config = require('./config');

// 100 accounts owned by 100 users u000..u099; account aNNN owned by uNNN.
// One admin (u000). Used to make BOLA/BFLA ground-truth unambiguous.
const accounts = {};
const users = {};
for (let i = 0; i < 100; i++) {
  const uid = 'u' + String(i).padStart(3, '0');
  const aid = 'a' + String(i).padStart(3, '0');
  users[uid] = { sub: uid, role: i === 0 ? 'admin' : 'customer' };
  accounts[aid] = {
    id: aid,
    owner: uid,
    balanceMinor: 100000 + ((i * 7919) % 900000), // pseudo, not financial data
    currency: 'USD',
    transactions: Array.from({ length: 5 }, (_, t) => ({
      id: `${aid}-t${t}`,
      amountMinor: 100 * ((i + t) % 50 + 1),
      kind: t % 2 ? 'debit' : 'credit',
    })),
  };
}
module.exports = { accounts, users };
