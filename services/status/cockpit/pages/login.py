"""/login: the sign-in form."""

from .theme import THEME

LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · __TITLE__</title>
<style>
  {THEME}
  body { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  form.card { width: 320px; margin: 24px; padding: 24px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 12px 0 4px; }
  .keep { display: flex; align-items: center; gap: 8px; margin: 16px 0 4px;
    font-size: 13px; color: var(--muted); }
  .keep input { accent-color: var(--accent); width: 15px; height: 15px; }
  button[type=submit] { width: 100%; margin-top: 16px; padding: 8px; }
  .bad { color: var(--down); font-size: 13px; margin-top: 12px; }
  .note { color: var(--muted); font-size: 12px; margin-top: 14px; }
</style>
</head>
<body>
<form method="post" action="/login" class="card">
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
  <button type="submit" class="btn">Sign in</button>
  __ERROR__
  <div class="note">Signing out, or changing the password in <code>.env</code>,
  ends every remembered session.</div>
</form>
</body>
</html>
""".replace("{THEME}", THEME)
