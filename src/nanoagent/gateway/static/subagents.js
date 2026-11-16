/* nano Agent sub-agent mascots. Pure functions, no deps.
 *   letter, shape, colour  <- first A-Z letter of the name (same letter = same look)
 *   eyes, personality      <- FNV-1a hash of the full name (stable, per agent)
 *   status 'running' = animated; anything else = static idle; no name = empty.
 * Exposes window.Subagents (browser) and module.exports (node). */
(function (root) {
  var SHAPES = ['blob', 'triangle', 'cloud', 'teardrop', 'square', 'circle', 'pill', 'squircle'];
  var COLOURS = ['#17b8a6', '#ff3d8b', '#1a7cff', '#ff8a1f', '#00c97a', '#8b5cf6'];
  var EYES = ['pill', 'dot', 'slash'];
  var PERSONALITY = ['bounce', 'sway', 'float', 'wobble'];
  var INK = '#0b0d14';

  var PATHS = {
    blob: 'M50 6C74 4 96 22 94 50S76 96 50 94 6 78 6 50 26 8 50 6Z',
    triangle: 'M50 10C56 10 60 14 66 24L88 62C94 72 90 86 78 88H22C10 86 6 72 12 62L34 24C40 14 44 10 50 10Z',
    cloud: 'M26 84C10 84 8 62 22 58C18 38 40 30 50 40C56 26 80 28 80 46C96 46 96 84 80 84Z',
    teardrop: 'M50 4C60 22 88 46 88 66C88 82 71 96 50 96S12 82 12 66C12 46 40 22 50 4Z'
  };
  // rounded-rect / circle shapes
  var RECTS = {
    square: '<rect x="6" y="6" width="88" height="88" rx="22"/>',
    circle: '<circle cx="50" cy="50" r="44"/>',
    pill: '<rect x="6" y="26" width="88" height="48" rx="24"/>',
    squircle: '<rect x="6" y="6" width="88" height="88" rx="40"/>'
  };

  function fnv1a(s) {
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h >>> 0;
  }

  // murmur3 finaliser: spreads FNV bits so low/high slices are independent
  function mix(h) {
    h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b);
    h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35);
    h ^= h >>> 16;
    return h >>> 0;
  }

  function letterIndex(name) {
    var m = /[A-Za-z]/.exec(name);
    return m ? m[0].toUpperCase().charCodeAt(0) - 65 : fnv1a(name) % 26;
  }

  // name, status -> {state, letter, shape, colour, eyes, personality}
  function describe(name, status) {
    var n = name == null ? '' : String(name).trim();
    if (!n) {
      return { state: 'empty', letter: '?', shape: 'circle', colour: '#9aa0ad', eyes: 'dot', personality: 'none' };
    }
    // every trait from the hash of the FULL name (bit slices, so they are independent)
    var h = mix(fnv1a(n.toLowerCase()));
    var li = letterIndex(n);
    return {
      state: status === 'running' ? 'running' : 'idle',
      letter: String.fromCharCode(65 + li),
      shape: SHAPES[h % 8],
      colour: COLOURS[(h >>> 3) % 6],
      eyes: EYES[(h >>> 6) % 3],
      personality: PERSONALITY[(h >>> 9) % 4]
    };
  }

  function shapeSvg(shape, colour, empty) {
    if (empty) {
      return '<path fill="none" stroke="' + colour + '" stroke-width="3" stroke-dasharray="6 6" d="' + PATHS.blob + '"/>';
    }
    if (PATHS[shape]) return '<path fill="' + colour + '" d="' + PATHS[shape] + '"/>';
    return RECTS[shape].replace('/>', ' fill="' + colour + '"/>');
  }

  function eyesSvg(type, shape) {
    var cy = (shape === 'teardrop' || shape === 'triangle' || shape === 'cloud') ? 58 : 50;
    var cxs = shape === 'teardrop' ? [40, 60] : [38, 62];
    return cxs.map(function (cx) {
      if (type === 'dot') return '<circle class="sa-eye" cx="' + cx + '" cy="' + cy + '" r="5" fill="' + INK + '"/>';
      if (type === 'slash') return '<rect class="sa-eye" x="' + (cx - 3) + '" y="' + (cy - 8) + '" width="6" height="16" rx="3" fill="' + INK + '" transform="rotate(-20 ' + cx + ' ' + cy + ')"/>';
      return '<rect class="sa-eye" x="' + (cx - 3.5) + '" y="' + (cy - 8) + '" width="7" height="16" rx="3.5" fill="' + INK + '"/>';
    }).join('');
  }

  // name, status -> standalone <svg> string (viewBox 0 0 100 100, transparent bg)
  function svg(name, status) {
    var d = describe(name, status);
    var empty = d.state === 'empty';
    var cls = 'subagent sa-' + d.state + (empty ? '' : ' sa-' + d.personality);
    var label = empty ? 'Sub-agent slot, empty' : 'Sub-agent ' + String(name).trim() + ', ' + d.state;
    var body = '<g class="sa-body">' + shapeSvg(d.shape, d.colour, empty) +
      (empty ? '<text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-size="34" font-family="system-ui,sans-serif" fill="#9aa0ad">?</text>' :
        '<g class="sa-eyes">' + eyesSvg(d.eyes, d.shape) + '</g>') + '</g>';
    var badge = empty ? '' :
      // light badge + dark ring + dark letter: reads on both light and dark pages
      '<circle cx="84" cy="16" r="11" fill="#ffffff" stroke="' + INK + '" stroke-width="2"/>' +
      '<text x="84" y="16.5" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="700" font-family="system-ui,sans-serif" fill="' + INK + '">' + d.letter + '</text>';
    return '<svg class="' + cls + '" viewBox="0 0 100 100" role="img" aria-label="' + label + '" xmlns="http://www.w3.org/2000/svg">' +
      body + badge + '</svg>';
  }

  var api = { SHAPES: SHAPES, COLOURS: COLOURS, EYES: EYES, PERSONALITY: PERSONALITY, fnv1a: fnv1a, describe: describe, svg: svg };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.Subagents = api;
})(typeof window !== 'undefined' ? window : globalThis);
