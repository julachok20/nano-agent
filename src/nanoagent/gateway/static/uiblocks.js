/* nano Agent generative UI renderer (v0.2). Schema and limits: team-assets/plans/v0.2-addendum.md, section 1.
 * Safe blocks only: text, steps, comparison, chart, stat, checklist, timeline. No html block, no links, no images.
 * Model output is untrusted data: strict JSON parse, one fixed component per type, every string set with textContent.
 * Model answers are parsed with { trusted: false }, which drops chart and stat blocks (O3: the app computes those numbers).
 * Unknown types, extra fields and out-of-range values drop that block only. Over 20 blocks or 40 KB rejects the whole answer. */
(function (root) {
  "use strict";
  var MAX_BLOCKS = 20, MAX_BYTES = 40000, SUPPORTED_V = 1;
  var TRUSTED_ONLY = ["chart", "stat"];

  function isStr(x, max) { return typeof x === "string" && x.length <= max; }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function arrOf(x, max) { return Array.isArray(x) && x.length <= max ? x : null; }
  function onlyKeys(o, keys) { return Object.keys(o).every(function (k) { return keys.indexOf(k) !== -1; }); }
  function isObj(x) { return x !== null && typeof x === "object" && !Array.isArray(x); }

  var CHECK = {
    text: function (b) { return onlyKeys(b, ["type", "body"]) && isStr(b.body, 2000); },
    steps: function (b) {
      var items = arrOf(b.items, 12);
      return onlyKeys(b, ["type", "items"]) && !!items && items.every(function (x) {
        return isObj(x) && onlyKeys(x, ["title", "detail"]) && isStr(x.title, 120) && (x.detail === undefined || isStr(x.detail, 300));
      });
    },
    comparison: function (b) {
      var cols = arrOf(b.columns, 4), rows = arrOf(b.rows, 12);
      return onlyKeys(b, ["type", "columns", "rows"]) && !!cols && !!rows && cols.every(function (c) { return isStr(c, 60); }) &&
        rows.every(function (r) {
          return isObj(r) && onlyKeys(r, ["label", "values"]) && isStr(r.label, 60) && !!arrOf(r.values, 4) &&
            r.values.every(function (v) { return isStr(v, 120); });
        });
    },
    chart: function (b) {
      var labels = arrOf(b.labels, 24), series = arrOf(b.series, 4);
      return onlyKeys(b, ["type", "kind", "labels", "series"]) && ["bar", "line", "pie"].indexOf(b.kind) !== -1 && !!labels &&
        labels.every(function (l) { return isStr(l, 60); }) && !!series && series.every(function (s) {
          return isObj(s) && onlyKeys(s, ["name", "values"]) && isStr(s.name, 60) && !!arrOf(s.values, 24) &&
            s.values.length === labels.length && s.values.every(isNum);
        });
    },
    stat: function (b) {
      return onlyKeys(b, ["type", "label", "value", "delta", "unit"]) && isStr(b.label, 60) && isStr(b.value, 40) &&
        (b.delta === undefined || isNum(b.delta)) && (b.unit === undefined || isStr(b.unit, 12));
    },
    checklist: function (b) {
      var items = arrOf(b.items, 20);
      return onlyKeys(b, ["type", "items"]) && !!items && items.every(function (x) {
        return isObj(x) && onlyKeys(x, ["text", "done"]) && isStr(x.text, 200) && typeof x.done === "boolean";
      });
    },
    timeline: function (b) {
      var items = arrOf(b.items, 20);
      return onlyKeys(b, ["type", "items"]) && !!items && items.every(function (x) {
        return isObj(x) && onlyKeys(x, ["when", "text"]) && isStr(x.when, 40) && isStr(x.text, 300);
      });
    }
  };

  // Returns { blocks, dropped } or null when the whole answer is rejected.
  function parse(src, opts) {
    var trusted = !!(opts && opts.trusted);
    if (typeof src !== "string" || src.length > MAX_BYTES) return null;
    var obj;
    try { obj = JSON.parse(src); } catch (e) { return null; }
    if (!isObj(obj) || !Array.isArray(obj.blocks) || obj.blocks.length > MAX_BLOCKS) return null;
    var textOnly = typeof obj.v === "number" && obj.v > SUPPORTED_V;   // newer schema: show text blocks only
    var kept = [], dropped = 0;
    obj.blocks.forEach(function (b) {
      var type = isObj(b) && typeof b.type === "string" ? b.type : "";
      var known = Object.prototype.hasOwnProperty.call(CHECK, type);
      var allowed = known && (!textOnly || type === "text") && (trusted || TRUSTED_ONLY.indexOf(type) === -1);
      if (allowed && CHECK[type](b)) kept.push(b); else dropped++;
    });
    return { blocks: kept, dropped: dropped };
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderBlock(b) {
    switch (b.type) {
      case "text": return el("p", "ui-text", b.body);
      case "steps": {
        var ol = el("ol", "ui-steps");
        b.items.forEach(function (x) {
          var li = el("li");
          li.appendChild(el("strong", null, x.title));
          if (x.detail) li.appendChild(el("span", "ui-detail", x.detail));
          ol.appendChild(li);
        });
        return ol;
      }
      case "comparison": {
        var table = el("table", "ui-table"), thead = el("thead"), hr = el("tr");
        hr.appendChild(el("th"));
        b.columns.forEach(function (c) { hr.appendChild(el("th", null, c)); });
        thead.appendChild(hr); table.appendChild(thead);
        var tbody = el("tbody");
        b.rows.forEach(function (r) {
          var tr = el("tr");
          tr.appendChild(el("th", null, r.label));
          r.values.forEach(function (v) { tr.appendChild(el("td", null, v)); });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        return table;
      }
      case "chart": {
        // Bars for every kind in v0.2 (line and pie are shown as bars). Widths are computed from finite numbers only.
        var wrap = el("div", "ui-chart"), s0 = b.series[0] || { values: [] };
        var max = Math.max.apply(null, [1].concat(s0.values.map(Math.abs)));
        b.labels.forEach(function (lab, i) {
          var row = el("div", "ui-bar-row");
          row.appendChild(el("span", "ui-bar-label", lab));
          var bar = el("span", "ui-bar");
          bar.style.width = Math.max(0, Math.round(100 * Math.abs(s0.values[i]) / max)) + "%";
          row.appendChild(bar);
          row.appendChild(el("span", "ui-bar-value", String(s0.values[i])));
          wrap.appendChild(row);
        });
        return wrap;
      }
      case "stat": {
        var tile = el("div", "ui-stat");
        tile.appendChild(el("small", null, b.label));
        tile.appendChild(el("strong", null, b.value + (b.unit ? " " + b.unit : "")));
        if (b.delta !== undefined) tile.appendChild(el("span", b.delta < 0 ? "ui-delta down" : "ui-delta up", (b.delta > 0 ? "+" : "") + b.delta));
        return tile;
      }
      case "checklist": {
        var ul = el("ul", "ui-checklist");
        b.items.forEach(function (x) {
          var li = el("li");
          var box = el("input"); box.type = "checkbox"; box.checked = x.done; box.disabled = true;   // read-only in v0.2
          li.appendChild(box); li.appendChild(el("span", x.done ? "done" : null, x.text));
          ul.appendChild(li);
        });
        return ul;
      }
      case "timeline": {
        var tl = el("ol", "ui-timeline");
        b.items.forEach(function (x) {
          var li = el("li");
          li.appendChild(el("small", null, x.when));
          li.appendChild(el("span", null, x.text));
          tl.appendChild(li);
        });
        return tl;
      }
    }
    return el("p", "ui-text");
  }

  // opts.note: text shown under an answer when some blocks were dropped.
  function render(ans, opts) {
    var wrap = el("div", "ui-answer");
    ans.blocks.forEach(function (b) { wrap.appendChild(renderBlock(b)); });
    if (ans.dropped && opts && opts.note) wrap.appendChild(el("p", "ui-note", opts.note));
    return wrap;
  }

  root.UIBlocks = { parse: parse, render: render, LIMITS: { MAX_BLOCKS: MAX_BLOCKS, MAX_BYTES: MAX_BYTES, SUPPORTED_V: SUPPORTED_V } };
})(window);
