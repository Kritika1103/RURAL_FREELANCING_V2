// ---- Fill hidden latitude/longitude using the browser Geolocation API
function useMyLocation(btn) {
  const form = btn.closest("form");
  if (!navigator.geolocation) { alert("Location is not supported in this browser."); return; }
  btn.disabled = true; const old = btn.textContent; btn.textContent = "Finding location...";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      form.querySelector("[name=latitude],[name=lat]").value = pos.coords.latitude.toFixed(6);
      form.querySelector("[name=longitude],[name=lng]").value = pos.coords.longitude.toFixed(6);
      btn.textContent = "Location saved \u2713"; btn.disabled = false;
      if (btn.dataset.submit === "1") form.submit();
    },
    () => { alert("Could not get location. Allow location access and try again."); btn.textContent = old; btn.disabled = false; },
    { enableHighAccuracy: true, timeout: 10000 });
}

// ---- Voice search using the Web Speech API (works in Chrome / Edge)
function startVoice(btn) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert("Voice search needs Google Chrome or Microsoft Edge."); return; }
  const input = document.getElementById(btn.dataset.target);
  const langSel = document.getElementById("voiceLang");
  const rec = new SR();
  rec.lang = langSel ? langSel.value : "en-IN";
  rec.interimResults = false;
  const label = btn.textContent;
  btn.textContent = "Listening...";
  rec.onresult = (e) => { input.value = e.results[0][0].transcript.replace(/[.]$/, ""); input.form.submit(); };
  rec.onerror = () => { btn.textContent = label; alert("Could not hear you. Please try again."); };
  rec.onend = () => { btn.textContent = label; };
  rec.start();
}

// ---- Read text aloud (voice assistance)
function speak(text, lang) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text); u.lang = lang || "en-IN";
  window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
}

// ---- Installable app (PWA): register the service worker (needs HTTPS or localhost)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
