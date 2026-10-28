// Password gate in front of the price board.
//
// The scanner (GitHub Actions) writes the finished board.html straight into this Worker's KV namespace.
// Visitors only get it with a session cookie, which they receive by entering BOARD_PASSWORD. Sessions are
// signed with SESSION_SECRET and the password itself, so changing the password signs everyone out.

const SESSION_COOKIE = "board_session";
const SESSION_DAYS = 30;
const SECURITY_HEADERS = {
  "X-Robots-Tag": "noindex, nofollow",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
};
const encoder = new TextEncoder();
// Secrets piped into `wrangler secret put` can pick up a trailing newline.
const secret = (env, name) => (env[name] || "").replace(/[\r\n]+$/, "");

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname.startsWith("www.")) {
      url.hostname = url.hostname.slice(4);
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/robots.txt") return respond("User-agent: *\nDisallow: /\n", 200, "text/plain");
    if (url.pathname === "/login" && request.method === "POST") return login(request, env);
    if (url.pathname === "/logout") return redirect("/", `${SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`);
    if (url.pathname !== "/") return redirect("/");

    if (!(await hasSession(request, env))) {
      return respond(loginPage(url.searchParams.has("failed") ? "That password didn't match." : ""), 200);
    }
    const board = await env.BOARD.get("board.html");
    if (!board) return respond(messagePage("The board is warming up", "The first scan hasn't been uploaded yet. Check back in a few minutes."), 503);
    return respond(board.replace("</body>", SIGN_OUT + "</body>"), 200);
  },
};

async function login(request, env) {
  const form = await request.formData();
  const password = String(form.get("password") || "");
  if (!secret(env, "BOARD_PASSWORD") || !(await sameSecret(password, secret(env, "BOARD_PASSWORD")))) {
    await new Promise((resolve) => setTimeout(resolve, 1000)); // slows down password guessing
    return redirect("/?failed=1");
  }
  const expires = String(Math.floor(Date.now() / 1000) + SESSION_DAYS * 86400);
  const cookie = `${SESSION_COOKIE}=${expires}.${await sign(env, expires)}; Path=/; Max-Age=${SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax`;
  return redirect("/", cookie);
}

async function hasSession(request, env) {
  if (!secret(env, "BOARD_PASSWORD") || !secret(env, "SESSION_SECRET")) return false;
  const match = (request.headers.get("Cookie") || "").match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]+)`));
  if (!match) return false;
  const [expires, signature] = match[1].split(".");
  if (!expires || !signature || Number(expires) < Date.now() / 1000) return false;
  return sameSecret(signature, await sign(env, expires));
}

async function sign(env, payload) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(`${secret(env, "SESSION_SECRET")}\n${secret(env, "BOARD_PASSWORD")}`),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(payload)));
  return btoa(String.fromCharCode(...mac)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Compares digests rather than the raw strings, so the comparison takes the same time whatever the input.
async function sameSecret(a, b) {
  const [x, y] = await Promise.all([a, b].map((s) => crypto.subtle.digest("SHA-256", encoder.encode(s))));
  return crypto.subtle.timingSafeEqual(x, y);
}

function respond(body, status, type = "text/html; charset=utf-8") {
  return new Response(body, { status, headers: { "Content-Type": type, "Cache-Control": "no-store", ...SECURITY_HEADERS } });
}

function redirect(location, cookie) {
  const headers = { Location: location, "Cache-Control": "no-store", ...SECURITY_HEADERS };
  if (cookie) headers["Set-Cookie"] = cookie;
  return new Response(null, { status: 303, headers });
}

const SIGN_OUT = '<a href="/logout" style="position:fixed;right:12px;bottom:10px;font:12px system-ui,sans-serif;color:#858e9a;text-decoration:none">Sign out</a>';

const PAGE_STYLE = `
  :root { --bg: #f5f6f8; --panel: #fff; --ink: #111418; --muted: #5b6470; --line: #d0d5dd; --accent: #0a58ca; --err: #b3362c; color-scheme: light; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0f1115; --panel: #171a20; --ink: #e8eaee; --muted: #a3abb7; --line: #363b46; --accent: #7cb2ff; --err: #ff8b80; color-scheme: dark; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px; background: var(--bg); color: var(--ink);
         font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { width: 100%; max-width: 360px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p { margin: 0 0 16px; color: var(--muted); }
  label { display: block; font-weight: 600; margin-bottom: 6px; }
  input[type=password] { width: 100%; font: inherit; padding: 9px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); color: var(--ink); }
  button { width: 100%; margin-top: 14px; font: inherit; font-weight: 600; padding: 10px; border: 0; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; }
  .err { color: var(--err); margin: 10px 0 0; }`;

function loginPage(error) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>SUV Price Board</title><style>${PAGE_STYLE}</style></head>
<body><main><h1>SUV Price Board</h1><p>Enter the password to see the board.</p>
<form method="post" action="/login">
<input type="text" name="username" value="board" autocomplete="username" hidden>
<label for="password">Password</label>
<input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
${error ? `<p class="err" role="alert">${error}</p>` : ""}
<button type="submit">Show board</button>
</form></main></body></html>`;
}

function messagePage(title, text) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>SUV Price Board</title><style>${PAGE_STYLE}</style></head>
<body><main><h1>${title}</h1><p>${text}</p></main></body></html>`;
}
