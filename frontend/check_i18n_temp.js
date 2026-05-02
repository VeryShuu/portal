const fs = require('fs');
const ru = JSON.parse(fs.readFileSync('src/i18n/ru.json', 'utf8'));
const en = JSON.parse(fs.readFileSync('src/i18n/en.json', 'utf8'));

function flat(o, p) {
  p = p || '';
  return Object.entries(o).reduce(function(a, e) {
    var k = e[0]; var v = e[1];
    var fk = p ? p + '.' + k : k;
    if (typeof v === 'object' && v && !Array.isArray(v)) {
      Object.assign(a, flat(v, fk));
    } else {
      a[fk] = v;
    }
    return a;
  }, {});
}

var rk = Object.keys(flat(ru));
var ek = new Set(Object.keys(flat(en)));
var miss = rk.filter(function(k) { return !ek.has(k); });
console.log('Missing in en: ' + miss.length);
miss.slice(0, 40).forEach(function(k) { console.log('  ' + k); });
var extra = Object.keys(flat(en)).filter(function(k) { return !new Set(rk).has(k); });
console.log('Extra in en (not in ru): ' + extra.length);
extra.slice(0, 20).forEach(function(k) { console.log('  +' + k); });
