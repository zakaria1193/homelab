// Shared helpers for every cockpit page. Loaded after theme.css and before
// the page's own script.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function postJSON(path, body) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await res.json();
  } catch (err) {
    return { ok: false, message: String(err) };
  }
}

// Server values a page used to receive through a Python .replace() now
// arrive as data-* attributes on <body>, escaped with html.escape(quote=True)
// by the handler. pageConfig() reads them back into a plain object, camelCased
// (data-tmux-session -> tmuxSession) the way the DOM already does.
function pageConfig() {
  return Object.assign({}, document.body.dataset);
}
