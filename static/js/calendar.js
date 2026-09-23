/* Buchungskalender: FullCalendar-Ansicht mit Filtern und HTMX-Modal für Buchung/Details. */
(() => {
  "use strict";

  const el = document.getElementById("calendar");
  if (!el) return;
  const urls = window.CALENDAR_URLS;

  const modalEl = document.getElementById("loans-modal");
  const modal = new bootstrap.Modal(modalEl);
  const modalContent = modalEl.querySelector(".modal-content");
  const filterForm = document.getElementById("calendar-filters");
  const deviceSelect = document.getElementById("filter-geraet");
  const unavailableHint = document.getElementById("unavailable-hint");

  function filterParams() {
    return Object.fromEntries(new FormData(filterForm).entries());
  }

  function selectedDeviceReason() {
    const option = deviceSelect.options[deviceSelect.selectedIndex];
    return option ? option.dataset.reason || null : null;
  }

  function updateUnavailableHint() {
    const reason = selectedDeviceReason();
    if (reason) {
      unavailableHint.textContent = `Dieses Gerät ist derzeit nicht verfügbar (${reason}) und kann nicht gebucht werden.`;
      unavailableHint.classList.remove("d-none");
    } else {
      unavailableHint.classList.add("d-none");
    }
  }

  function openModal(url) {
    htmx.ajax("GET", url, { target: modalContent, swap: "innerHTML" });
    modal.show();
  }

  const calendar = new FullCalendar.Calendar(el, {
    locale: "de",
    firstDay: 1,
    initialView: "dayGridMonth",
    height: "auto",
    selectable: true,
    selectMirror: true,
    headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,listMonth" },
    events(info, success, failure) {
      const params = new URLSearchParams({ start: info.startStr, end: info.endStr, ...filterParams() });
      fetch(`${urls.events}?${params}`)
        .then((response) => response.json())
        .then(success)
        .catch(failure);
    },
    eventClick(info) {
      openModal(urls.bookingDetail.replace("/0/", `/${info.event.id}/`));
    },
    select(info) {
      if (selectedDeviceReason()) {
        calendar.unselect();
        return;
      }
      const end = new Date(info.end);
      end.setDate(end.getDate() - 1); // FullCalendar liefert das Ende exklusiv, die Buchung endet am Vortag.
      const params = new URLSearchParams({ start: info.startStr.slice(0, 10), end: end.toISOString().slice(0, 10) });
      if (deviceSelect.value) params.set("geraet", deviceSelect.value);
      openModal(`${urls.bookingCreate}?${params}`);
      calendar.unselect();
    },
  });
  calendar.render();

  filterForm.addEventListener("change", () => {
    updateUnavailableHint();
    calendar.refetchEvents();
  });
  updateUnavailableHint();

  document.getElementById("btn-new-booking")?.addEventListener("click", () => {
    if (selectedDeviceReason()) return;
    const params = deviceSelect.value ? `?geraet=${deviceSelect.value}` : "";
    openModal(`${urls.bookingCreate}${params}`);
  });

  // Verfügbarkeits-Hinweis im Buchungsformular selbst (deaktivierte Option gewählt).
  function updateItemAvailabilityHint() {
    const select = modalContent.querySelector('select[name="item"]');
    const hint = modalContent.querySelector("#item-availability-hint");
    if (!select || !hint) return;
    const option = select.options[select.selectedIndex];
    if (option && option.disabled) {
      hint.textContent = option.textContent;
      hint.classList.remove("d-none");
    } else {
      hint.classList.add("d-none");
    }
  }

  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target !== modalContent) return;
    const select = modalContent.querySelector('select[name="item"]');
    select?.addEventListener("change", updateItemAvailabilityHint);
    updateItemAvailabilityHint();
  });

  document.body.addEventListener("booking-saved", () => {
    modal.hide();
    calendar.refetchEvents();
  });
})();
