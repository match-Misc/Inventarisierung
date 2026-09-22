(() => {
  const form = document.getElementById("chat-form");
  if (!form) return;
  const log = document.getElementById("chat-log");
  const input = document.getElementById("chat-question");
  const submit = document.getElementById("chat-submit");
  const storageKey = `inventar-chat-v1-${form.dataset.user}`;
  let messages = [];
  try {
    messages = JSON.parse(sessionStorage.getItem(storageKey) || "[]");
    if (!Array.isArray(messages)) messages = [];
  } catch (_) { messages = []; }

  function render() {
    log.replaceChildren();
    if (!messages.length) {
      const hint = document.createElement("p");
      hint.className = "text-muted";
      hint.textContent = "Wie kann ich dir bei der Geräteauswahl helfen?";
      log.append(hint);
    }
    for (const message of messages) {
      const bubble = document.createElement("div");
      bubble.className = `chat-message ${message.role === "user" ? "user" : "assistant"}`;
      bubble.textContent = message.content;
      log.append(bubble);
      if (message.role !== "assistant") continue;
      for (const card of message.cards || []) {
        const box = document.createElement("div");
        box.className = "chat-result";
        const title = document.createElement("a");
        title.href = card.detail_url;
        title.textContent = card.name;
        title.className = "fw-bold";
        box.append(title);
        const description = document.createElement("p");
        description.className = "mb-1";
        description.textContent = `${card.category} · ${card.status} · ${card.suitability}`;
        box.append(description);
        if (card.specification || card.proposal) {
          const spec = card.specification || card.proposal;
          const source = document.createElement("a");
          source.href = spec.source_url;
          source.target = "_blank";
          source.rel = "noopener noreferrer";
          source.textContent = `${card.specification ? "Geprüft" : "Noch ungeprüft"}: ${spec.value} (${spec.source_kind})`;
          box.append(source, document.createElement("br"));
        }
        if (card.bookable) {
          const book = document.createElement("a");
          book.href = card.booking_url;
          book.className = "btn btn-sm btn-outline-primary mt-2";
          book.textContent = "Buchung vorbereiten";
          box.append(book);
        }
        log.append(box);
      }
    }
    log.scrollTop = log.scrollHeight;
  }

  function save() {
    messages = messages.slice(-12);
    try { sessionStorage.setItem(storageKey, JSON.stringify(messages)); } catch (_) { /* Sitzung ohne Speicherung */ }
    render();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    const history = messages.slice(-4).map(({ role, content }) => ({ role, content }));
    messages.push({ role: "user", content: question });
    input.value = "";
    submit.disabled = true;
    save();
    try {
      const response = await fetch("/assistent/nachricht/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
        body: JSON.stringify({ question, history }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Die Suche ist fehlgeschlagen.");
      messages.push({ role: "assistant", content: result.answer, cards: result.cards });
    } catch (error) {
      messages.push({ role: "assistant", content: error.message || "Die Suche ist fehlgeschlagen." });
    } finally {
      submit.disabled = false;
      save();
      input.focus();
    }
  });
  render();
})();
