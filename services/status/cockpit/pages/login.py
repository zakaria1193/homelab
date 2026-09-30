"""/login: the sign-in form."""

LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · __TITLE__</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --down: #f85149; --accent: #58a6ff;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --panel: #fff; --border: #d0d7de; --text: #1f2328;
            --muted: #636c76; --accent: #0969da; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; background: var(--bg); color: var(--text); font: 15px/1.5
    ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  form { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 24px; width: 320px; margin: 24px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 12px 0 4px; }
  input[type=text], input[type=password] { width: 100%; background: var(--bg);
    color: var(--text); font: inherit; border: 1px solid var(--border); border-radius: 6px;
    padding: 7px 10px; }
  input:focus { outline: none; border-color: var(--accent); }
  .keep { display: flex; align-items: center; gap: 8px; margin: 16px 0 4px;
    font-size: 13px; color: var(--muted); }
  .keep input { accent-color: var(--accent); width: 15px; height: 15px; }
  button { width: 100%; margin-top: 16px; background: var(--accent); border: none;
    color: #fff; font: inherit; font-weight: 600; border-radius: 6px; padding: 8px;
    cursor: pointer; }
  button:hover { filter: brightness(1.08); }
  .bad { color: var(--down); font-size: 13px; margin-top: 12px; }
  .note { color: var(--muted); font-size: 12px; margin-top: 14px; }
</style>
</head>
<body>
<form method="post" action="/login">
  <h1>__TITLE__</h1>
  <div class="sub">Sign in to reach the console.</div>
  <input type="hidden" name="next" value="__NEXT__">
  <label for="user">User</label>
  <input id="user" name="user" type="text" autocomplete="username" autofocus>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password">
  <div class="keep">
    <input id="remember" name="remember" type="checkbox" value="1" checked>
    <label for="remember" style="margin:0">Keep me signed in for __DAYS__ days</label>
  </div>
  <button type="submit">Sign in</button>
  __ERROR__
  <div class="note">Signing out, or changing the password in <code>.env</code>,
  ends every remembered session.</div>
</form>
</body>
</html>
"""
