// Kleine Helfer der Webseite. Kein Tracking, keine Cookies.
(function () {
  // Kaffee-Link aus einstellungen.js
  var url = window.KAFFEE_URL;
  if (url) {
    var a = document.getElementById("kaffee");
    a.href = url;
    a.hidden = false;
    document.getElementById("kaffee-trenner").hidden = false;
  }

  // Aktuelle Version und Datum von GitHub. Schlägt das fehl, bleibt der Text, wie er ist.
  var zeile = document.getElementById("version");
  if (!zeile || !window.fetch) return;
  fetch("https://api.github.com/repos/DMNT-Studio/DMNT-Kobold/releases/latest",
        { headers: { "Accept": "application/vnd.github+json" } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (rel) {
      if (!rel || !rel.tag_name) return;
      var datum = rel.published_at ? new Date(rel.published_at).toLocaleDateString("de-DE") : "";
      zeile.textContent = "Version " + rel.tag_name.replace(/^v/, "") + (datum ? " vom " + datum : "") +
        " · Windows 10 und 11 · kostenlos · ohne Admin-Rechte";
    })
    .catch(function () {});
})();
