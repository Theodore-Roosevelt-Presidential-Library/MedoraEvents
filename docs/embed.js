/* Medora Events embed loader.
 *
 *   <div data-medora-events="upcoming" data-limit="5" data-source="trpl,nps"></div>
 *   <script src="https://medoraevents.labs.trlibrary.com/embed.js" async></script>
 *
 * data-medora-events: upcoming | browse | month | week. Any other data-* attribute is passed to the widget
 * (source, attendance, cost, kind, q, when, limit, more, recurring, filters, title, theme, bg, compact, date).
 */
(function () {
  "use strict";
  var me = document.currentScript || document.querySelector('script[src*="embed.js"]');
  var base = me ? me.src.replace(/embed\.js(\?.*)?$/, "") : "https://medoraevents.labs.trlibrary.com/";
  var n = 0, frames = {};

  function mount(el) {
    if (el.getAttribute("data-medora-events-mounted")) return;
    el.setAttribute("data-medora-events-mounted", "1");
    var view = el.getAttribute("data-medora-events") || "upcoming";
    var q = new URLSearchParams();
    Array.prototype.forEach.call(el.attributes, function (a) {
      if (a.name.indexOf("data-") === 0 && a.name !== "data-medora-events" && a.name !== "data-medora-events-mounted") q.set(a.name.slice(5), a.value);
    });
    var id = "medevents-" + (++n);
    q.set("frame", id);
    var f = document.createElement("iframe");
    f.src = base + "widgets/" + encodeURIComponent(view) + ".html?" + q.toString();
    f.title = view === "upcoming" ? "Upcoming events in Medora" : "Medora events calendar";
    f.loading = "lazy";
    f.style.cssText = "width:100%;border:0;display:block;overflow:hidden;height:" + (view === "upcoming" ? 520 : view === "browse" ? 900 : 760) + "px";
    f.setAttribute("scrolling", "no");
    el.appendChild(f);
    frames[id] = f;
  }

  window.addEventListener("message", function (ev) {
    var d = ev.data;
    if (!d || d.type !== "medevents:height" || !frames[d.frame]) return;
    if (base.indexOf(ev.origin) !== 0) return;
    frames[d.frame].style.height = Math.max(120, d.height) + "px";
  });

  function scan() { Array.prototype.forEach.call(document.querySelectorAll("[data-medora-events]"), mount); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan); else scan();
})();
