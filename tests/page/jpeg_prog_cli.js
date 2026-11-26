// Usa site/jpeg_prog.js da riga di comando (per le prove): node tests/page/jpeg_prog_cli.js <ingresso.jpg> <uscita.jpg>  -> stampa le fine dei livelli (JSON)
const fs = require('fs');
const path = require('path');
const { transcode } = require(path.resolve(__dirname, '..', '..', 'site', 'jpeg_prog.js'));
try {
  const r = transcode(new Uint8Array(fs.readFileSync(process.argv[2])));
  fs.writeFileSync(process.argv[3], Buffer.from(r.data));
  console.log(JSON.stringify(r.ends));
} catch (e) { console.error('errore: ' + e.message); process.exit(2); }
