// Drag & Drop fuer das Board. Faellt auf das Dropdown auf jeder Karte zurueck,
// wenn ein Request fehlschlaegt.
(function () {
  let dragged = null;
  let origin = null;

  function updateColumn(column) {
    const visible = column.querySelectorAll(":scope > .cards > .card").length;
    const badge = column.querySelector(".count");
    if (badge) badge.textContent = visible;
    const empty = column.querySelector(":scope > .cards > .empty");
    if (empty) empty.classList.toggle("hidden", visible > 0);
  }

  function updateAll() {
    document.querySelectorAll(".column").forEach(updateColumn);
  }

  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      dragged = card;
      origin = card.parentElement;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", card.dataset.jobId);
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      document.querySelectorAll(".cards.drag-over").forEach((c) => c.classList.remove("drag-over"));
    });
  });

  document.querySelectorAll(".column > .cards").forEach((target) => {
    target.addEventListener("dragover", (e) => {
      e.preventDefault();
      target.classList.add("drag-over");
    });
    target.addEventListener("dragleave", (e) => {
      if (!target.contains(e.relatedTarget)) target.classList.remove("drag-over");
    });
    target.addEventListener("drop", (e) => {
      e.preventDefault();
      target.classList.remove("drag-over");
      if (!dragged || target === origin) return;

      const card = dragged;
      const from = origin;
      const newStatus = target.dataset.status;
      target.insertBefore(card, target.querySelector(".empty"));
      const select = card.querySelector("select[name=status]");
      if (select) select.value = newStatus;
      updateAll();

      fetch(`/job/${card.dataset.jobId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      })
        .then((r) => r.json())
        .then((data) => { if (!data.ok) throw new Error("abgelehnt"); })
        .catch(() => {
          from.insertBefore(card, from.querySelector(".empty"));
          updateAll();
          alert("Verschieben hat nicht geklappt. Bitte das Auswahlfeld auf der Karte benutzen.");
        });
    });
  });

  // "Löschen" ohne Seiten-Neuladen: Karte ausblenden, Archiv-Zaehler bleibt beim naechsten Laden aktuell.
  document.querySelectorAll("form.js-archive").forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const card = form.closest(".card");
      fetch(form.action, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then((r) => { if (!r.ok) throw new Error(); card.classList.add("removing"); setTimeout(() => { card.remove(); updateAll(); }, 180); })
        .catch(() => form.submit());
    });
  });
})();
