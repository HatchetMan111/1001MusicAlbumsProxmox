/* AlbumsDashboard – Progressive Enhancement.
 * Ohne JavaScript funktioniert alles ueber die klassischen Formulare weiter.
 * Mit JavaScript: Autosave ohne Reload (Scroll-Position bleibt erhalten),
 * Auto-Submit der Filter-Dropdowns und " Suche per Enter" (Standard). */
(function () {
  "use strict";

  var SAVE_DEBOUNCE_MS = 600;

  function setStatus(el, text, ok) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove("ok", "error");
    if (ok !== undefined) el.classList.add(ok ? "ok" : "error");
  }

  function saveForm(form) {
    var statusEl = form.querySelector(".save-status");
    setStatus(statusEl, "Speichert…");

    var data = new URLSearchParams(new FormData(form));
    fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        setStatus(statusEl, "Gespeichert ✓", true);
      })
      .catch(function () {
        setStatus(statusEl, "Fehler – bitte erneut speichern", false);
      });
  }

  var timers = new WeakMap();

  /* Autosave: Checkbox und Bewertung sofort, Notiz entprellt. */
  document.querySelectorAll("form[data-autosave]").forEach(function (form) {
    form.addEventListener("change", function (ev) {
      if (ev.target.name === "listened" || ev.target.name === "rating") {
        saveForm(form);
      } else if (ev.target.name === "note") {
        clearTimeout(timers.get(form));
        timers.set(form, setTimeout(function () { saveForm(form); }, SAVE_DEBOUNCE_MS));
      }
    });
    /* Klassischer Submit (Enter im Notiz-Feld) abfangen, kein Reload noetig. */
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      saveForm(form);
    });
  });

  /* Filter-Dropdowns: sofort absenden statt Klick auf "Filtern". */
  document.querySelectorAll("select[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      sel.closest("form").submit();
    });
  });

  /* Nach dem normalen Redirect-Anker (#album-…) die Karte kurz aufleuchten lassen. */
  if (location.hash) {
    var target = document.querySelector(location.hash);
    if (target && target.classList.contains("album-card")) {
      target.classList.add("flash");
      setTimeout(function () { target.classList.remove("flash"); }, 1500);
    }
  }
})();
