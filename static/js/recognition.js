(() => {
  const form = document.getElementById("recognition-form");
  if (!form || !window.fetch || !window.ReadableStream) return;

  const progress = document.getElementById("recognition-progress");
  const current = document.getElementById("recognition-current");
  const steps = document.getElementById("recognition-steps");
  const errorBox = document.getElementById("recognition-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    progress.hidden = false;
    errorBox.hidden = true;
    steps.replaceChildren();
    current.textContent = "Foto wird hochgeladen und vorbereitet.";
    let completed = false;
    let activeStep = current.textContent;

    function handleLine(line) {
      if (!line.trim()) return;
      const update = JSON.parse(line);
      if (update.type === "stage") {
        const entry = document.createElement("li");
        entry.textContent = activeStep;
        steps.append(entry);
        activeStep = update.text;
        current.textContent = activeStep;
      } else if (update.type === "result") {
        completed = true;
        document.open();
        document.write(update.html);
        document.close();
      }
    }

    try {
      const response = await fetch(form.action || window.location.href, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Recognition-Stream": "1" },
      });
      if (!response.ok) {
        if (response.status === 400) {
          const data = await response.json();
          const messages = Object.values(data.errors || {}).flat().map((error) => error.message);
          throw new Error(messages.join(" ") || "Bitte Eingaben prüfen.");
        }
        throw new Error("Der Server konnte die Anfrage nicht verarbeiten.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      while (true) {
        const { value, done } = await reader.read();
        pending += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = pending.split("\n");
        pending = lines.pop();
        for (const line of lines) handleLine(line);
        if (done) break;
      }
      if (pending) handleLine(pending);
      if (!completed) throw new Error("Die Erkennung wurde ohne Vorschlag beendet.");
    } catch (error) {
      if (completed) return;
      errorBox.textContent = error.message || "Die Verbindung wurde unterbrochen. Bitte erneut versuchen.";
      errorBox.hidden = false;
      progress.hidden = true;
      button.disabled = false;
    }
  });
})();
