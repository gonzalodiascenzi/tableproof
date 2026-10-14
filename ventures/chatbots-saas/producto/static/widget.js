// Widget de chat. Se pega en la web del cliente:
//   <script src="https://<dominio del producto>/widget.js" data-bot="<id del bot>"></script>
// El historial vive solo en la pestaña (no se guarda en el servidor ni en el navegador).
// Las respuestas se insertan como texto, nunca como HTML.
(function () {
  var script = document.currentScript;
  var botId = script.getAttribute("data-bot");
  var base = new URL(script.src).origin;
  if (!botId) return;
  var history = [];
  var busy = false;

  var css = document.createElement("style");
  css.textContent =
    ".tpc-btn{position:fixed;right:16px;bottom:16px;z-index:2147483000;border:0;border-radius:24px;padding:12px 18px;background:#1f3a5f;color:#fff;font:600 14px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.25)}" +
    ".tpc-box{position:fixed;right:16px;bottom:72px;z-index:2147483000;width:min(360px,calc(100vw - 32px));height:min(480px,calc(100vh - 100px));display:flex;flex-direction:column;background:#fff;color:#1b1b1b;border:1px solid #cfd6de;border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.25);font:14px/1.45 system-ui,sans-serif;overflow:hidden}" +
    ".tpc-box[hidden]{display:none}" +
    ".tpc-head{padding:10px 14px;background:#1f3a5f;color:#fff;font-weight:600}" +
    ".tpc-note{padding:6px 14px;background:#f1f4f7;color:#4a5560;font-size:12px}" +
    ".tpc-log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}" +
    ".tpc-msg{max-width:85%;padding:8px 11px;border-radius:12px;white-space:pre-wrap;overflow-wrap:anywhere}" +
    ".tpc-user{align-self:flex-end;background:#1f3a5f;color:#fff}" +
    ".tpc-bot{align-self:flex-start;background:#eef1f4;color:#1b1b1b}" +
    ".tpc-form{display:flex;gap:6px;padding:10px;border-top:1px solid #e2e7ec}" +
    ".tpc-form input{flex:1;min-width:0;padding:9px 10px;border:1px solid #b9c2cc;border-radius:8px;font:inherit;color:#1b1b1b;background:#fff}" +
    ".tpc-form button{border:0;border-radius:8px;padding:9px 14px;background:#1f3a5f;color:#fff;font:inherit;font-weight:600;cursor:pointer}" +
    ".tpc-form button:disabled{opacity:.5;cursor:default}";
  document.head.appendChild(css);

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  var btn = el("button", "tpc-btn", "¿Consultas?");
  btn.type = "button";
  var box = el("div", "tpc-box");
  box.hidden = true;
  var log = el("div", "tpc-log");
  var form = el("form", "tpc-form");
  var input = el("input");
  input.type = "text";
  input.maxLength = 1000;
  input.placeholder = "Escribí tu consulta";
  input.setAttribute("aria-label", "Tu consulta");
  var send = el("button", "", "Enviar");
  send.type = "submit";
  form.appendChild(input);
  form.appendChild(send);
  box.appendChild(el("div", "tpc-head", "Consultas"));
  box.appendChild(el("div", "tpc-note", "Asistente automático: puede equivocarse."));
  box.appendChild(log);
  box.appendChild(form);
  document.body.appendChild(box);
  document.body.appendChild(btn);

  function add(role, text) {
    var m = el("div", "tpc-msg " + (role === "user" ? "tpc-user" : "tpc-bot"), text);
    log.appendChild(m);
    log.scrollTop = log.scrollHeight;
    return m;
  }

  btn.addEventListener("click", function () {
    box.hidden = !box.hidden;
    if (!box.hidden) input.focus();
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    send.disabled = true;
    input.value = "";
    add("user", text);
    var pending = add("bot", "…");
    fetch(base + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot_id: botId, message: text, history: history }),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          return { ok: r.ok, d: d };
        });
      })
      .then(function (res) {
        if (res.ok && res.d.reply) {
          pending.textContent = res.d.reply;
          history.push({ role: "user", content: text }, { role: "assistant", content: res.d.reply });
        } else {
          pending.textContent = (res.d && res.d.error) || "No pude contestar. Probá de nuevo en un rato.";
        }
      })
      .catch(function () {
        pending.textContent = "No pude contestar. Probá de nuevo en un rato.";
      })
      .then(function () {
        busy = false;
        send.disabled = false;
        log.scrollTop = log.scrollHeight;
        input.focus();
      });
  });
})();
