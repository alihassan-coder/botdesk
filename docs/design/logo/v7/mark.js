// The bd mark, v7: two circles and two straight lines.
// Each bowl is a true circle. The crossing is the pair of internal tangent lines between
// the circles, so curve and line meet with no kink. The b and d stems rise from the
// outermost points of the circles, where the curve is exactly vertical.
function bdGeometry({ cx = 50, cy = 68, r = 15.5, gap = 36, top = 16 } = {}) {
  const h = gap / 2;                       // centre of each circle is h from the middle
  const beta = Math.acos(r / h);           // angle from the centre line to the tangent point
  const Lx = cx - h, Rx = cx + h;
  const f = v => +v.toFixed(3);
  const T1 = [f(Lx + r * Math.cos(beta)), f(cy - r * Math.sin(beta))]; // left circle, upper
  const T2 = [f(Lx + r * Math.cos(beta)), f(cy + r * Math.sin(beta))]; // left circle, lower
  const T3 = [f(Rx - r * Math.cos(beta)), f(cy - r * Math.sin(beta))]; // right circle, upper
  const T4 = [f(Rx - r * Math.cos(beta)), f(cy + r * Math.sin(beta))]; // right circle, lower
  const loop = `M${T1} A${r} ${r} 0 1 0 ${T2} L${T3} A${r} ${r} 0 1 1 ${T4} Z`.replace(/,/g, ' ');
  const stems = `M${f(Lx - r)} ${top} V${cy} M${f(Rx + r)} ${top} V${cy}`;
  return { loop, stems, Lx, Rx, r, cy, top, T: [T1, T2, T3, T4] };
}

// SVG markup for the mark in a 100×100 box, painted with currentColor.
function bdMark(sw = 11, opts) {
  const g = bdGeometry(opts);
  return `<g fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">` +
         `<path d="${g.stems}"/><path d="${g.loop}"/></g>`;
}

if (typeof module !== 'undefined') module.exports = { bdGeometry, bdMark };
