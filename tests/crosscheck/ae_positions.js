// Independent cross-check with astronomy-engine (MIT, VSOP87/ELP/NOVAS-based; no Swiss Ephemeris code).
// stdin: [{"id":..., "utc":"ISO", "lat":deg, "lon":deg}]  stdout: {id: {sun:..., ..., asc:..., mc:...}}
const A = require('astronomy-engine');
const BODIES = {sun: A.Body.Sun, moon: A.Body.Moon, mercury: A.Body.Mercury, venus: A.Body.Venus, mars: A.Body.Mars,
  jupiter: A.Body.Jupiter, saturn: A.Body.Saturn, uranus: A.Body.Uranus, neptune: A.Body.Neptune, pluto: A.Body.Pluto};
const D = Math.PI / 180;
const norm = x => ((x % 360) + 360) % 360;
function angles(date, lat, lon) {
  const t = A.MakeTime(date);
  const gast = A.SiderealTime(t);               // hours, apparent sidereal time
  const ramc = norm(gast * 15 + lon) * D;
  // true obliquity: ecliptic pole (ECT z axis) expressed in equator-of-date coordinates
  const rot = A.Rotation_ECT_EQD(t);
  const pole = A.RotateVector(rot, new A.Vector(0, 0, 1, t));
  const eps = Math.acos(pole.z);
  const mc = norm(Math.atan2(Math.sin(ramc), Math.cos(ramc) * Math.cos(eps)) / D);
  const asc = norm(Math.atan2(Math.cos(ramc), -(Math.sin(ramc) * Math.cos(eps) + Math.tan(lat * D) * Math.sin(eps))) / D);
  return {asc, mc, eps: eps / D};
}
let input = '';
process.stdin.on('data', d => input += d).on('end', () => {
  const out = {};
  for (const c of JSON.parse(input)) {
    const date = new Date(c.utc);
    const r = {};
    // Optional: align Delta-T with Swiss Ephemeris (c.dt_se seconds) so that body positions are compared at the
    // same Terrestrial Time; models diverge for future dates (e.g. 2099: SE 93 s vs astronomy-engine 200 s).
    let bdate = date;
    if (typeof c.dt_se === 'number') {
      const t = A.MakeTime(date);
      const dtAe = (t.tt - t.ut) * 86400;
      bdate = new Date(date.getTime() + (c.dt_se - dtAe) * 1000);
      r.dt_ae = dtAe;
    }
    for (const [k, b] of Object.entries(BODIES)) r[k] = A.Ecliptic(A.GeoVector(b, bdate, true)).elon;
    if (c.lat !== null && c.lat !== undefined) Object.assign(r, angles(date, c.lat, c.lon));
    out[c.id] = r;
  }
  process.stdout.write(JSON.stringify(out));
});
