(() => {
  const token = document.body.dataset.token;
  const ACTIONS = [
    "redrive_now",
    "redrive_later",
    "quarantine_poison",
    "discard_duplicate",
    "escalate_human",
  ];
  const ACTION_META = {
    redrive_now: {
      label: "Redrive now",
      short: "now",
      desc: "Send back to the source queue",
      dest: "→ source queue",
      color: "var(--a-now)",
      ink: "var(--a-now-ink)",
    },
    redrive_later: {
      label: "Redrive later",
      short: "later",
      desc: "Send back with a delay",
      dest: "→ source, delayed",
      color: "var(--a-later)",
      ink: "var(--a-later-ink)",
    },
    quarantine_poison: {
      label: "Quarantine",
      short: "quar",
      desc: "Move to S3 quarantine",
      dest: "→ S3 quarantine",
      color: "var(--a-quar)",
      ink: "var(--a-quar-ink)",
    },
    discard_duplicate: {
      label: "Discard duplicate",
      short: "disc",
      desc: "Delete from the DLQ",
      dest: "→ delete",
      color: "var(--a-disc)",
      ink: "var(--a-disc-ink)",
    },
    escalate_human: {
      label: "Escalate to human",
      short: "esc",
      desc: "Left in the DLQ, flagged in report",
      dest: "stays in DLQ",
      color: "var(--a-esc)",
      ink: "var(--a-esc-ink)",
    },
  };

  let idToken = sessionStorage.getItem("dlqj_id") || "";
  let run = null;
  let messages = [];
  let clusters = null;
  let benchmark = null;
  let filterAction = "";
  let msgPage = 0;
  const PAGE_SIZE = 25;
  let selectedId = null;

  const $ = (s) => document.querySelector(s);
  const authGate = $("#auth-gate");
  const siteLanding = $("#site-landing");
  const app = $("#app");
  const DEPLOY_ACCOUNT = "<AWS_ACCOUNT_ID>";
  const DEPLOY_REGION = "us-east-1";
  const DEPLOY_ROLE = "dlqj-ec2";

  function esc(s) {
    return String(s ?? "").replace(/[<>&"']/g, (c) =>
      ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function chipBg(color) {
    return `color-mix(in oklch, ${color} 15%, transparent)`;
  }

  function bandOf(c) {
    if (c == null || Number.isNaN(c)) return "none";
    if (c >= 0.85) return "auto";
    if (c >= 0.6) return "check";
    return "low";
  }

  function confColor(c) {
    const b = bandOf(c);
    if (b === "auto") return "var(--fg)";
    if (b === "check") return "var(--br)";
    if (b === "low") return "var(--a-esc)";
    return "var(--faint)";
  }

  function shortId(id) {
    return (id || "").slice(0, 13);
  }

  function queueShort(nameOrArn) {
    if (!nameOrArn) return "—";
    const s = String(nameOrArn);
    if (s.includes(":")) return s.split(":").pop() || s;
    return s;
  }

  function decodeEmail() {
    if (!idToken) return "";
    try {
      const payload = JSON.parse(atob(idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      return payload.email || payload["cognito:username"] || "";
    } catch {
      return "";
    }
  }

  function initials(email) {
    if (!email) return "—";
    const local = email.split("@")[0] || email;
    const parts = local.split(/[._-]/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return local.slice(0, 2).toUpperCase();
  }

  function setTheme(theme) {
    document.body.setAttribute("data-theme", theme);
    authGate.setAttribute("data-theme", theme);
    app.setAttribute("data-theme", theme);
    if (siteLanding) siteLanding.setAttribute("data-theme", theme);
    $("#btn-theme-light")?.classList.toggle("active", theme === "light");
    $("#btn-theme-dark")?.classList.toggle("active", theme === "dark");
    const siteToggle = $("#site-theme-toggle");
    if (siteToggle) siteToggle.textContent = theme === "light" ? "Dark" : "Light";
    try {
      localStorage.setItem("dlqj_theme", theme);
    } catch (_) {}
  }

  function showLanding() {
    document.body.classList.add("login-only");
    document.body.classList.remove("authed", "auth-open");
    authGate.classList.add("hidden");
    app.classList.add("hidden");
    if (siteLanding) siteLanding.classList.remove("hidden");
  }

  function openAuth(tab) {
    document.body.classList.add("login-only", "auth-open");
    document.body.classList.remove("authed");
    authGate.classList.remove("hidden");
    app.classList.add("hidden");
    setTab(tab || "login");
    showAuthMsg("");
  }

  function fillDeployAccountChip() {
    const name = $("#acct-name");
    const sub = $("#acct-sub");
    if (name) name.textContent = DEPLOY_ACCOUNT;
    if (sub) sub.textContent = `${DEPLOY_REGION} · instance role`;
    const setName = $("#set-acct-name");
    const setSub = $("#set-acct-sub");
    if (setName) setName.textContent = `Account ${DEPLOY_ACCOUNT}`;
    if (setSub) {
      setSub.textContent = `Region ${DEPLOY_REGION} · Instance role ${DEPLOY_ROLE}`;
    }
  }

  function renderHeroStats(stats) {
    const labels = [
      ["redrive_now", "Redrive now", "var(--a-now)"],
      ["redrive_later", "Redrive later", "var(--a-later)"],
      ["quarantine_poison", "Quarantine", "var(--a-quar)"],
      ["discard_duplicate", "Discard", "var(--a-disc)"],
      ["escalate_human", "Escalate", "var(--a-esc)"],
    ];
    const counts = (stats && stats.counts) || {};
    const processed = (stats && stats.processed) || 0;
    const hasRun = Boolean(stats && stats.has_run);
    const cards = $("#hero-action-cards");
    if (cards) {
      cards.innerHTML = labels
        .map(
          ([key, label, color]) =>
            `<div><span class="lab"><span class="sw" style="background:${color}"></span>${esc(
              label
            )}</span><span class="n">${hasRun ? counts[key] || 0 : 0}</span></div>`
        )
        .join("");
    }
    const queueEl = $("#hero-queue");
    const badgeEl = $("#hero-badge");
    const q = (stats && stats.queue) || "dlqj-payments-dlq";
    if (queueEl) queueEl.textContent = q;
    if (badgeEl) {
      badgeEl.textContent = hasRun
        ? stats.label || `Last run · ${q}`
        : "No triage run yet";
    }
    const msgs = $("#hero-msgs");
    const lat = $("#hero-lat");
    const br = $("#hero-bedrock");
    if (msgs) msgs.textContent = String(hasRun ? processed : 0);
    if (lat) {
      const ms = stats && stats.median_decider_ms;
      lat.textContent = hasRun && ms != null ? `${ms} ms` : "—";
    }
    if (br) {
      const bc = (stats && stats.bedrock_calls) || 0;
      br.innerHTML = hasRun
        ? `${bc} <span style="color:var(--faint);font-size:12px">vs ${processed}</span>`
        : "0";
    }
    const bars = $("#hero-bars");
    if (bars) {
      const bands = (stats && stats.band_counts) || {};
      const low = bands.low || 0;
      const review = bands.review || 0;
      const auto = bands.auto || 0;
      const total = low + review + auto || processed || 0;
      let heights;
      if (hasRun && total > 0) {
        // 20 bars proportional to escalate / bedrock / auto bands
        heights = [];
        for (let i = 0; i < 20; i++) {
          const t = i / 19;
          const share =
            t < low / total
              ? 0.35 + (low / total) * 0.5
              : t < (low + review) / total
                ? 0.45 + (review / total) * 0.45
                : 0.55 + (auto / total) * 0.45;
          heights.push(Math.round(18 + share * 82));
        }
      } else {
        heights = Array(20).fill(8);
      }
      bars.innerHTML = heights
        .map((h, i) => {
          const c =
            i < 8 ? "var(--a-esc)" : i < 14 ? "var(--br)" : "var(--fg)";
          return `<i style="height:${h}%;background:${c}"></i>`;
        })
        .join("");
    }
  }

  async function loadPublicStats() {
    try {
      const res = await fetch("/api/public/stats");
      if (!res.ok) throw new Error("stats");
      const stats = await res.json();
      renderHeroStats(stats);
    } catch (_) {
      renderHeroStats({ has_run: false, processed: 0, counts: {} });
    }
  }

  function showAuthMsg(msg, ok = false) {
    const el = $("#auth-msg");
    el.hidden = !msg;
    el.textContent = msg || "";
    el.classList.toggle("ok", Boolean(ok && msg));
  }

  async function api(path, opts = {}) {
    const headers = {
      "Content-Type": "application/json",
      "X-DLQJ-Token": token,
      ...(opts.headers || {}),
    };
    if (idToken) headers.Authorization = `Bearer ${idToken}`;
    const res = await fetch(path, { ...opts, headers });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { error: text };
    }
    if (!res.ok) {
      const err = new Error((data && (data.message || data.error)) || res.statusText);
      err.status = res.status;
      err.code = data && data.error;
      err.data = data;
      throw err;
    }
    return data;
  }

  function setTab(name) {
    ["login", "signup", "verify"].forEach((t) => {
      $(`#tab-${t}`).classList.toggle("active", t === name);
      $(`#form-${t}`).classList.toggle("hidden", t !== name);
    });
    const title = $("#auth-title");
    const sub = $("#auth-sub");
    const sw = $("#auth-switch");
    if (name === "signup") {
      if (title) title.textContent = "Create your account";
      if (sub) {
        sub.textContent =
          "Sign up with email to use the shared deploy account. No AWS keys required.";
      }
      if (sw) {
        sw.innerHTML =
          'Already have an account? <button type="button" id="switch-to-login">Log in</button>';
        $("#switch-to-login").onclick = () => setTab("login");
      }
    } else if (name === "verify") {
      if (title) title.textContent = "Verify your email";
      if (sub) sub.textContent = "Enter the confirmation code from Cognito.";
      if (sw) sw.innerHTML = "";
    } else {
      if (title) title.textContent = "Log in to DLQ Judge";
      if (sub) {
        sub.textContent = "View runs, reports and audit logs on the shared deploy.";
      }
      if (sw) {
        sw.innerHTML =
          'New here? <button type="button" id="switch-to-signup">Create an account</button>';
        $("#switch-to-signup").onclick = () => setTab("signup");
      }
    }
  }
  $("#tab-login").onclick = () => setTab("login");
  $("#tab-signup").onclick = () => setTab("signup");
  $("#tab-verify").onclick = () => setTab("verify");
  $("#auth-back-home").onclick = () => showLanding();
  $("#site-login")?.addEventListener("click", () => openAuth("login"));
  $("#site-signup")?.addEventListener("click", () => openAuth("signup"));
  $("#hero-signup")?.addEventListener("click", () => openAuth("signup"));
  $("#hero-login")?.addEventListener("click", () => openAuth("login"));
  $("#footer-signup")?.addEventListener("click", () => openAuth("signup"));
  $("#site-logo")?.addEventListener("click", () => showLanding());
  $("#site-theme-toggle")?.addEventListener("click", () => {
    const cur = document.body.getAttribute("data-theme") || "light";
    setTheme(cur === "light" ? "dark" : "light");
  });
  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => {
      showLanding();
      const id = btn.getAttribute("data-jump");
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          window.scrollTo({
            top: el.getBoundingClientRect().top + window.scrollY - 70,
            behavior: "smooth",
          });
        }
      }, 30);
    });
  });

  $("#form-signup").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const data = await api("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          email: fd.get("email"),
          password: fd.get("password"),
        }),
      });
      const email = fd.get("email");
      $("#form-verify [name=email]").value = email;
      $("#form-login [name=email]").value = email;
      if (data.auto_confirmed || data.user_confirmed) {
        showAuthMsg("Account confirmed — you can log in now.", true);
        setTab("login");
      } else {
        const dest =
          (data.code_delivery && data.code_delivery.destination) || email;
        let msg = `Check your email (${dest}) for a verification code, then use Verify.`;
        if (data.admin_confirm_error) {
          msg += " Auto-confirm failed — use Resend, then Verify.";
        }
        showAuthMsg(msg, true);
        setTab("verify");
      }
    } catch (err) {
      showAuthMsg(err.message);
    }
  };

  $("#form-verify").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("/api/auth/confirm", {
        method: "POST",
        body: JSON.stringify({ email: fd.get("email"), code: fd.get("code") }),
      });
      showAuthMsg("Verified — you can log in.", true);
      setTab("login");
    } catch (err) {
      showAuthMsg(err.message);
    }
  };

  $("#btn-resend").onclick = async () => {
    const email = $("#form-verify [name=email]").value.trim();
    if (!email) {
      showAuthMsg("Enter your email first.");
      return;
    }
    try {
      const data = await api("/api/auth/resend", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      const dest =
        (data.code_delivery && data.code_delivery.destination) || email;
      showAuthMsg(`New code sent to ${dest}. Check inbox/spam.`, true);
    } catch (err) {
      showAuthMsg(err.message);
    }
  };

  $("#form-login").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const email = String(fd.get("email") || "").trim();
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password: fd.get("password"),
        }),
      });
      idToken = data.id_token;
      sessionStorage.setItem("dlqj_id", idToken);
      showAuthMsg("");
      await enterApp();
    } catch (err) {
      const msg = err.message || "";
      const notConfirmed =
        err.code === "user_not_confirmed" ||
        /not confirmed/i.test(msg) ||
        /UserNotConfirmed/i.test(msg);
      if (notConfirmed) {
        $("#form-verify [name=email]").value = email;
        setTab("verify");
        showAuthMsg(
          "Account not confirmed. We tried to confirm it — click Resend if needed, enter the code, then log in again."
        );
        try {
          await api("/api/auth/resend", {
            method: "POST",
            body: JSON.stringify({ email }),
          });
        } catch (_) {}
      } else {
        showAuthMsg(msg);
      }
    }
  };

  function leaveApp() {
    idToken = "";
    sessionStorage.removeItem("dlqj_id");
    $("#profile-menu")?.classList.add("hidden");
    showLanding();
    loadPublicStats();
  }

  $("#btn-logout").onclick = async () => {
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
    } catch (_) {}
    leaveApp();
    showAuthMsg("Signed out.", true);
  };

  $("#btn-theme-light").onclick = () => setTheme("light");
  $("#btn-theme-dark").onclick = () => setTheme("dark");
  try {
    const saved = localStorage.getItem("dlqj_theme");
    if (saved === "dark" || saved === "light") setTheme(saved);
  } catch (_) {}

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
    $(`#view-${name}`).classList.remove("hidden");
    document.querySelectorAll(".nav").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === name);
    });
  }
  document.querySelectorAll(".nav").forEach((b) => {
    b.onclick = () => showView(b.dataset.view);
  });

  function loadProfileLocal() {
    try {
      return JSON.parse(localStorage.getItem("dlqj_profile") || "{}");
    } catch (_) {
      return {};
    }
  }

  function saveProfileLocal(p) {
    localStorage.setItem("dlqj_profile", JSON.stringify(p));
  }

  function updateProfile() {
    const email = decodeEmail();
    const local = loadProfileLocal();
    const name = local.name || (email ? email.split("@")[0] : "Signed in");
    const team = local.team || "Platform Engineering";
    $("#profile-email").textContent = email || "—";
    $("#profile-name").textContent = name;
    $("#profile-avatar").textContent = initials(name || email);
    const mn = $("#menu-profile-name");
    const me = $("#menu-profile-email");
    if (mn) mn.textContent = name;
    if (me) me.textContent = email || "—";
    const pfName = $("#pf-name");
    if (pfName) {
      pfName.value = name;
      $("#pf-team").value = team;
      $("#pf-email").value = email || "";
      $("#pf-avatar").textContent = initials(name || email);
      $("#pref-notify-email").textContent = email
        ? `Sent to ${email}`
        : "";
    }
  }

  function openSettingsTab(stab) {
    showView("settings");
    document.querySelectorAll(".set-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.stab === stab);
    });
    ["profile", "prefs", "accounts"].forEach((k) => {
      $(`#stab-${k}`)?.classList.toggle("hidden", k !== stab);
    });
    $("#profile-menu")?.classList.add("hidden");
    if (stab === "accounts") refreshAwsAccounts();
  }

  function connectorsKey() {
    return `dlqj_connectors_${decodeEmail() || "anon"}`;
  }

  function loadSavedConnectors() {
    try {
      return JSON.parse(localStorage.getItem(connectorsKey()) || "[]");
    } catch (_) {
      return [];
    }
  }

  function saveConnectors(list) {
    localStorage.setItem(connectorsKey(), JSON.stringify(list));
  }

  let liveConnector = null;
  let lastTestResult = null;

  async function refreshAwsAccounts() {
    const cards = $("#acct-cards");
    if (!cards) return;
    cards.innerHTML = `<div class="muted" style="padding:12px">Checking connector…</div>`;
    try {
      liveConnector = await api("/api/aws/connector");
    } catch (err) {
      cards.innerHTML = `<div class="page-error">Could not load connector: ${esc(err.message)}</div>`;
      return;
    }
    const saved = loadSavedConnectors();
    const liveId = liveConnector.account_id || DEPLOY_ACCOUNT;
    // Merge: live deploy account always first; saved extras after
    const list = [
      {
        id: liveId,
        name: liveConnector.name || "Hackathon deploy",
        region: liveConnector.region || DEPLOY_REGION,
        role: liveConnector.role_name || DEPLOY_ROLE,
        role_arn: liveConnector.role_arn || "",
        queues: liveConnector.queues || 0,
        last: liveConnector.checked_at || "—",
        run: (run && run.run_id) || "—",
        stLabel: liveConnector.st_label || "Connected",
        ok: liveConnector.ok !== false,
        current: true,
        checks: liveConnector.checks || [],
        connector: "instance_role",
        builtin: true,
      },
      ...saved.filter((c) => c.id !== liveId),
    ];
    let nOk = 0;
    let nDeg = 0;
    let nDisc = 0;
    list.forEach((c) => {
      if (c.stLabel === "Disconnected") nDisc++;
      else if (c.ok === false || c.stLabel === "Degraded" || c.stLabel === "Failed")
        nDeg++;
      else nOk++;
    });
    $("#stat-connected").textContent = String(nOk);
    $("#stat-degraded").textContent = String(nDeg);
    $("#stat-disc").textContent = String(nDisc);
    $("#stat-total").textContent = String(list.length);

    cards.innerHTML = list
      .map((c) => {
        const color = c.ok === false ? "var(--a-esc)" : "var(--ok)";
        const ink = c.ok === false ? "var(--a-esc-ink)" : "var(--ok-ink)";
        const checks = (c.checks || [])
          .map(
            (ch) => `
          <div class="acct-check">
            <span style="font-weight:700;color:${esc(ch.color)}">${esc(ch.mark)}</span>
            <span>${esc(ch.label)}</span>
            <span class="mono muted">${esc(ch.note)}</span>
          </div>`
          )
          .join("");
        return `
        <article class="acct-card" data-id="${esc(c.id)}" style="border-color:color-mix(in oklch, ${color} 35%, var(--line))">
          <div class="acct-card-main">
            <div>
              <div class="acct-card-title">
                <b>${esc(c.name)}</b>
                <span class="acct-pill" style="background:color-mix(in oklch, ${color} 15%, transparent);color:${ink}">
                  <span class="dot" style="background:${color}"></span>${esc(c.stLabel)}
                </span>
                ${c.current ? `<span class="muted" style="font-size:11px">· active</span>` : ""}
              </div>
              <div class="mono muted">${esc(c.id)} · ${esc(c.region)}</div>
              <div class="mono faint">${esc(c.role_arn || c.role || "")}</div>
            </div>
            <div class="acct-card-meta">
              <span><span class="muted">Queues</span> ${esc(String(c.queues))} dlqj-*</span>
              <span><span class="muted">Last check</span> ${esc(c.last)}</span>
              <span><span class="muted">Last run</span> ${esc(c.run)}</span>
            </div>
            <div class="acct-card-actions">
              <button type="button" class="btn btn-retry-conn" data-id="${esc(c.id)}">Test again</button>
              ${
                c.builtin
                  ? `<button type="button" class="btn" disabled title="Instance role cannot be disconnected">Disconnect</button>`
                  : `<button type="button" class="btn btn-disc-conn" data-id="${esc(c.id)}" style="color:var(--a-esc-ink)">Disconnect</button>`
              }
            </div>
          </div>
          <div class="acct-checks">${checks}</div>
        </article>`;
      })
      .join("");

    fillDeployAccountChip();
    if (liveConnector.account_id) {
      $("#acct-name").textContent = liveConnector.account_id;
      $("#acct-sub").textContent = `${liveConnector.region} · ${liveConnector.role_name}`;
    }

    cards.querySelectorAll(".btn-retry-conn").forEach((b) => {
      b.onclick = async () => {
        b.disabled = true;
        await refreshAwsAccounts();
      };
    });
    cards.querySelectorAll(".btn-disc-conn").forEach((b) => {
      b.onclick = () => {
        const id = b.dataset.id;
        saveConnectors(loadSavedConnectors().filter((c) => c.id !== id));
        refreshAwsAccounts();
      };
    });
  }

  if ($("#btn-add-aws")) {
    $("#btn-add-aws").onclick = () => {
      $("#aws-connect-panel").classList.remove("hidden");
      $("#conn-role-arn").value = "";
      $("#conn-name").value = "My AWS account";
      $("#conn-test-msg").textContent = "";
      $("#btn-save-conn").disabled = true;
      lastTestResult = null;
    };
  }
  if ($("#btn-connect-cancel")) {
    $("#btn-connect-cancel").onclick = () => {
      $("#aws-connect-panel").classList.add("hidden");
    };
  }
  document.querySelectorAll(".conn-method").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".conn-method").forEach((x) =>
        x.classList.toggle("active", x === b)
      );
      ["cfn", "cli", "sso"].forEach((m) => {
        $(`#conn-${m}`)?.classList.toggle("hidden", b.dataset.method !== m);
      });
    };
  });
  if ($("#btn-test-conn")) {
    $("#btn-test-conn").onclick = async () => {
      const msg = $("#conn-test-msg");
      msg.textContent = "Testing…";
      try {
        lastTestResult = await api("/api/aws/connector/test", {
          method: "POST",
          body: JSON.stringify({
            role_arn: $("#conn-role-arn").value.trim(),
            region: $("#conn-region").value,
          }),
        });
        if (lastTestResult.ok) {
          msg.textContent =
            lastTestResult.message ||
            `OK · account ${lastTestResult.account_id}`;
          $("#btn-save-conn").disabled = false;
        } else {
          msg.textContent =
            (lastTestResult.message || "Failed") +
            (lastTestResult.hint ? ` — ${lastTestResult.hint}` : "");
          $("#btn-save-conn").disabled = true;
        }
      } catch (err) {
        msg.textContent = err.message;
        $("#btn-save-conn").disabled = true;
      }
    };
  }
  if ($("#btn-save-conn")) {
    $("#btn-save-conn").onclick = () => {
      if (!lastTestResult || !lastTestResult.ok) return;
      const id = String(lastTestResult.account_id || DEPLOY_ACCOUNT);
      const entry = {
        id,
        name: $("#conn-name").value.trim() || "AWS account",
        region: $("#conn-region").value || DEPLOY_REGION,
        role: lastTestResult.role_name || lastTestResult.pasted_role_arn || "",
        role_arn: lastTestResult.pasted_role_arn || lastTestResult.role_arn || "",
        queues: lastTestResult.queues || 0,
        last: lastTestResult.checked_at || new Date().toISOString(),
        run: "—",
        stLabel: lastTestResult.st_label || "Connected",
        ok: true,
        current: false,
        checks: lastTestResult.checks || [],
        connector: lastTestResult.connector || "saved",
      };
      const rest = loadSavedConnectors().filter((c) => c.id !== id);
      saveConnectors([entry, ...rest]);
      $("#aws-connect-panel").classList.add("hidden");
      refreshAwsAccounts();
    };
  }

  $("#profile-display").onclick = (e) => {
    e.stopPropagation();
    const menu = $("#profile-menu");
    menu.classList.toggle("hidden");
    $("#profile-display").setAttribute(
      "aria-expanded",
      menu.classList.contains("hidden") ? "false" : "true"
    );
  };
  document.addEventListener("click", () => {
    $("#profile-menu")?.classList.add("hidden");
  });
  $("#profile-menu")?.addEventListener("click", (e) => e.stopPropagation());
  $("#btn-go-profile").onclick = () => openSettingsTab("profile");
  $("#btn-go-settings").onclick = () => openSettingsTab("prefs");
  document.querySelectorAll(".set-tab").forEach((b) => {
    b.onclick = () => openSettingsTab(b.dataset.stab);
  });

  $("#btn-pf-save").onclick = () => {
    const email = decodeEmail();
    saveProfileLocal({
      name: $("#pf-name").value.trim() || email.split("@")[0],
      team: $("#pf-team").value.trim() || "Platform Engineering",
    });
    updateProfile();
    const m = $("#pf-msg");
    m.hidden = false;
    m.textContent = "Profile saved on this device.";
    m.classList.add("ok");
  };

  $("#btn-pf-password").onclick = () => {
    const m = $("#pf-msg");
    m.hidden = false;
    m.classList.remove("ok");
    m.textContent =
      "Password changes use Cognito: sign out, then use Sign up/Verify flow, or ask an admin to reset.";
  };

  function setToggle(el, on) {
    el.dataset.on = on ? "1" : "0";
    el.setAttribute("aria-pressed", on ? "true" : "false");
  }
  document.querySelectorAll(".pref-toggle").forEach((btn) => {
    btn.onclick = () => setToggle(btn, btn.dataset.on !== "1");
  });
  $("#btn-tfa").onclick = () => {
    const m = $("#pf-msg");
    m.hidden = false;
    m.textContent = "Two-factor auth is not enabled in this Cognito pool yet.";
  };
  $("#pref-theme-light").onclick = () => {
    setTheme("light");
    $("#pref-theme-light").classList.add("active");
    $("#pref-theme-dark").classList.remove("active");
  };
  $("#pref-theme-dark").onclick = () => {
    setTheme("dark");
    $("#pref-theme-dark").classList.add("active");
    $("#pref-theme-light").classList.remove("active");
  };

  $("#btn-pf-delete").onclick = () => {
    $("#delete-confirm-input").value = "";
    $("#delete-modal-ok").disabled = true;
    $("#delete-modal").classList.remove("hidden");
  };
  $("#delete-modal-cancel").onclick = () =>
    $("#delete-modal").classList.add("hidden");
  $("#delete-modal-scrim").onclick = () =>
    $("#delete-modal").classList.add("hidden");
  $("#delete-confirm-input").oninput = (e) => {
    $("#delete-modal-ok").disabled = e.target.value.trim() !== "DELETE";
  };
  $("#delete-modal-ok").onclick = async () => {
    if ($("#delete-confirm-input").value.trim() !== "DELETE") return;
    try {
      await api("/api/auth/delete-profile", {
        method: "POST",
        body: "{}",
      });
      localStorage.removeItem("dlqj_profile");
      $("#delete-modal").classList.add("hidden");
      leaveApp();
      showAuthMsg("Profile deleted. You can create a new account.", true);
      setTab("signup");
    } catch (err) {
      showAuthMsg(err.message);
      $("#delete-modal").classList.add("hidden");
    }
  };

  function statusOf(m) {
    if (m.override) return { label: "Overridden", color: "var(--br)" };
    if (m.action === "discard_duplicate" && (m.confidence == null || m.confidence < 0.9)) {
      return { label: "Blocked · held in DLQ", color: "var(--a-quar)" };
    }
    if (m.action === "escalate_human") return { label: "Flagged", color: "var(--a-esc)" };
    if (m.status === "applied") return { label: "Applied", color: "var(--ok)" };
    if (m.status === "failed") return { label: "Failed", color: "var(--a-esc)" };
    if (m.status === "skipped") return { label: "Skipped", color: "var(--faint)" };
    return run && run.mode === "applied"
      ? { label: "Applied", color: "var(--ok)" }
      : { label: "Planned", color: "var(--faint)" };
  }

  function decidedBy(m) {
    const d = (m.decided_by || "").toLowerCase();
    if (d.includes("rule")) return { label: "Rule", color: "var(--muted)" };
    if (d.includes("bedrock") || m.bedrock) return { label: "Decider + Bedrock", color: "var(--br-ink)" };
    return { label: m.decided_by || "Decider", color: "var(--fg)" };
  }

  function renderSummary() {
    const qName = queueShort(run.queue || run.queue_name || run.dlq_arn);
    $("#queue-name").textContent = qName;
    $("#run-id").textContent = run.run_id || document.body.dataset.run || "—";

    const applied = run.mode === "applied";
    const pill = $("#mode-pill");
    pill.className = "pill " + (applied ? "pill-applied" : "pill-dry");
    pill.querySelector(".label").textContent = applied ? "Applied" : "Dry run";

    const counts = run.counts || {};
    const total = run.processed || messages.length || 0;
    const held =
      run.discard_held_count ||
      messages.filter(
        (m) => m.action === "discard_duplicate" && (m.confidence == null || m.confidence < 0.9)
      ).length;

    $("#summary-sub").textContent = `${total} messages · select a card to filter the table`;

    $("#summary-cards").innerHTML = ACTIONS.map((a) => {
      const meta = ACTION_META[a];
      const n = counts[a] || 0;
      const pct = total ? ((n / total) * 100).toFixed(1) : "0.0";
      const bar = total ? Math.min(100, (n / total) * 100) : 0;
      const note =
        a === "discard_duplicate" && held > 0
          ? `<div class="note"><span style="font-weight:600">⚠</span>${held} held: confidence &lt; 0.90</div>`
          : "";
      return `<button type="button" class="action-card" data-action="${a}">
        <div class="lab"><span class="swatch" style="background:${meta.color}"></span>${esc(meta.label)}</div>
        <div class="nums"><span class="n">${n}</span><span class="pct">${pct}%</span></div>
        <div class="desc">${esc(meta.desc)}${note}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${bar}%;background:${meta.color}"></div></div>
      </button>`;
    }).join("");

    $("#summary-cards").querySelectorAll(".action-card").forEach((btn) => {
      btn.onclick = () => {
        filterAction = btn.dataset.action;
        msgPage = 0;
        showView("messages");
        renderMessages();
      };
    });

    const scored = messages.filter((m) => m.confidence != null).length;
    const bedrockCalls = run.bedrock_calls ?? run.bedrock_call_count ?? "—";
    const medLat = run.median_latency_ms ?? run.latency_median_ms ?? "—";
    const p95 = run.p95_latency_ms ?? "—";

    $("#summary-stats").innerHTML = `
      <div class="stat-cell">
        <span class="lab">Messages processed</span>
        <span class="val">${total} <span>/ ${total || "—"}</span></span>
        <span class="hint">${scored} scored · ${Math.max(0, total - scored)} routed by rule</span>
      </div>
      <div class="stat-cell">
        <span class="lab">Median decision latency</span>
        <span class="val">${medLat} <span>ms</span></span>
        <span class="hint">p95 ${p95} ms</span>
      </div>
      <div class="stat-cell">
        <span class="lab">Bedrock calls</span>
        <span class="val">${bedrockCalls}</span>
        <span class="hint">vs ${total || 0} baseline</span>
      </div>
      <div class="stat-cell" style="justify-content:center;gap:8px">
        <div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)"><span>DLQ Judge</span><span class="mono" style="color:var(--fg)">${bedrockCalls}</span></div>
        <div style="height:6px;border-radius:3px;background:var(--sunk)"><div style="height:6px;width:${total ? Math.min(100, (Number(bedrockCalls) / total) * 100) : 0}%;border-radius:3px;background:var(--br)"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)"><span>Bedrock-only baseline</span><span class="mono" style="color:var(--fg)">${total || 0}</span></div>
        <div style="height:6px;border-radius:3px;background:var(--line)"><div style="height:6px;width:100%;border-radius:3px;background:var(--faint)"></div></div>
      </div>`;

    renderHistogram();

    const t = run.thresholds || {};
    const discardMin = t.discard_min ?? t.discard_confidence_min ?? 0.9;
    $("#sidebar-meta").innerHTML = `
      <div class="row"><span>Decider</span><span>${esc(run.decider_model || "—")}</span></div>
      <div class="row"><span>Bedrock</span><span>${esc(shortModel(run.bedrock_model_id))}</span></div>
      <div class="row"><span>Call cap</span><span>${esc(String(t.bedrock_max_calls ?? "—"))} / run</span></div>
      <div class="row"><span>Discard min</span><span>≥ ${esc(String(discardMin))} + idem key</span></div>`;

    fillDeployAccountChip();

    $("#meta-row").innerHTML = [
      run.source_queue ? `Source <b>${esc(queueShort(run.source_queue))}</b>` : null,
      `Account <b>${esc(DEPLOY_ACCOUNT)} · ${esc(DEPLOY_REGION)}</b>`,
      run.started_at ? `Started <b>${esc(formatTime(run.started_at))}</b>` : null,
      run.duration_s != null ? `Duration <b>${esc(String(run.duration_s))} s</b>` : null,
      run.quarantine_uri
        ? `Quarantine <b>${esc(run.quarantine_uri)}</b>`
        : null,
    ]
      .filter(Boolean)
      .map((x) => `<span>${x}</span>`)
      .join("");

    const btn = $("#btn-apply");
    const can = run.mode === "dry_run" && (run.actionable_count || 0) > 0;
    btn.disabled = !can;
    btn.textContent = applied ? "Actions applied · view audit log" : "Apply actions";
    btn.classList.toggle("btn-primary", !applied);
    if (applied) btn.classList.add("btn");

    $("#nav-msg-count").textContent = total ? String(total) : "";
    const cItems = (clusters && clusters.items) || [];
    $("#nav-cluster-count").textContent = cItems.length ? String(cItems.length) : "";
  }

  function shortModel(id) {
    if (!id) return "—";
    const s = String(id);
    if (s.includes(".")) return s.split(".").pop();
    return s.length > 24 ? s.slice(0, 22) + "…" : s;
  }

  function formatTime(iso) {
    try {
      const d = new Date(iso);
      return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
    } catch {
      return iso;
    }
  }

  function renderHistogram() {
    let hist = run.confidence_histogram || [];
    // Always rebuild from messages when present so UI matches live decisions
    // (bins: [0,0.30] + 0.30..1.00 in 0.025 steps → 28 bins, same as runlog).
    if (messages.length) {
      hist = Array(28).fill(0);
      messages.forEach((m) => {
        if (m.confidence == null) return;
        const c = Number(m.confidence);
        if (Number.isNaN(c)) return;
        let i;
        if (c < 0.3) i = 0;
        else if (c >= 1) i = 27;
        else i = Math.min(27, Math.floor((c - 0.3) / 0.025 + 1e-9));
        hist[i]++;
      });
    }
    if (!hist.length) {
      $("#summary-hist").innerHTML =
        '<div style="grid-column:1/-1;color:var(--muted);padding:20px">No confidence histogram yet — run triage.</div>';
      return;
    }
    while (hist.length < 28) hist.push(0);
    hist = hist.slice(0, 28);
    const max = Math.max(1, ...hist);
    const scored = hist.reduce((a, b) => a + b, 0);

    const bars = hist
      .map((n, i) => {
        const lo = 0.3 + i * 0.025;
        const bd = bandOf(lo + 0.001);
        const color =
          bd === "auto" ? "var(--fg)" : bd === "check" ? "var(--br)" : "var(--a-esc)";
        const h = n ? Math.max(6, (n / max) * 88) : 0;
        return `<div class="hist-bar" title="${lo.toFixed(3)}–${(lo + 0.025).toFixed(3)}: ${n} messages">
          <span class="cnt">${n ? n : ""}</span>
          <div class="fill" style="height:${h}%;background:${color}"></div>
        </div>`;
      })
      .join("");

    const bc = (k) => messages.filter((m) => bandOf(m.confidence) === k).length;
    const bands = [
      { label: "≥ 0.85 · auto-act", count: bc("auto"), color: "var(--fg)", desc: "Decider acts alone" },
      { label: "0.60–0.85 · Bedrock check", count: bc("check"), color: "var(--br)", desc: "Acts only if Bedrock agrees" },
      { label: "< 0.60 · escalate", count: bc("low"), color: "var(--a-esc)", desc: "Left in DLQ for a human" },
      { label: "Missing attributes", count: bc("none"), color: "var(--faint)", desc: "Escalated by rule, Decider not called" },
    ];

    $("#summary-hist").innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
        <div>
          <h2 style="margin:0;font-size:14px;font-weight:600">Confidence distribution</h2>
          <div style="font-size:12px;color:var(--muted)">Decider top-option probability per message · 0.025 bins · ${scored} scored</div>
        </div>
        <div class="hist-chart">
          <div class="hist-band" style="left:0;width:42.857%;background:color-mix(in oklch, var(--a-esc) 6%, transparent)"></div>
          <div class="hist-band" style="left:42.857%;width:35.714%;background:color-mix(in oklch, var(--br) 6%, transparent)"></div>
          <div class="hist-band" style="left:78.571%;right:0;background:color-mix(in oklch, var(--ok) 6%, transparent)"></div>
          <div class="hist-band-label" style="left:0;width:42.857%;color:var(--a-esc-ink)">&lt; 0.60 · escalate</div>
          <div class="hist-band-label" style="left:42.857%;width:35.714%;color:var(--br-ink)">0.60–0.85 · Bedrock check</div>
          <div class="hist-band-label" style="left:78.571%;right:0;color:var(--ok-ink)">≥ 0.85 · auto-act</div>
          <div class="hist-guide" style="left:42.857%;border-color:var(--br)"></div>
          <div class="hist-guide" style="left:78.571%;border-color:var(--ok)"></div>
          <div class="hist-bars">${bars}</div>
        </div>
        <div class="hist-axis">
          <span style="left:0">0.30</span>
          <span style="left:14.286%;transform:translateX(-50%)">0.40</span>
          <span style="left:28.571%;transform:translateX(-50%)">0.50</span>
          <span style="left:42.857%;transform:translateX(-50%);color:var(--br-ink)">0.60</span>
          <span style="left:57.143%;transform:translateX(-50%)">0.70</span>
          <span style="left:71.429%;transform:translateX(-50%)">0.80</span>
          <span style="left:78.571%;transform:translateX(-50%);color:var(--ok-ink)">0.85</span>
          <span style="right:0">1.00</span>
        </div>
      </div>
      <div class="band-side">
        <div style="font-size:12px;color:var(--muted)">Confidence policy</div>
        ${bands
          .map(
            (bd) => `<div class="band-row">
            <div class="top"><span class="lab"><span class="swatch" style="background:${bd.color}"></span>${esc(bd.label)}</span><span class="n">${bd.count}</span></div>
            <span class="desc">${esc(bd.desc)}</span>
          </div>`
          )
          .join("")}
      </div>`;
  }

  function filteredMessages() {
    const q = ($("#msg-search").value || "").toLowerCase();
    const fs = $("#filter-status").value;
    const fb = $("#filter-band").value;
    return messages.filter((m) => {
      if (filterAction && m.action !== filterAction) return false;
      if (fs && m.status !== fs) return false;
      if (fb && bandOf(m.confidence) !== fb) return false;
      if (!q) return true;
      return (
        (m.message_id || "").toLowerCase().includes(q) ||
        (m.error_type || "").toLowerCase().includes(q) ||
        (m.error_text || "").toLowerCase().includes(q)
      );
    });
  }

  function renderActionFilters() {
    const counts = {};
    ACTIONS.forEach((a) => (counts[a] = 0));
    messages.forEach((m) => {
      if (counts[m.action] != null) counts[m.action]++;
    });
    const all = [{ key: "", label: "All", color: "var(--fg)", count: messages.length }];
    const chips = all.concat(
      ACTIONS.map((a) => ({
        key: a,
        label: ACTION_META[a].label,
        color: ACTION_META[a].color,
        count: counts[a],
      }))
    );
    $("#action-filters").innerHTML = chips
      .map((f) => {
        const active = filterAction === f.key;
        return `<button type="button" class="fchip${active ? " active" : ""}" data-action="${esc(f.key)}">
          <span class="swatch" style="background:${f.color}"></span>${esc(f.label)}
          <span class="cnt">${f.count}</span>
        </button>`;
      })
      .join("");
    $("#action-filters").querySelectorAll(".fchip").forEach((b) => {
      b.onclick = () => {
        filterAction = b.dataset.action || "";
        msgPage = 0;
        renderMessages();
      };
    });
  }

  function renderMessages() {
    renderActionFilters();
    const rows = filteredMessages();
    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (msgPage >= pageCount) msgPage = pageCount - 1;
    const slice = rows.slice(msgPage * PAGE_SIZE, msgPage * PAGE_SIZE + PAGE_SIZE);

    const hasFilters =
      filterAction ||
      $("#filter-status").value ||
      $("#filter-band").value ||
      ($("#msg-search").value || "").trim();
    $("#btn-clear-filters").classList.toggle("hidden", !hasFilters);

    $("#msg-showing").textContent = `Showing ${slice.length ? msgPage * PAGE_SIZE + 1 : 0}–${msgPage * PAGE_SIZE + slice.length} of ${rows.length}`;
    $("#page-label").textContent = `Page ${msgPage + 1} of ${pageCount}`;
    $("#btn-prev-page").disabled = msgPage <= 0;
    $("#btn-next-page").disabled = msgPage >= pageCount - 1;

    if (!slice.length) {
      $("#msg-rows").innerHTML = `<div class="msg-empty">No messages match these filters.</div>`;
      return;
    }

    $("#msg-rows").innerHTML = slice
      .map((m) => {
        const meta = ACTION_META[m.action] || ACTION_META.escalate_human;
        const conf = m.confidence;
        const confPct = conf == null ? 0 : Math.round(conf * 100);
        const st = statusOf(m);
        const by = decidedBy(m);
        const warn =
          m.action === "discard_duplicate" && (conf == null || conf < 0.9);
        const sel = selectedId === m.message_id ? " selected" : "";
        return `<div class="msg-row${sel}" data-id="${esc(m.message_id)}">
          <span class="id" title="${esc(m.message_id)}">${esc(shortId(m.message_id))}</span>
          <span class="err">${esc(m.error_type || "—")}</span>
          <span class="recv">${m.receive_count ?? ""}</span>
          <span style="display:flex;align-items:center;gap:6px">
            <span class="action-chip" style="background:${chipBg(meta.color)};color:${meta.ink}">
              <span class="dot" style="background:${meta.color}"></span>${esc(meta.label)}
            </span>
            ${warn ? `<span class="warn-badge" title="Discard below 0.90 confidence">⚠ &lt;0.90</span>` : ""}
          </span>
          <span class="conf-cell">
            <span class="conf-bar">
              <span class="fill" style="width:${confPct}%;background:${confColor(conf)}"></span>
              <span class="mk mk60"></span><span class="mk mk85"></span>
            </span>
            <span class="conf-txt">${conf == null ? "—" : conf.toFixed(2)}</span>
          </span>
          <span style="font-size:12px;color:${by.color}">${esc(by.label)}</span>
          <span class="status-cell"><span class="dot" style="background:${st.color}"></span>${esc(st.label)}</span>
        </div>`;
      })
      .join("");

    $("#msg-rows").querySelectorAll(".msg-row").forEach((tr) => {
      tr.onclick = () => openDrawer(tr.dataset.id);
    });
  }

  async function openDrawer(id) {
    selectedId = id;
    const d = await api(`/api/messages/${encodeURIComponent(id)}`);
    const root = $("#drawer-root");
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");

    const meta = ACTION_META[d.action] || ACTION_META.escalate_human;
    const st = statusOf(d);
    const by = decidedBy(d);
    $("#drawer-id").textContent = id;
    $("#drawer-chips").innerHTML = `
      <span class="action-chip" style="background:${chipBg(meta.color)};color:${meta.ink};padding:3px 9px;font-size:12.5px">
        <span class="dot" style="background:${meta.color};width:7px;height:7px"></span>${esc(meta.label)}
      </span>
      <span class="status-cell muted"><span class="dot" style="background:${st.color}"></span>${esc(st.label)}</span>
      <span class="muted" style="font-size:12px">· ${esc(by.label)}${d.latency_ms != null ? ` · ${d.latency_ms} ms` : ""}</span>`;

    const warn =
      d.action === "discard_duplicate" && (d.confidence == null || d.confidence < 0.9);
    const probs = d.probabilities || {};
    const scored = Object.keys(probs).length > 0 || d.confidence != null;

    let attrs = [];
    const stObj = d.state || {};
    const rawAttrs = stObj.attributes || stObj.error_attributes || d.attributes || {};
    if (rawAttrs && typeof rawAttrs === "object" && !Array.isArray(rawAttrs)) {
      attrs = Object.entries(rawAttrs).map(([k, v]) => ({
        k,
        v: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
      }));
    }
    if (!attrs.length) {
      [
        ["error_type", d.error_type || stObj.error_type],
        ["error_message", d.error_text || stObj.error_text || stObj.error_message],
        ["receive_count", d.receive_count ?? stObj.receive_count],
        ["idempotency_key", stObj.idempotency_key || d.idempotency_key],
        ["band", d.band],
        ["reason", d.reason],
      ].forEach(([k, v]) => {
        if (v != null && v !== "") attrs.push({ k, v: String(v) });
      });
    }

    let body = stObj.body_masked || d.body_masked || "";
    try {
      body = JSON.stringify(JSON.parse(body), null, 2);
    } catch (_) {}

    const br = d.bedrock;
    const probKeys = ACTIONS.filter((a) => probs[a] != null);
    if (!probKeys.length && d.confidence != null) {
      // synthesize single bar for chosen action
    }

    let probHtml = "";
    if (scored && (probKeys.length || d.confidence != null)) {
      const entries = probKeys.length
        ? probKeys.map((a) => [a, probs[a]])
        : [[d.action, d.confidence]];
      entries.sort((a, b) => (b[1] || 0) - (a[1] || 0));
      probHtml = `<div style="display:flex;flex-direction:column;gap:7px">
        ${entries
          .map(([a, v]) => {
            const m = ACTION_META[a] || ACTION_META.escalate_human;
            const w = Math.round((v || 0) * 100);
            const top = a === d.action;
            return `<div class="prob-row">
              <span style="font-size:12.5px;font-weight:${top ? 600 : 400};display:flex;align-items:center;gap:6px">
                <span style="width:7px;height:7px;border-radius:2px;background:${m.color}"></span>${esc(m.label)}
              </span>
              <span class="prob-track">
                <span class="fill" style="width:${w}%;background:${m.color};opacity:${top ? 1 : 0.45}"></span>
                <span class="mk" style="left:60%"></span><span class="mk" style="left:85%"></span>
              </span>
              <span class="mono" style="font-size:12px;text-align:right;font-weight:${top ? 600 : 400}">${(v ?? 0).toFixed(2)}</span>
            </div>`;
          })
          .join("")}
        <div class="prob-row" style="font-family:var(--mono);font-size:10px;color:var(--faint)">
          <span></span>
          <span style="position:relative;height:12px">
            <span style="position:absolute;left:60%;transform:translateX(-50%)">0.60</span>
            <span style="position:absolute;left:85%;transform:translateX(-50%)">0.85</span>
          </span>
          <span></span>
        </div>
      </div>`;
    } else {
      probHtml = `<div style="padding:12px;border:1px dashed var(--line2);border-radius:8px;font-size:12.5px;color:var(--muted)">Decider was not called or probabilities are unavailable.</div>`;
    }

    let brHtml = "";
    if (br) {
      const agree = br.agree !== false && br.verdict !== "disagree";
      const pick = br.pick || br.action || br.chosen_action || "—";
      const reason = br.reason || br.rationale || br.text || "";
      const verdict = agree ? "Agrees" : "Disagrees";
      const vColor = agree ? "var(--ok-ink)" : "var(--a-esc-ink)";
      const pickLabel = ACTION_META[pick]?.label || pick;
      brHtml = `<div class="bedrock-card">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <span style="display:flex;align-items:center;gap:7px;font-size:12px;font-weight:600;color:var(--br-ink)">
            <span style="width:7px;height:7px;border-radius:50%;background:var(--br)"></span>Bedrock second opinion
          </span>
          <span style="font-size:11.5px;font-weight:600;color:${vColor}">${verdict}</span>
        </div>
        <div style="font-size:12.5px">Picked <b style="font-weight:600">${esc(pickLabel)}</b>${reason ? ` — ${esc(reason)}` : ""}</div>
        <div style="font-size:11px;color:var(--muted);font-family:var(--mono)">${esc(br.model_id || br.model || "")}</div>
      </div>`;
    }

    $("#drawer-body").innerHTML = `
      ${
        warn
          ? `<div class="drawer-warn"><span style="font-weight:700;color:var(--a-quar-ink)">⚠</span>
          <div style="display:flex;flex-direction:column;gap:2px">
            <span style="font-weight:600;color:var(--a-quar-ink)">Discard below 0.90 confidence</span>
            <span style="font-size:12px">Allowed but risky (OQ-09). Override still logged to the audit trail.</span>
          </div></div>`
          : ""
      }
      <div style="display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <h3 style="margin:0;font-size:13px;font-weight:600">Decider probabilities</h3>
          <span style="font-size:11.5px;color:var(--muted)">${esc(d.path || d.band || "")}</span>
        </div>
        ${probHtml}
      </div>
      ${brHtml}
      <div style="display:flex;flex-direction:column;gap:8px">
        <h3 style="margin:0;font-size:13px;font-weight:600">Error attributes</h3>
        <div class="attrs-table">
          ${
            attrs.length
              ? attrs
                  .map(
                    (at) => `<div class="attr-row"><span class="k">${esc(at.k)}</span><span class="v">${esc(at.v)}</span></div>`
                  )
                  .join("")
              : `<div class="attr-row"><span class="k">—</span><span class="v" style="color:var(--muted)">No attributes</span></div>`
          }
        </div>
      </div>
      ${
        d.reason
          ? `<div style="display:flex;flex-direction:column;gap:6px">
              <h3 style="margin:0;font-size:13px;font-weight:600">Reason</h3>
              <div style="font-size:13px;text-wrap:pretty">${esc(d.reason)}</div>
            </div>`
          : ""
      }
      <div style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <h3 style="margin:0;font-size:13px;font-weight:600">Message body</h3>
          <span style="font-size:11.5px;color:var(--muted)">PII masked before leaving this machine</span>
        </div>
        <pre class="body-pre">${esc(body || "(empty)")}</pre>
      </div>`;

    const can =
      run.mode === "dry_run" &&
      (d.status === "planned" || d.status === "failed" || !d.status);
    $("#drawer-foot").innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <span style="font-size:12px;font-weight:600">Override action</span>
        <span style="font-size:11.5px;color:var(--muted)">Logged to the audit trail</span>
      </div>
      <div class="override-grid" id="override-btns"></div>
      <p id="override-warn" class="auth-msg" hidden style="margin:0"></p>
      <div id="override-revert"></div>`;

    const row = $("#override-btns");
    ACTIONS.forEach((a) => {
      const m = ACTION_META[a];
      const b = document.createElement("button");
      b.type = "button";
      b.disabled = !can;
      if (a === d.action) b.classList.add("active");
      b.innerHTML = `<span class="bar" style="background:${m.color}"></span>${esc(m.label)}`;
      b.style.borderColor = a === d.action ? "var(--fg)" : "var(--line2)";
      b.onclick = async () => {
        if (a === "discard_duplicate" && (d.confidence || 0) < 0.9) {
          $("#override-warn").hidden = false;
          $("#override-warn").textContent =
            "Discard below 0.90 — allowed but risky (OQ-09).";
        }
        await api(`/api/messages/${encodeURIComponent(id)}/override`, {
          method: "POST",
          body: JSON.stringify({ action: a }),
        });
        await reload();
        openDrawer(id);
      };
      row.appendChild(b);
    });
    if (d.override) {
      const rev = document.createElement("button");
      rev.type = "button";
      rev.className = "btn-ghost";
      rev.textContent = `Revert to model decision (${ACTION_META[d.override.original_action || d.original_action]?.label || "original"})`;
      rev.onclick = async () => {
        await api(`/api/messages/${encodeURIComponent(id)}/override`, {
          method: "POST",
          body: JSON.stringify({ revert: true }),
        });
        await reload();
        openDrawer(id);
      };
      $("#override-revert").appendChild(rev);
    }
    renderMessages();
  }

  function closeDrawer() {
    selectedId = null;
    $("#drawer-root").classList.add("hidden");
    $("#drawer-root").setAttribute("aria-hidden", "true");
    renderMessages();
  }
  $("#drawer-close").onclick = closeDrawer;
  $("#drawer-scrim").onclick = closeDrawer;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawer();
      $("#modal").classList.add("hidden");
    }
  });

  function renderClusters() {
    const items = (clusters && clusters.items) || [];
    const qCount = items.reduce((s, c) => s + (c.count || 0), 0);
    $("#cluster-sub").textContent = items.length
      ? `${qCount} quarantined · ${items.length} clusters`
      : "No clusters";
    if (!items.length) {
      $("#cluster-list").innerHTML = `<div class="muted" style="padding:20px">No failure clusters for this run.</div>`;
      return;
    }
    $("#cluster-list").innerHTML = items
      .map((c) => {
        const claims = c.claims || [];
        const claimHtml = claims.length
          ? `<ol class="claim-list">${claims
              .map((x, i) => {
                const text = typeof x === "string" ? x : x.text || "";
                const unverified = typeof x === "object" && x.unverified;
                const cites = (typeof x === "object" && x.cites) || [];
                return `<li>
                  <span class="mono" style="font-size:11px;color:var(--faint);padding-top:2px">${i + 1}</span>
                  <div style="display:flex;flex-direction:column;gap:5px">
                    <span style="font-size:13.5px;text-wrap:pretty">${esc(text)}</span>
                    <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
                      ${unverified || c.unverified ? `<span class="unverified">Unverified · no cited evidence</span>` : ""}
                      ${(cites || [])
                        .map(
                          (ci) =>
                            `<button type="button" class="sample" data-id="${esc(ci)}" style="font-family:var(--mono);font-size:10.5px;padding:1px 6px;border-radius:4px;border:0;background:color-mix(in oklch, var(--br) 12%, transparent);color:var(--br-ink);cursor:pointer">${esc(shortId(ci))}</button>`
                        )
                        .join("")}
                    </div>
                  </div>
                </li>`;
              })
              .join("")}</ol>`
          : `<p style="font-size:13.5px">${esc(c.root_cause || "—")}${c.unverified ? ' <span class="unverified">Unverified</span>' : ""}</p>`;

        return `<article class="cluster-card">
          <div class="cluster-left">
            <div style="display:flex;flex-direction:column;gap:4px">
              <span class="action-chip" style="align-self:flex-start;background:color-mix(in oklch, var(--a-quar) 18%, transparent);color:var(--a-quar-ink)">
                <span class="dot" style="background:var(--a-quar)"></span>Quarantine
              </span>
              <span class="cluster-err">${esc(c.error_type || "—")}</span>
              <span style="font-size:12px;color:var(--muted);font-family:var(--mono)">${esc(c.sample_error_text || "")}</span>
            </div>
            <div style="display:flex;align-items:baseline;gap:8px">
              <span style="font-size:30px;font-weight:500;letter-spacing:-0.02em">${c.count ?? 0}</span>
              <span style="font-size:12px;color:var(--muted)">messages · ${c.pct_of_quarantined ?? "—"}% of quarantined</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px">
              <span style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint)">Sample IDs</span>
              <div class="sample-ids">${(c.sample_ids || [])
                .map(
                  (id) =>
                    `<button type="button" class="sample" data-id="${esc(id)}">${esc(shortId(id))}</button>`
                )
                .join("")}</div>
            </div>
          </div>
          <div class="cluster-right">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="width:8px;height:8px;border-radius:50%;background:var(--br)"></span>
              <span style="font-size:12px;font-weight:600;color:var(--br-ink)">Bedrock root-cause summary</span>
            </div>
            ${claimHtml}
            <div class="fix-box">
              <span class="lab">Suggested fix</span>
              <span style="font-size:13px;text-wrap:pretty">${esc(c.suggested_fix || "—")}</span>
            </div>
          </div>
        </article>`;
      })
      .join("");

    document.querySelectorAll(".sample").forEach((b) => {
      b.onclick = () => openDrawer(b.dataset.id);
    });
  }

  function renderBench() {
    const approaches = (benchmark && benchmark.approaches) || [];
    if (!approaches.length) {
      $("#bench-root").innerHTML = `
        <div class="section-head">
          <div><h2>Benchmark</h2><div class="muted" style="margin-top:4px">No measured benchmark results on this deploy yet.</div></div>
        </div>`;
      return;
    }

    const metrics = [
      ["accuracy", "Accuracy", "Share of labelled messages with the correct action", true],
      ["unsafe_action_rate", "Unsafe-action rate", "Incorrect redrive / discard / quarantine", false],
      ["median_latency_ms", "Median latency", "End-to-end decision time", false],
      ["p95_latency_ms", "p95 latency", "Tail latency", false],
      ["bedrock_calls_per_1000", "Bedrock calls / 1,000", "Cost proxy", false],
    ];

    const head = approaches
      .map(
        (a, i) =>
          `<div style="background:${i === approaches.length - 1 ? "color-mix(in oklch, var(--br) 6%, transparent)" : "transparent"}">
            <span style="font-weight:600;font-size:13.5px;display:block">${esc(a.name)}</span>
            <span style="font-size:11.5px;color:var(--muted)">${esc(a.how || a.description || "")}</span>
          </div>`
      )
      .join("");

    const rows = metrics
      .map(([key, label, hint, higherBetter]) => {
        const vals = approaches.map((a) => a[key]);
        const numeric = vals.map((v) => (typeof v === "number" ? v : NaN));
        let bestIdx = -1;
        if (numeric.every((n) => !Number.isNaN(n))) {
          bestIdx = higherBetter
            ? numeric.indexOf(Math.max(...numeric))
            : numeric.indexOf(Math.min(...numeric));
        }
        const maxAbs = Math.max(1, ...numeric.filter((n) => !Number.isNaN(n)).map(Math.abs));
        const cells = vals
          .map((v, i) => {
            const num = typeof v === "number" ? v : null;
            let display = v ?? "—";
            let sub = "";
            if (key.includes("latency") && num != null) {
              display = Math.round(num);
              sub = "ms";
            } else if (key === "accuracy" && num != null) {
              display = (num <= 1 ? num * 100 : num).toFixed(1) + "%";
            } else if (key === "unsafe_action_rate" && num != null) {
              display = (num <= 1 ? num * 100 : num).toFixed(1) + "%";
            }
            const w =
              num == null
                ? 0
                : key === "accuracy"
                  ? Math.min(100, (num <= 1 ? num * 100 : num))
                  : Math.min(100, (Math.abs(num) / maxAbs) * 100);
            const color =
              i === approaches.length - 1 ? "var(--br)" : i === 0 ? "var(--faint)" : "var(--a-now)";
            return `<div style="display:flex;flex-direction:column;gap:7px;justify-content:center;background:${i === approaches.length - 1 ? "color-mix(in oklch, var(--br) 4%, transparent)" : "transparent"}">
              <div style="display:flex;align-items:baseline;gap:8px">
                <span style="font-size:18px;font-weight:500;font-variant-numeric:tabular-nums">${esc(String(display))}</span>
                <span style="font-size:11.5px;color:var(--muted)">${esc(sub)}</span>
                ${i === bestIdx ? `<span class="best-tag">Best</span>` : ""}
              </div>
              <div class="bench-cell-bar"><i style="width:${w}%;background:${color}"></i></div>
            </div>`;
          })
          .join("");
        return `<div class="bench-row">
          <div style="display:flex;flex-direction:column;gap:2px">
            <span style="font-weight:500">${esc(label)}</span>
            <span style="font-size:11.5px;color:var(--muted)">${esc(hint)}</span>
          </div>
          ${cells}
        </div>`;
      })
      .join("");

    const perType = benchmark.per_type || benchmark.accuracy_by_type || [];
    let perTypeHtml = "";
    if (perType.length) {
      perTypeHtml = `<div class="panel" style="margin-top:20px">
        <div><h3 style="margin:0;font-size:13.5px;font-weight:600">Accuracy by failure type</h3>
        <span class="muted" style="font-size:12px">${approaches.map((a) => a.name).join(" · ")}</span></div>
        <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
          ${perType
            .map((pt) => {
              const cells = approaches.map((a, i) => {
                const v = (pt[a.key || a.name] ?? pt.values?.[i] ?? 0);
                const pct = v <= 1 ? Math.round(v * 100) : Math.round(v);
                const color =
                  i === approaches.length - 1 ? "var(--br)" : i === 0 ? "var(--faint)" : "var(--a-now)";
                return `<span style="display:flex;align-items:center;gap:8px;padding-right:14px">
                  <span style="flex:1;height:6px;border-radius:3px;background:var(--sunk)"><span style="display:block;height:6px;border-radius:3px;width:${pct}%;background:${color}"></span></span>
                  <span class="mono" style="font-size:12px;width:34px;text-align:right">${pct}%</span>
                </span>`;
              });
              return `<div style="display:grid;grid-template-columns:190px repeat(${approaches.length},minmax(0,1fr));align-items:center">
                <span class="mono" style="font-size:12px">${esc(pt.type || pt.error_type || "")}</span>
                ${cells.join("")}
              </div>`;
            })
            .join("")}
        </div>
      </div>`;
    }

    $("#bench-root").innerHTML = `
      <div class="section-head" style="margin-bottom:16px">
        <div>
          <h2>Benchmark</h2>
          <div class="muted" style="margin-top:4px">Same labelled messages for all approaches · results shown as measured</div>
        </div>
      </div>
      <div class="bench-table">
        <div class="bench-row" style="border-bottom:1px solid var(--line)">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);align-self:end">Metric</div>
          ${head}
        </div>
        ${rows}
      </div>
      ${perTypeHtml}`;
  }

  $("#btn-export").onclick = () => {
    const blob = new Blob(
      [JSON.stringify({ run, messages, clusters }, null, 2)],
      { type: "application/json" }
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `dlqj-report-${run.run_id || "run"}.json`;
    a.click();
  };

  async function pollJob(jobId) {
    const el = $("#job-status");
    for (;;) {
      const j = await api(`/api/jobs/${jobId}`);
      el.textContent = `${j.kind}: ${j.status} ${j.progress || 0}% ${j.message || ""}`;
      if (j.status === "succeeded" || j.status === "failed") return j;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  $("#btn-set-queue").onclick = async () => {
    try {
      await api("/api/queue", {
        method: "POST",
        body: JSON.stringify({ dlq_arn: $("#queue-arn").value.trim() }),
      });
      $("#job-status").textContent = "queue set";
    } catch (err) {
      $("#job-status").textContent = err.message;
    }
  };

  $("#btn-triage").onclick = async () => {
    try {
      const { job_id } = await api("/api/jobs/triage", {
        method: "POST",
        body: "{}",
      });
      const j = await pollJob(job_id);
      if (j.status === "succeeded" && j.result && j.result.run_id) {
        location.reload();
      }
    } catch (err) {
      $("#job-status").textContent = err.message;
    }
  };

  $("#btn-apply").onclick = () => {
    if (run.mode === "applied") return;
    const counts = run.counts || {};
    const n = run.actionable_count || 0;
    $("#modal-title").textContent = `Apply ${n} actions to ${queueShort(run.queue)}?`;
    $("#modal-sub").innerHTML = `Equivalent to re-running with <code class="mono">--apply</code>. Every action is written to the audit log.`;
    $("#modal-body").innerHTML =
      ACTIONS.filter((a) => a !== "escalate_human")
        .map((a) => {
          const m = ACTION_META[a];
          return `<div class="apply-row">
            <span class="lab"><span class="swatch" style="background:${m.color}"></span>${esc(m.label)}
              <span style="color:var(--muted);font-size:11.5px">${esc(m.dest)}</span></span>
            <span class="mono">${counts[a] || 0}</span>
          </div>`;
        })
        .join("") +
      `<div style="font-size:12px;color:var(--muted);padding-top:10px">Escalated held: ${
        counts.escalate_human || 0
      }; discard held: ${run.discard_held_count || 0}</div>`;
    $("#modal-ok").textContent = `Apply ${n} actions`;
    $("#modal").classList.remove("hidden");
  };
  $("#modal-cancel").onclick = () => $("#modal").classList.add("hidden");
  $("#modal-scrim").onclick = () => $("#modal").classList.add("hidden");
  $("#modal-ok").onclick = async () => {
    $("#modal").classList.add("hidden");
    const btn = $("#btn-apply");
    btn.disabled = true;
    btn.textContent = "Applying…";
    try {
      const resp = await api("/api/run/apply", {
        method: "POST",
        body: JSON.stringify({
          confirm: "APPLY",
          expected_actionable_count: run.actionable_count,
        }),
      });
      if (resp.job_id) await pollJob(resp.job_id);
      await reload();
    } catch (err) {
      $("#page-error").hidden = false;
      $("#page-error").textContent = err.message;
      btn.textContent = "Apply actions";
      btn.disabled = false;
    }
  };

  async function reload() {
    run = await api("/api/run");
    const msg = await api("/api/messages");
    messages = msg.items || [];
    clusters = await api("/api/clusters");
    try {
      benchmark = await api("/api/benchmark");
      if (benchmark && benchmark.sample_data) {
        benchmark = { sample_data: false, approaches: [] };
      }
    } catch (_) {
      benchmark = { sample_data: false, approaches: [] };
    }
    const fs = $("#filter-status");
    if (fs.options.length <= 1) {
      ["planned", "applied", "skipped", "failed"].forEach((s) => {
        const o = document.createElement("option");
        o.value = s;
        o.textContent = s;
        fs.appendChild(o);
      });
    }
    updateProfile();
    renderSummary();
    renderMessages();
    renderClusters();
    renderBench();
  }

  $("#msg-search").oninput = () => {
    msgPage = 0;
    renderMessages();
  };
  $("#filter-status").onchange = () => {
    msgPage = 0;
    renderMessages();
  };
  $("#filter-band").onchange = () => {
    msgPage = 0;
    renderMessages();
  };
  $("#btn-clear-filters").onclick = () => {
    filterAction = "";
    $("#msg-search").value = "";
    $("#filter-status").value = "";
    $("#filter-band").value = "";
    msgPage = 0;
    renderMessages();
  };
  $("#btn-prev-page").onclick = () => {
    if (msgPage > 0) {
      msgPage--;
      renderMessages();
    }
  };
  $("#btn-next-page").onclick = () => {
    msgPage++;
    renderMessages();
  };

  async function enterApp() {
    document.body.classList.remove("login-only", "auth-open");
    document.body.classList.add("authed");
    authGate.classList.add("hidden");
    if (siteLanding) siteLanding.classList.add("hidden");
    app.classList.remove("hidden");
    fillDeployAccountChip();
    updateProfile();
    try {
      await reload();
      const start = $("#pref-start")?.value || "summary";
      showView(start === "messages" || start === "clusters" ? start : "summary");
    } catch (err) {
      if (err.status === 401) {
        leaveApp();
        openAuth("login");
        showAuthMsg("Session expired — log in again.");
      } else {
        $("#page-error").hidden = false;
        $("#page-error").textContent = err.message;
      }
    }
  }

  // Marketing landing first; enter app only with a valid token.
  fillDeployAccountChip();
  if (idToken) {
    enterApp();
  } else {
    showLanding();
    loadPublicStats();
  }
})();
