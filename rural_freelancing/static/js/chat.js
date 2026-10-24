// Simple chat: polls the server every 3 seconds for new messages.
(function () {
  const box = document.getElementById("chatBox");
  if (!box) return;
  const bid = box.dataset.booking;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  let last = parseInt(box.dataset.last || "0", 10);

  function add(m, me) {
    const d = document.createElement("div");
    if (m.sender_id === null) { d.className = "msg sys"; d.textContent = m.body; }
    else {
      d.className = "msg" + (m.sender_id === me ? " me" : "");
      const s = document.createElement("small"); s.textContent = m.name + " \u00B7 " + m.t;
      const t = document.createElement("span"); t.textContent = m.body;   // textContent = safe from XSS
      d.append(s, t);
    }
    box.appendChild(d); last = m.id;
  }
  async function poll() {
    try {
      const r = await fetch(`/booking/${bid}/messages?after=${last}`);
      const data = await r.json();
      if (data.messages.length) { data.messages.forEach((m) => add(m, data.me)); box.scrollTop = box.scrollHeight; }
    } catch (e) {}
  }
  box.scrollTop = box.scrollHeight;
  setInterval(poll, 3000);

  const form = document.getElementById("chatForm");
  if (form) form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = form.querySelector("input[name=body]");
    if (!input.value.trim()) return;
    await fetch(`/booking/${bid}/message`, { method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ body: input.value }) });
    input.value = ""; poll();
  });
})();
