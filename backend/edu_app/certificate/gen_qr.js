const QRCode = require('/usr/lib/node_modules/npm/node_modules/qrcode-terminal/vendor/QRCode');
const QRErrorCorrectLevel = require('/usr/lib/node_modules/npm/node_modules/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel');
const fs = require('fs');

const text = process.argv[2];
const outFile = process.argv[3];

// Find the smallest typeNumber (1-40) that works for this data + EC level
let qr = null;
for (let t = 1; t <= 40; t++) {
  try {
    const candidate = new QRCode(t, QRErrorCorrectLevel.M);
    candidate.addData(text);
    candidate.make();
    qr = candidate;
    break;
  } catch (e) {
    if (t === 40) console.error('last error:', e.message);
    continue;
  }
}
if (!qr) {
  throw new Error('Could not fit data into any QR version');
}

const count = qr.getModuleCount();
const matrix = [];
for (let row = 0; row < count; row++) {
  const r = [];
  for (let col = 0; col < count; col++) {
    r.push(qr.isDark(row, col) ? 1 : 0);
  }
  matrix.push(r);
}

fs.writeFileSync(outFile, JSON.stringify({ size: count, matrix: matrix }));
console.log('QR generated:', count, 'x', count, 'modules for text length', text.length);
