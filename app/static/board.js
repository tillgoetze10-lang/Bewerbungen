// Drag & Drop fuer das Kanban-Board. Faellt auf die normale <select> +
// Formular-Loesung zurueck (schon im HTML vorhanden), falls JS mal aus ist
// oder ein Request fehlschlaegt.
(function () {
  let dragged = null;

  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      dragged = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      dragged = null;
    });
  });

  document.querySelectorAll(".cards").forEach((columnEl) => {
    columnEl.addEventListener("dragover", (e) => {
      e.preventDefault();
      columnEl.classList.add("drag-over");
    });
    columnEl.addEventListener("dragleave", () => {
      columnEl.classList.remove("drag-over");
    });
    columnEl.addEventListener("drop", (e) => {
      e.preventDefault();
      columnEl.classList.remove("drag-over");
      if (!dragged) return;

      const fromColumn = dragged.closest(".cards");
      const newStatus = columnEl.dataset.status;
      const jobId = dragged.dataset.jobId;

      // Leere-Spalte-Hinweis entfernen, Karte optimistisch verschieben.
      const emptyHint = columnEl.querySelector(".empty");
      if (emptyHint) emptyHint.remove();
      columnEl.appendChild(dragged);
      updateCounts();

      // Status im Formular der Karte mitziehen, falls JS-Aufruf fehlschlaegt
      // und die Seite neu geladen wird, bleibt die Auswahl konsistent.
      const select = dragged.querySelector("select[name=status]");
      if (select) select.value = newStatus;

      fetch(`/job/${jobId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok && fromColumn) {
            // Server hat abgelehnt -> Karte zurueckschieben.
            fromColumn.appendChild(dragged);
            updateCounts();
          }
        })
        .catch(() => {
          // Netzwerkfehler: sicherheitshalber zurueckschieben und den
          // Nutzer nicht im Unklaren lassen.
          if (fromColumn) {
            fromColumn.appendChild(dragged);
            updateCounts();
          }
          alert("Verschieben fehlgeschlagen (Netzwerk). Bitte per Dropdown auf der Karte versuchen.");
        });
    });
  });

  function updateCounts() {
    document.querySelectorAll(".column").forEach((col) => {
      const count = col.querySelector(".cards").children.length;
      const badge = col.querySelector(".count");
      if (badge) badge.textContent = count;
    });
  }
})();
