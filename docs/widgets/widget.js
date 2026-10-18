/* TR Events widgets: upcoming list, month calendar, week calendar.
 * Configure with URL parameters (or data- attributes on #tre-app):
 *   view=upcoming|browse|month|week|map   scope=medora|region (map)   source=trpl,nps   attendance=in_person,virtual,hybrid   cost=free,paid
 *   kind=event,tour,exhibition,program   q=keyword   limit=6   recurring=collapse|show|hide
 *   filters=1|0   more=link|button|scroll   when=week|month|3m   title=Heading   theme=light|dark|auto   bg=transparent   compact=1   link=URL   date=YYYY-MM-DD
 */
(function () {
  "use strict";
  var app = document.getElementById("tre-app");
  var P = new URLSearchParams(location.search);
  function opt(k, d) { var v = P.get(k); if (v === null && app.dataset[k] !== undefined) v = app.dataset[k]; return v === null || v === undefined || v === "" ? d : v; }
  function list(k) { var v = opt(k, ""); return v ? v.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : []; }

  var VIEW = opt("view", "upcoming");
  var LIST = VIEW === "upcoming" || VIEW === "browse";
  var API = opt("api", new URL("../api/v1/widget.json", location.href).href);
  var SITE = opt("link", new URL("../", location.href).href);
  var theme = opt("theme", "auto");
  if (theme !== "auto") document.documentElement.setAttribute("data-theme", theme);
  if (opt("bg", "") === "transparent") document.documentElement.setAttribute("data-bg", "transparent");

  var state = {
    sources: list("source"), attendance: list("attendance"), cost: list("cost"), kind: list("kind"), area: list("area"),
    q: opt("q", "").toLowerCase(), limit: parseInt(opt("limit", VIEW === "upcoming" ? "6" : VIEW === "browse" ? "10" : "500"), 10),
    recurring: opt("recurring", "hide"), when: opt("when", ""), pages: 1,
    more: opt("more", VIEW === "browse" ? "scroll" : "link"),   // link = "see all" link to the site; button = Show more; scroll = Show more + auto-load
    filters: opt("filters", VIEW === "upcoming" ? "0" : "1") === "1",
    cursor: null, data: null, narrow: false, openPop: false,
    scope: opt("scope", "medora"), place: null
  };
  if (VIEW === "map" && !opt("when", "")) state.when = "3m";
  var ATT = { in_person: "In person", virtual: "Virtual", hybrid: "Hybrid" };
  var COST = { free: "Free", paid: "Paid" };
  var ICON = {
    in_person: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 1a4.5 4.5 0 0 0-4.5 4.5C3.5 9 8 15 8 15s4.5-6 4.5-9.5A4.5 4.5 0 0 0 8 1Zm0 6.2A1.7 1.7 0 1 1 8 3.8a1.7 1.7 0 0 1 0 3.4Z"/></svg>',
    virtual: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M2 3h12v8H2zM1 12h14v1.5H1z"/><path fill="var(--bg)" d="M3.3 4.3h9.4v5.4H3.3z"/></svg>',
    hybrid: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M5 1a3.2 3.2 0 0 0-3.2 3.2C1.8 6.7 5 11 5 11s3.2-4.3 3.2-6.8A3.2 3.2 0 0 0 5 1Zm4 6h6v5H9zm-.5 6h7v1h-7z"/></svg>'
  };

  // ---------- dates ----------
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function ymd(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function parseYmd(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  var TODAY = ymd(new Date());
  function sDate(e) { return e.start.slice(0, 10); }
  function eDate(e) { return (e.end || e.start).slice(0, 10); }
  function spanDays(e) { return Math.round((parseYmd(eDate(e)) - parseYmd(sDate(e))) / 864e5); }
  function fmt(d, o) { return new Intl.DateTimeFormat("en-US", o).format(d); }
  function timeLabel(e) {
    if (e.all_day) return spanDays(e) > 0 ? "" : "All day";
    try {
      var o = { hour: "numeric", minute: "2-digit", timeZone: e.timezone };
      var a = fmt(new Date(e.start), o);
      var z = fmt(new Date(e.start), { timeZone: e.timezone, timeZoneName: "short" }).split(" ").pop();
      if (e.end && sDate(e) === eDate(e)) a += " – " + fmt(new Date(e.end), o);
      return (a + " " + z).replace(/:00/g, "");
    } catch (err) { return ""; }
  }
  function shortTime(e) {
    try {
      return fmt(new Date(e.start), { hour: "numeric", minute: "2-digit", timeZone: e.timezone })
        .replace(":00", "").replace(/\s?AM$/, "a").replace(/\s?PM$/, "p");
    } catch (err) { return ""; }
  }
  function dateLabel(e, long) {
    var a = parseYmd(sDate(e)), b = parseYmd(eDate(e));
    var o = long ? { weekday: "long", month: "long", day: "numeric", year: "numeric" } : { month: "short", day: "numeric" };
    if (sDate(e) === eDate(e)) return fmt(a, o);
    if (long) return fmt(a, { month: "long", day: "numeric" }) + " – " + fmt(b, { month: "long", day: "numeric", year: "numeric" });
    return fmt(a, { month: "short", day: "numeric" }) + " – " + fmt(b, o);
  }

  // ---------- data ----------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function srcName(id, short) {
    var s = (state.data.sources || []).filter(function (x) { return x.id === id; })[0];
    return s ? (short ? s.short || s.name : s.name) : id;
  }
  function matches(e) {
    if (e.kind === "closure") return false;
    if (state.sources.length && state.sources.indexOf(e.source) < 0) return false;
    if (state.attendance.length && state.attendance.indexOf(e.attendance) < 0) return false;
    if (state.cost.length && state.cost.indexOf(e.cost) < 0) return false;
    if (state.kind.length && state.kind.indexOf(e.kind) < 0) return false;
    if (state.area.length && state.area.indexOf(e.area) < 0) return false;
    if (state.recurring === "hide" && e.recurring && (e.kind === "tour" || e.kind === "program")) return false;
    if (state.q && (e.title + " " + (e.summary || "") + " " + (e.venue || "") + " " + (e.region_label || "") + " " + srcName(e.source)).toLowerCase().indexOf(state.q) < 0) return false;
    if (state.when && sDate(e) > whenEnd()) return false;
    return true;
  }
  function whenEnd() {
    var d = new Date();
    if (state.when === "week") d = addDays(d, 6 - d.getDay());
    else if (state.when === "month") d = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    else if (state.when === "3m") d = addDays(d, 90);
    else return "9999-12-31";
    return ymd(d);
  }
  function sortKey(e) { return (e.start.length > 10 ? new Date(e.start).toISOString() : e.start + "T00:00"); }
  function filtered() { return state.data.events.filter(matches); }

  // ---------- pieces ----------
  function badges(e) {
    var h = "";
    if (ATT[e.attendance]) h += '<span class="tre-badge b-' + e.attendance + '">' + ICON[e.attendance] + ATT[e.attendance] + "</span>";
    if (e.cost === "free") h += '<span class="tre-badge b-free">Free</span>';
    else if (e.cost === "paid") h += '<span class="tre-badge b-paid">' + (e.price_min ? "From $" + (+e.price_min).toFixed(e.price_min % 1 ? 2 : 0) : "Paid") + "</span>";
    if (e.status === "cancelled") h += '<span class="tre-badge b-status">Cancelled</span>';
    if (e.status === "sold_out") h += '<span class="tre-badge b-status">Sold out</span>';
    if (e.occurrences > 1) h += '<span class="tre-badge b-muted">' + e.occurrences + " dates</span>";
    return '<div class="tre-badges">' + h + "</div>";
  }
  function where(e) {
    if (e.attendance === "virtual") return "Online";
    var src = (state.data.sources || []).filter(function (x) { return x.id === e.source; })[0] || {};
    var v = e.venue && e.venue !== src.name && e.venue !== src.short ? e.venue : null;
    return [v, e.region_label].filter(Boolean).filter(function (x, i, a) { return a.indexOf(x) === i; }).join(" · ");
  }
  function filterBar() {
    if (!state.filters) return "";
    function chip(group, val, label) {
      var on = state[group].indexOf(val) >= 0;
      return '<button class="tre-chip" data-f="' + group + '" data-v="' + val + '" aria-pressed="' + on + '">' + label + "</button>";
    }
    var srcs = (state.data.sources || []).filter(function (s) { return state.data.events.some(function (e) { return e.source === s.id; }); });
    var pop = '<span class="tre-pop"><button class="tre-chip" data-pop="1" aria-expanded="' + state.openPop + '" aria-pressed="' + (state.sources.length > 0) + '">' +
      (state.sources.length ? state.sources.length + " organization" + (state.sources.length > 1 ? "s" : "") : "All organizations") + " ▾</button>";
    if (state.openPop) {
      pop += '<div class="tre-pop-panel" role="group" aria-label="Organizations">' + srcs.map(function (s) {
        return '<label><input type="checkbox" data-src="' + s.id + '"' + (state.sources.indexOf(s.id) >= 0 ? " checked" : "") + "> " + esc(s.name) + "</label>";
      }).join("") + "</div>";
    }
    pop += "</span>";
    var extra = "";
    if (VIEW === "browse" || VIEW === "map") {
      var whens = [["", "Any time"], ["week", "This week"], ["month", "This month"], ["3m", "Next 3 months"]];
      extra = '<div class="tre-filters tre-filters-top"><label class="tre-search"><span class="tre-vh">Search events</span>' +
        '<input type="search" id="tre-q" placeholder="Search events, places, organizations" value="' + esc(state.q) + '"></label>' +
        whens.map(function (w) { return '<button class="tre-chip" data-when="' + w[0] + '" aria-pressed="' + (state.when === w[0]) + '">' + w[1] + "</button>"; }).join("") + "</div>";
    }
    var active = state.sources.length + state.area.length + state.attendance.length + state.cost.length + (state.q ? 1 : 0) + (state.when ? 1 : 0) + (state.recurring !== "hide" ? 1 : 0);
    return extra + '<div class="tre-filters">' + pop + '<span class="tre-sep"></span>' +
      (VIEW === "map" ? "" : chip("area", "medora", "In Medora") + chip("area", "nearby", "Out of Medora") + '<span class="tre-sep"></span>') +
      '<span class="tre-sep"></span>' + chip("cost", "free", "Free") + chip("cost", "paid", "Paid") +
      '<span class="tre-sep"></span><button class="tre-chip" data-rec="1" aria-pressed="' + (state.recurring !== "hide") + '">Include daily activities</button>' +
      (VIEW === "browse" && active ? '<button class="tre-clear" data-clear="1">Clear filters</button>' : "") + "</div>";
  }
  function header(rangeLabel) {
    var t = opt("title", VIEW === "upcoming" ? "Upcoming in Medora" : VIEW === "browse" ? "Medora Events" : VIEW === "map" ? "Medora Events Map" : "Medora Events Calendar");
    var nav = LIST ? "" : VIEW === "map" ?
      '<div class="tre-seg" role="group" aria-label="Map area"><button class="tre-btn" data-scope="medora" aria-pressed="' + (state.scope === "medora") + '">Medora</button>' +
      '<button class="tre-btn" data-scope="region" aria-pressed="' + (state.scope === "region") + '">The region</button></div>' :
      '<div class="tre-nav"><button class="tre-btn tre-icon" data-nav="-1" aria-label="Previous">‹</button>' +
      '<div class="tre-range" aria-live="polite">' + esc(rangeLabel) + "</div>" +
      '<button class="tre-btn tre-icon" data-nav="1" aria-label="Next">›</button><button class="tre-btn" data-nav="0">Today</button></div>';
    return '<div class="tre-head"><div>' + (t === "none" ? "" : '<p class="tre-kicker">In and around Medora, North Dakota</p><h2 class="tre-title">' + esc(t) + "</h2>") + "</div>" + nav + "</div>";
  }
  function footer() {
    return '<div class="tre-foot"><span>Updated ' + fmt(new Date(state.data.generated), { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) +
      '</span><a href="' + esc(SITE) + '" target="_blank" rel="noopener">Medora Events · Theodore Roosevelt Presidential Library</a></div>';
  }

  // ---------- views ----------
  function collapse(evs) {
    var seen = {}, out = [];
    evs.forEach(function (e) {
      if (!e.recurring || state.recurring === "show") { out.push(e); return; }
      if (seen[e.series_id]) { seen[e.series_id].occurrences++; seen[e.series_id]._dates.push(e); return; }
      var c = Object.assign({}, e, { occurrences: 1, _dates: [e] }); seen[e.series_id] = c; out.push(c);
    });
    return out;
  }
  function renderUpcoming() {
    var evs = filtered().filter(function (e) { return eDate(e) >= TODAY; });
    evs.sort(function (a, b) {
      var ka = sDate(a) < TODAY ? TODAY : sDate(a), kb = sDate(b) < TODAY ? TODAY : sDate(b);
      return ka < kb ? -1 : ka > kb ? 1 : sortKey(a) < sortKey(b) ? -1 : 1;
    });
    evs = collapse(evs);
    var total = evs.length;
    evs = evs.slice(0, state.limit * (state.more === "link" ? 1 : state.pages));
    var h = header("") + filterBar();
    if (VIEW === "browse") h += '<p class="tre-count" aria-live="polite">' + (total ? "Showing " + evs.length + " of " + total + " upcoming event" + (total === 1 ? "" : "s") : "") + "</p>";
    if (!evs.length) h += '<div class="tre-empty">No upcoming events match these filters.' + (VIEW === "browse" ? ' <button class="tre-clear" data-clear="1">Clear filters</button>' : "") + "</div>";
    else {
      var lastMonth = "";
      h += '<ul class="tre-list' + (opt("compact", "0") === "1" ? " tre-compact" : "") + '">' + evs.map(function (e, i) {
        var mk = (sDate(e) < TODAY ? TODAY : sDate(e)).slice(0, 7), head = "";
        if (VIEW === "browse" && mk !== lastMonth) { lastMonth = mk; head = '<li class="tre-month-h" aria-hidden="false"><h4>' + fmt(parseYmd(mk + "-01"), { month: "long", year: "numeric" }) + "</h4></li>"; }
        var d = parseYmd(sDate(e) < TODAY ? TODAY : sDate(e)), now = sDate(e) < TODAY;
        var dateBlock = now ? '<div class="tre-date"><span class="m">Now</span><span class="d">' + fmt(d, { day: "numeric" }) + '</span><span class="w">thru ' + fmt(parseYmd(eDate(e)), { month: "short", day: "numeric" }) + "</span></div>"
          : '<div class="tre-date"><span class="m">' + fmt(d, { month: "short" }) + '</span><span class="d">' + fmt(d, { day: "numeric" }) + '</span><span class="w">' + fmt(d, { weekday: "short" }) + "</span></div>";
        var when = spanDays(e) > 0 ? dateLabel(e) : timeLabel(e);
        return head + '<li><button class="tre-card' + (e.image ? " has-img" : "") + '" data-i="' + i + '">' + dateBlock +
          "<div><h3>" + esc(e.title) + '</h3><div class="tre-meta"><strong>' + esc(when) + "</strong>" + (when && where(e) ? " · " : "") + esc(where(e)) +
          '</div><div class="tre-meta">' + esc(srcName(e.source, true)) + (e.drive_label ? ' · <span class="tre-drive">' + esc(e.drive_label) + "</span>" : "") + "</div>" + badges(e) + "</div>" +
          (e.image ? '<img src="' + esc(e.image) + '" alt="" loading="lazy">' : "") + "</button></li>";
      }).join("") + "</ul>";
      if (total > evs.length) {
        if (state.more === "link") h += '<p class="tre-more"><a href="' + esc(SITE) + '" target="_blank" rel="noopener">See all ' + total + " upcoming events →</a></p>";
        else h += '<div class="tre-loadmore"><button class="tre-btn" data-more="1">Show more events <span>(' + (total - evs.length) + " more)</span></button></div>";
      }
    }
    var qEl = document.getElementById("tre-q"), hadFocus = qEl && document.activeElement === qEl, caret = hadFocus ? qEl.selectionStart : 0;
    app.innerHTML = h + footer();
    app.querySelectorAll(".tre-card").forEach(function (b) { b.onclick = function () { openEvent(evs[+b.dataset.i]); }; });
    if (hadFocus) { qEl = document.getElementById("tre-q"); qEl.focus(); try { qEl.setSelectionRange(caret, caret); } catch (err) {} }
    watchMore();
  }

  function dayBuckets(from, to) {
    var buckets = {}, ongoing = [];
    filtered().forEach(function (e) {
      var s = sDate(e), t = eDate(e);
      if (t < from || s > to) return;
      if (spanDays(e) > 6) { ongoing.push(e); return; }
      for (var d = parseYmd(s < from ? from : s); ymd(d) <= (t > to ? to : t); d = addDays(d, 1)) {
        (buckets[ymd(d)] = buckets[ymd(d)] || []).push(e);
      }
    });
    Object.keys(buckets).forEach(function (k) { buckets[k].sort(function (a, b) { if (!!a.recurring !== !!b.recurring) return a.recurring ? 1 : -1; return a.all_day === b.all_day ? (sortKey(a) < sortKey(b) ? -1 : 1) : a.all_day ? -1 : 1; }); });
    return { buckets: buckets, ongoing: ongoing };
  }
  function evButton(e, cls) {
    var t = e.all_day ? "" : shortTime(e);
    return '<button class="' + cls + " k-" + e.kind + " a-" + e.attendance + '" data-id="' + e.id + '" title="' + esc(e.title) + '">' +
      (cls === "tre-wev" ? '<span class="t">' + esc(e.all_day ? (spanDays(e) ? dateLabel(e) : "All day") : timeLabel(e)) + "</span>" + esc(e.title) + '<span class="s">' + esc(srcName(e.source, true)) + (where(e) ? " · " + esc(where(e)) : "") + "</span>"
        : (t ? '<span class="t">' + esc(t) + "</span>" : "") + esc(e.title)) + "</button>";
  }
  function ongoingStrip(list) {
    if (!list.length) return "";
    return '<div class="tre-ongoing"><span>Ongoing</span>' + list.map(function (e) { return '<button data-id="' + e.id + '">' + esc(e.title) + " · thru " + fmt(parseYmd(eDate(e)), { month: "short", day: "numeric" }) + "</button>"; }).join("") + "</div>";
  }
  function agenda(from, to, buckets) {
    var keys = Object.keys(buckets).filter(function (k) { return k >= from && k <= to; }).sort();
    if (!keys.length) return '<div class="tre-empty">Nothing scheduled in this range.</div>';
    return '<div class="tre-agenda">' + keys.map(function (k) {
      return "<h4>" + fmt(parseYmd(k), { weekday: "short", month: "short", day: "numeric" }) + "</h4>" + buckets[k].map(function (e) { return evButton(e, "tre-wev"); }).join("");
    }).join("") + "</div>";
  }
  function renderMonth() {
    var c = state.cursor, first = new Date(c.getFullYear(), c.getMonth(), 1), last = new Date(c.getFullYear(), c.getMonth() + 1, 0);
    var gStart = addDays(first, -first.getDay()), gEnd = addDays(last, 6 - last.getDay());
    var b = dayBuckets(ymd(first), ymd(last));
    var h = header(fmt(first, { month: "long", year: "numeric" })) + filterBar() + ongoingStrip(b.ongoing);
    if (state.narrow) h += agenda(ymd(first), ymd(last), b.buckets);
    else {
      var bb = dayBuckets(ymd(gStart), ymd(gEnd)).buckets;
      h += '<div class="tre-month" role="grid">' + ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(function (d) { return '<div class="tre-dow" role="columnheader">' + d + "</div>"; }).join("");
      for (var d = gStart; d <= gEnd; d = addDays(d, 1)) {
        var k = ymd(d), evs = bb[k] || [], out = d.getMonth() !== c.getMonth();
        h += '<div class="tre-day' + (out ? " out" : "") + (k === TODAY ? " today" : "") + '" role="gridcell"><span class="n">' + d.getDate() + "</span>" +
          evs.slice(0, 3).map(function (e) { return evButton(e, "tre-ev"); }).join("") +
          (evs.length > 3 ? '<button class="more" data-day="' + k + '">+' + (evs.length - 3) + " more</button>" : "") + "</div>";
      }
      h += "</div>";
      state._bb = bb;
    }
    app.innerHTML = h + footer();
  }
  function renderWeek() {
    var s = addDays(state.cursor, -state.cursor.getDay()), e = addDays(s, 6);
    var b = dayBuckets(ymd(s), ymd(e));
    var label = fmt(s, { month: "short", day: "numeric" }) + " – " + fmt(e, s.getMonth() === e.getMonth() ? { day: "numeric" } : { month: "short", day: "numeric" });
    var h = header(label) + filterBar() + ongoingStrip(b.ongoing);
    if (state.narrow) h += agenda(ymd(s), ymd(e), b.buckets);
    else {
      h += '<div class="tre-week">';
      for (var d = s; d <= e; d = addDays(d, 1)) {
        var k = ymd(d), evs = b.buckets[k] || [];
        h += '<div class="tre-wday' + (k === TODAY ? " today" : "") + '"><h4>' + fmt(d, { weekday: "short" }) + " <small>" + fmt(d, { month: "short", day: "numeric" }) + "</small></h4>" +
          (evs.length ? evs.map(function (x) { return evButton(x, "tre-wev"); }).join("") : '<div class="none">—</div>') + "</div>";
      }
      h += "</div>";
    }
    app.innerHTML = h + footer();
  }


  // ---------- map ----------
  var L_CDN = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/";
  var mapObj = null, pinLayer = null, pinByKey = {}, lastScope = null, mapPlaces = [];
  function loadLeaflet(cb) {
    if (window.L) return cb();
    var css = document.createElement("link"); css.rel = "stylesheet"; css.href = L_CDN + "leaflet.min.css"; document.head.appendChild(css);
    var js = document.createElement("script"); js.src = L_CDN + "leaflet.min.js"; js.onload = cb;
    js.onerror = function () { app.innerHTML = '<div class="tre-empty">The map could not be loaded right now.</div>'; postHeight(); };
    document.head.appendChild(js);
  }
  function dark() { return document.documentElement.getAttribute("data-theme") === "dark" || (theme === "auto" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches); }
  function townOf(e) { return e.area === "medora" ? "Medora" : (e.region_label || "").split(",")[0] || "Elsewhere"; }
  function places() {
    var evs = filtered().filter(function (e) { return eDate(e) >= TODAY && e.attendance !== "virtual"; });
    if (state.scope === "medora") evs = evs.filter(function (e) { return e.area === "medora"; });
    evs.sort(function (a, b) { var ka = sDate(a) < TODAY ? TODAY : sDate(a), kb = sDate(b) < TODAY ? TODAY : sDate(b); return ka < kb ? -1 : ka > kb ? 1 : sortKey(a) < sortKey(b) ? -1 : 1; });
    var groups = {}, order = [], unplaced = 0;
    collapse(evs).forEach(function (e) {
      if (e.lat == null) { unplaced++; return; }
      var key = state.scope === "region" ? townOf(e) : (+e.lat).toFixed(4) + "," + (+e.lon).toFixed(4);
      var g = groups[key];
      if (!g) { g = groups[key] = { key: key, evs: [], lat: 0, lon: 0, names: {}, approx: true }; order.push(g); }
      g.evs.push(e); g.lat += +e.lat; g.lon += +e.lon;
      if (e.geo_precision === "venue") g.approx = false;
      var n = state.scope === "region" ? townOf(e) : (e.geo_precision === "town" ? null : e.venue);
      if (n) g.names[n] = (g.names[n] || 0) + 1;
    });
    order.forEach(function (g) {
      g.lat /= g.evs.length; g.lon /= g.evs.length;
      var best = Object.keys(g.names).sort(function (a, b) { return g.names[b] - g.names[a]; })[0];
      g.name = best || townOf(g.evs[0]);
      if (state.scope === "region") g.approx = false;   // town pins are meant to be towns
      g.sub = state.scope === "region" ? (g.key === "Medora" ? "Pick Medora above to see venues" : g.evs[0].drive_label || "")
        : (g.approx ? "In Medora; exact spot not listed" : "");
    });
    return { list: order, unplaced: unplaced };
  }
  function pinIcon(g, on) {
    var n = g.evs.length, sz = n > 20 ? 44 : n > 5 ? 36 : 30;
    return L.divIcon({ className: "", iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      html: '<span class="tre-pin' + (g.approx ? " approx" : "") + (on ? " on" : "") + '" style="width:' + sz + "px;height:" + sz + 'px">' + n + "</span>" });
  }
  function placeHtml(g) {
    var open = state.place === g.key, show = open ? g.evs.slice(0, 40) : g.evs.slice(0, 4);
    return '<section class="tre-place' + (open ? " on" : "") + '" data-place="' + esc(g.key) + '"><button class="tre-place-h" data-place="' + esc(g.key) + '"><span>' + esc(g.name) + "</span>" +
      '<em>' + g.evs.length + " event" + (g.evs.length === 1 ? "" : "s") + "</em></button>" + (g.sub ? '<p class="tre-place-s">' + esc(g.sub) + "</p>" : "") +
      show.map(function (e) {
        var d = sDate(e) < TODAY ? "Now" : fmt(parseYmd(sDate(e)), { month: "short", day: "numeric" });
        return '<button class="tre-place-ev" data-id="' + e.id + '"><span class="d">' + d + "</span><span>" + esc(e.title) +
          (e.occurrences > 1 ? ' <small>· ' + e.occurrences + " dates</small>" : "") + (state.scope === "region" && e.venue && e.venue !== g.name ? "<small>" + esc(e.venue) + "</small>" : "") + "</span></button>";
      }).join("") + (g.evs.length > show.length ? '<button class="tre-place-more" data-place="' + esc(g.key) + '">' + (open ? "" : "Show all " + g.evs.length) + "</button>" : "") + "</section>";
  }
  function renderMap() {
    if (!window.L) { app.innerHTML = '<div class="tre-loading">Loading map…</div>'; loadLeaflet(render); return; }
    var P = places(); mapPlaces = P.list;
    if (!app.querySelector(".tre-mapwrap")) {
      app.innerHTML = '<div class="tre-maptop"></div><div class="tre-mapwrap"><div class="tre-map" id="tre-map" role="region" aria-label="Map of events"></div><div class="tre-maplist" aria-live="polite"></div></div><div class="tre-mapnote"></div>' + footer();
      mapObj = L.map("tre-map", { scrollWheelZoom: false, zoomControl: true, attributionControl: true });
      L.tileLayer("https://{s}.basemaps.cartocdn.com/" + (dark() ? "dark_all" : "light_all") + "/{z}/{x}/{y}{r}.png", {
        maxZoom: 19, subdomains: "abcd", attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>' }).addTo(mapObj);
      mapObj.on("focus click", function () { mapObj.scrollWheelZoom.enable(); });
      mapObj.on("mouseout blur", function () { mapObj.scrollWheelZoom.disable(); });
      pinLayer = L.layerGroup().addTo(mapObj);
    }
    var qEl = document.getElementById("tre-q"), hadFocus = qEl && document.activeElement === qEl, caret = hadFocus ? qEl.selectionStart : 0;
    app.querySelector(".tre-maptop").innerHTML = header("") + filterBar();
    if (hadFocus) { qEl = document.getElementById("tre-q"); qEl.focus(); try { qEl.setSelectionRange(caret, caret); } catch (err) {} }
    pinLayer.clearLayers(); pinByKey = {};
    P.list.forEach(function (g) {
      var m = L.marker([g.lat, g.lon], { icon: pinIcon(g, state.place === g.key), title: g.name, keyboard: true, riseOnHover: true });
      m.on("click", function () { if (state.scope === "region" && g.key === "Medora") { setScope("medora"); return; } selectPlace(g.key, false); });
      m.addTo(pinLayer); pinByKey[g.key] = m;
    });
    var list = app.querySelector(".tre-maplist");
    list.innerHTML = P.list.length ? '<p class="tre-count">' + P.list.length + (state.scope === "region" ? " town" : " place") + (P.list.length === 1 ? "" : "s") + " · " +
      P.list.reduce(function (n, g) { return n + g.evs.length; }, 0) + " events</p>" + P.list.map(placeHtml).join("")
      : '<div class="tre-empty">No events on the map match these filters.</div>';
    var online = filtered().filter(function (e) { return eDate(e) >= TODAY && e.attendance === "virtual"; }).length;
    app.querySelector(".tre-mapnote").innerHTML = [
      state.scope === "medora" ? "Pins show event venues in Medora. Dashed pins mean the calendar didn't name a venue." : "Pins show towns; drive times are approximate, one way from Medora.",
      online ? online + " online event" + (online === 1 ? "" : "s") + " not shown." : "",
      P.unplaced ? P.unplaced + " event" + (P.unplaced === 1 ? "" : "s") + " without a location not shown." : ""].filter(Boolean).join(" ");
    if (lastScope !== state.scope) { lastScope = state.scope; fitPins(); }
    setTimeout(function () { mapObj.invalidateSize(); }, 0);
  }
  function fitPins() {
    var pts = mapPlaces.map(function (g) { return [g.lat, g.lon]; });
    if (state.scope === "medora") pts = pts.concat([[46.9139, -103.5244]]);
    if (!pts.length) { mapObj.setView([46.9139, -103.5244], state.scope === "medora" ? 15 : 8); return; }
    mapObj.fitBounds(L.latLngBounds(pts).pad(0.15), { maxZoom: state.scope === "medora" ? 16 : 10, animate: false });
  }
  function setScope(sc) { state.scope = sc; state.place = null; render(); }
  function selectPlace(key, fly) {
    state.place = state.place === key && !fly ? null : key;
    render();
    var g = mapPlaces.filter(function (x) { return x.key === key; })[0];
    if (fly && g) mapObj.flyTo([g.lat, g.lon], Math.max(mapObj.getZoom(), state.scope === "medora" ? 16 : 10), { duration: 0.5 });
    var sec = app.querySelector('.tre-place[data-place="' + (window.CSS && CSS.escape ? CSS.escape(key) : key) + '"]'), list = app.querySelector(".tre-maplist");
    if (sec && list) list.scrollTo({ top: sec.offsetTop - list.offsetTop - 8, behavior: "smooth" });
  }

  // ---------- modal ----------
  function byId(id) { return state.data.events.filter(function (e) { return e.id === id; })[0]; }
  function icsFor(e) {
    function z(s) { return new Date(s).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); }
    var L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TRPL//MedoraEvents//EN", "BEGIN:VEVENT", "UID:" + e.id + "@medoraevents.labs.trlibrary.com", "DTSTAMP:" + z(new Date().toISOString())];
    if (e.all_day) { L.push("DTSTART;VALUE=DATE:" + sDate(e).replace(/-/g, "")); L.push("DTEND;VALUE=DATE:" + ymd(addDays(parseYmd(eDate(e)), 1)).replace(/-/g, "")); }
    else { L.push("DTSTART:" + z(e.start)); L.push("DTEND:" + z(e.end || new Date(new Date(e.start).getTime() + 36e5).toISOString())); }
    function q(s) { return String(s || "").replace(/\\/g, "\\\\").replace(/([,;])/g, "\\$1").replace(/\n/g, "\\n"); }
    L.push("SUMMARY:" + q(e.title), "DESCRIPTION:" + q((e.summary || "") + "\n\n" + (e.url || "")), "LOCATION:" + q(where(e)), "URL:" + (e.url || ""), "END:VEVENT", "END:VCALENDAR");
    return "data:text/calendar;charset=utf-8," + encodeURIComponent(L.join("\r\n"));
  }
  function gcal(e) {
    function z(s) { return new Date(s).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); }
    var dates = e.all_day ? sDate(e).replace(/-/g, "") + "/" + ymd(addDays(parseYmd(eDate(e)), 1)).replace(/-/g, "")
      : z(e.start) + "/" + z(e.end || new Date(new Date(e.start).getTime() + 36e5).toISOString());
    return "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + encodeURIComponent(e.title) + "&dates=" + dates +
      "&details=" + encodeURIComponent((e.summary || "") + "\n\n" + (e.url || "")) + "&location=" + encodeURIComponent(where(e));
  }
  var lastFocus = null, lastClick = { el: null, y: null };
  // remember what was clicked (Safari doesn't focus buttons on click, so activeElement isn't enough)
  document.addEventListener("click", function (ev) {
    if (ev.target.closest && ev.target.closest(".tre-modal")) return;
    lastClick = { el: ev.target.closest ? ev.target.closest("button,a") : null, y: ev.clientY };
  }, true);
  function closeModal() {
    var m = document.querySelector(".tre-modal"); if (!m) return;
    m.remove(); document.body.style.minHeight = "";
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
    postHeight();
  }
  function modal(html) {
    var wasOpen = !!document.querySelector(".tre-modal"), keepTop = wasOpen ? document.querySelector(".tre-modal").style.paddingTop : null;
    closeModal();
    if (!wasOpen) lastFocus = (lastClick.el && document.contains(lastClick.el)) ? lastClick.el : document.activeElement;
    var m = document.createElement("div");
    m.className = "tre-modal"; m.innerHTML = '<div class="tre-dialog" role="dialog" aria-modal="true">' + html + "</div>";
    if (window.parent !== window) {  // inside an auto-height iframe: open the dialog right where the visitor clicked
      var top;
      if (keepTop) top = parseInt(keepTop, 10);
      else {
        var y = lastClick.y != null ? lastClick.y : (lastFocus && lastFocus.getBoundingClientRect ? lastFocus.getBoundingClientRect().top : 0);
        top = y + window.scrollY - 140;
      }
      m.classList.add("in-frame");
      m.style.paddingTop = Math.max(16, top) + "px";
    }
    m.onclick = function (ev) { if (ev.target === m || ev.target.closest(".tre-close")) closeModal(); var b = ev.target.closest("[data-id]"); if (b) openEvent(byId(b.dataset.id)); };
    document.body.appendChild(m);
    var c = m.querySelector(".tre-close"); if (c) c.focus({ preventScroll: true });
    document.body.style.minHeight = (m.querySelector(".tre-dialog").offsetHeight + (parseInt(m.style.paddingTop, 10) || 24) + 40) + "px";
    postHeight();
  }
  function openEvent(e) {
    if (!e) return;
    var dates = (e._dates || state.data.events.filter(function (x) { return x.series_id === e.series_id && x.recurring && eDate(x) >= TODAY; }));
    var rows = [
      ["When", dateLabel(e, true) + (e.times && e.times.length > 1 ? "<br>Start times: " + esc(e.times.join(", ")) : (timeLabel(e) ? "<br>" + esc(spanDays(e) > 0 ? "Starts " + timeLabel(e) : timeLabel(e)) : ""))],
      ["Where", esc(where(e) || "—") + (e.drive_label ? '<br><span class="tre-drive">' + esc(e.drive_label) + "</span>" : "")],
      ["Attend", ATT[e.attendance] || "Not stated"],
      ["Cost", (COST[e.cost] || "Not stated") + (e.price_min ? " · from $" + (+e.price_min).toFixed(e.price_min % 1 ? 2 : 0) : "") + (e.cost_note ? " · " + esc(e.cost_note) : "")]
    ];
    var h = (e.image ? '<img class="hero" src="' + esc(e.image) + '" alt="">' : "") + '<div class="body"><button class="tre-close" aria-label="Close">×</button>' +
      '<div class="src">' + esc(srcName(e.source)) + "</div><h2>" + esc(e.title) + "</h2>" + badges(e) +
      "<dl>" + rows.map(function (r) { return "<dt>" + r[0] + "</dt><dd>" + r[1] + "</dd>"; }).join("") + "</dl>" +
      (e.summary ? '<div class="desc">' + esc(e.summary) + "</div>" : "");
    if (e.recurring && dates.length > 1) {
      h += '<div class="tre-meta" style="margin-top:12px"><strong>Upcoming dates</strong></div><ul class="tre-dates">' + dates.slice(0, 24).map(function (x) {
        return "<li>" + fmt(parseYmd(sDate(x)), { weekday: "short", month: "short", day: "numeric" }) + (x.all_day ? "" : ", " + esc(timeLabel(x).split(" – ")[0])) + "</li>";
      }).join("") + (dates.length > 24 ? "<li>…and " + (dates.length - 24) + " more</li>" : "") + "</ul>";
    }
    h += '<div class="tre-actions">' + (e.url ? '<a class="tre-primary" href="' + esc(e.url) + '" target="_blank" rel="noopener">' + (e.registration_url && e.registration_url !== e.url ? "Event details" : "Details & tickets") + " ↗</a>" : "") +
      (e.registration_url && e.registration_url !== e.url ? '<a class="tre-primary" href="' + esc(e.registration_url) + '" target="_blank" rel="noopener">Register ↗</a>' : "") +
      '<a class="tre-secondary" href="' + icsFor(e) + '" download="' + esc(e.title.replace(/[^\w]+/g, "-").slice(0, 60)) + '.ics">Add to calendar</a>' +
      '<a class="tre-secondary" href="' + gcal(e) + '" target="_blank" rel="noopener">Google Calendar</a></div></div>';
    modal(h);
  }
  function openDay(k) {
    var evs = (state._bb || {})[k] || [];
    modal('<div class="body"><button class="tre-close" aria-label="Close">×</button><h2>' + fmt(parseYmd(k), { weekday: "long", month: "long", day: "numeric" }) + "</h2>" +
      evs.map(function (e) { return evButton(e, "tre-wev"); }).join("") + "</div>");
  }

  // ---------- wiring ----------
  function render() {
    if (VIEW === "month") renderMonth(); else if (VIEW === "week") renderWeek(); else if (VIEW === "map") renderMap(); else renderUpcoming();
    postHeight();
  }
  app.addEventListener("click", function (ev) {
    var t = ev.target.closest("button,input"); if (!t) return;
    if (t.dataset.nav !== undefined) {
      var n = +t.dataset.nav;
      if (n === 0) state.cursor = new Date();
      else if (VIEW === "month") state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() + n, 1);
      else state.cursor = addDays(state.cursor, 7 * n);
      render(); return;
    }
    if (t.dataset.scope) { setScope(t.dataset.scope); return; }
    if (t.dataset.place !== undefined) { selectPlace(t.dataset.place, t.classList.contains("tre-place-h")); return; }
    if (t.dataset.more) { state.pages++; render(); return; }
    if (t.dataset.when !== undefined) { state.when = t.dataset.when; state.pages = 1; render(); return; }
    if (t.dataset.clear) { state.sources = []; state.area = []; state.attendance = []; state.cost = []; state.q = ""; state.when = ""; state.recurring = "hide"; state.pages = 1; state.openPop = false; render(); return; }
    if (t.dataset.f) { var g = state[t.dataset.f], i = g.indexOf(t.dataset.v); if (i >= 0) g.splice(i, 1); else g.push(t.dataset.v); state.pages = 1; render(); return; }
    if (t.dataset.rec) { state.pages = 1; state.recurring = state.recurring === "hide" ? (VIEW === "upcoming" ? "collapse" : "show") : "hide"; render(); return; }
    if (t.dataset.pop) { state.openPop = !state.openPop; render(); return; }
    if (t.dataset.src) { state.pages = 1; var j = state.sources.indexOf(t.dataset.src); if (t.checked && j < 0) state.sources.push(t.dataset.src); if (!t.checked && j >= 0) state.sources.splice(j, 1); render(); return; }
    if (t.dataset.day) { openDay(t.dataset.day); return; }
    if (t.dataset.id) { openEvent(byId(t.dataset.id)); }
  });
  var qTimer;
  app.addEventListener("input", function (ev) {
    if (ev.target.id !== "tre-q") return;
    clearTimeout(qTimer);
    qTimer = setTimeout(function () { state.q = ev.target.value.trim().toLowerCase(); state.pages = 1; render(); }, 180);
  });
  // progressive loading: when the "Show more" button scrolls into view (in the page that embeds the iframe), load the next page
  var moreObs = null, moreBusy = false;
  function watchMore() {
    if (moreObs) moreObs.disconnect();
    if (state.more !== "scroll" || !window.IntersectionObserver) return;
    var b = app.querySelector("[data-more]");
    if (!b) return;
    moreObs = new IntersectionObserver(function (es) {
      if (!es[0].isIntersecting || moreBusy) return;
      moreBusy = true;
      setTimeout(function () { state.pages++; render(); moreBusy = false; }, 250);
    }, { rootMargin: "0px 0px 200px 0px" });
    moreObs.observe(b);
  }
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { if (document.querySelector(".tre-modal")) closeModal(); else if (state.openPop) { state.openPop = false; render(); } } });

  var frameId = opt("frame", "");
  function postHeight() {
    if (window.parent === window) return;
    var h = Math.ceil(document.body.getBoundingClientRect().height) + 2;
    window.parent.postMessage({ type: "medevents:height", frame: frameId, height: h }, "*");
  }
  function measure() {
    var narrow = app.clientWidth < 640;
    if (narrow !== state.narrow) { state.narrow = narrow; if (state.data) render(); }
    postHeight();
  }
  if (window.ResizeObserver) new ResizeObserver(measure).observe(document.body); else window.addEventListener("resize", measure);

  var start = opt("date", "");
  state.cursor = start ? parseYmd(start.length === 7 ? start + "-01" : start) : new Date();
  state.narrow = app.clientWidth < 640;
  app.innerHTML = '<div class="tre-loading">Loading events…</div>';
  fetch(API, { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (d) {
    state.data = d;
    d.events.sort(function (a, b) { return sortKey(a) < sortKey(b) ? -1 : 1; });
    render();
  }).catch(function () { app.innerHTML = '<div class="tre-empty">Events could not be loaded right now.</div>'; postHeight(); });
})();
