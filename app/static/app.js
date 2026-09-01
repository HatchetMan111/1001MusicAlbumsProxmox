/* AlbumsDashboard – Progressive Enhancement.
 * Ohne JavaScript funktionieren alle Formulare weiterhin klassisch.
 * Mit JavaScript: Autosave via JSON-API ohne Reload; die Antwort enthaelt
 * den TATSAECHLICHEN DB-Stand, mit dem die Karte sofort synchronisiert
 * wird (inkl. Statistik-Leiste und Gehört-Datum). */
(function () {
  "use strict";

  var SAVE_DEBOUNCE_MS = 600;

  function setStatus(el, text, ok) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove("ok", "error");
    if (ok !== undefined) el.classList.add(ok ? "ok" : "error");
  }

  function applyCard(card, data) {
    /* Karte an den tatsaechlichen DB-Stand angleichen. */
    card.classList.toggle("is-listened", !!data.listened);

    var stars = card.querySelector(".stars");
    if (stars) {
      stars.hidden = !data.rating;
      stars.setAttribute("aria-label", "Bewertung: " + (data.rating || 0) + " von 5 Sternen");
      stars.querySelectorAll("span[class]").forEach(function (s) {
        var idx = parseInt(s.getAttribute("data-star"), 10);
        s.className = data.rating && idx <= data.rating ? "star-filled" : "star-empty";
      });
    }

    var dateEl = card.querySelector(".listened-date");
    if (dateEl) {
      if (data.listened && data.listened_on) {
        dateEl.hidden = false;
        dateEl.textContent = data.listened_on.slice(0, 10);
        dateEl.setAttribute("title", "Gehört am " + data.listened_on);
      } else {
        dateEl.hidden = true;
      }
    }

    /* Formular-Elemente auf Server-Stand halten (verhindert drift). */
    var cb = card.querySelector('input[name="listened"]');
    if (cb) cb.checked = !!data.listened;
    var sel = card.querySelector('select[name="rating"]');
    if (sel) sel.value = data.rating ? String(data.rating) : "";
    var note = card.querySelector('input[name="note"]');
    if (note) note.value = data.note || "";
  }

  function applyStats(data) {
    if (!data) return;
    var listened = document.getElementById("stat-listened");
    var percent = document.getElementById("stat-percent");
    var fill = document.getElementById("progress-fill");
    if (listened) listened.textContent = data.listened;
    if (percent) percent.textContent = data.percent + " %";
    if (fill) fill.style.width = data.percent + "%";
  }

  function saveForm(form) {
    var statusEl = form.querySelector(".save-status");
    var card = form.closest(".album-card");
    setStatus(statusEl, "Speichert…");

    var data = new URLSearchParams(new FormData(form));
    /* Wichtig: eine abgehakte Checkbox wird vom Browser GAR NICHT gesendet.
     * URLSearchParams(new FormData(form)) enthaelt 'listened' dann nicht,
     * und der Server wuerde 'nicht gehört' annehmen. Deshalb explizit
     * setzen: 'on' wenn angehakt, sonst '' (leer = nicht gehört). */
    if (!data.has("listened")) {
      data.set("listened", form.querySelector('input[name="listened"]').checked ? "on" : "");
    }

    fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (payload) {
        /* Nur mit der Server-Bestaetigung (echter DB-Stand) UI updaten:
         * 'Gespeichert' ist erst WAHR, wenn der Server es zurueckmeldet. */
        applyCard(card, payload);
        applyStats(payload.stats);
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
    /* Klassischer Submit (Enter im Notiz-Feld) abfangen, kein Reload nötig. */
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
