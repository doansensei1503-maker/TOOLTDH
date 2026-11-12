/* TOOLTDH dashboard — talks to the real backend API. No mock data. */
"use strict";

const API = "/api";
const state = {
  view: "overview",
  overview: null,
  reviews: [],
  candidates: [],
  scores: [],
  rejected: [],
  selected: null,
  selectedScore: null,
  eligibility: null,
  result: null,
  status: "IDLE",
  jobId: "",
  lastDetailButton: null,
  approvals: [],
  jobs: [],
  pollTimer: null,
  analyses: [],
  previewUrl: "",
};

/* ------------------------------------------------------------ helpers */

async function api(path, options) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  if (!res.ok) {
    const message = (data && data.error) || `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
}

function el(id) { return document.getElementById(id); }

function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function num(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US");
}

/** A metric the source did not publish is shown as "Không có dữ liệu", never as 0. */
function metric(value, known) {
  if (known === false) return '<span class="muted" title="Nguồn không cung cấp chỉ số này">Không có dữ liệu</span>';
  return num(value);
}

function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return esc(value);
  return d.toLocaleString("vi-VN", { hour12: false });
}

function toast(message, kind) {
  const wrap = el("toasts");
  const node = document.createElement("div");
  node.className = "toast" + (kind ? " " + kind : "");
  node.textContent = message;
  wrap.appendChild(node);
  setTimeout(() => node.remove(), 5200);
}

function setBadge(id, count) {
  const badge = el(id);
  if (!badge) return;
  badge.textContent = String(count);
  badge.hidden = !count;
}

function tag(text, kind) {
  return '<span class="tag' + (kind ? " tag-" + kind : "") + '">' + esc(text) + "</span>";
}

function emptyRow(colspan, text) {
  return '<tr><td colspan="' + colspan + '" class="empty">' + esc(text) + "</td></tr>";
}

/* ---------------------------------------------------------- routing */

const TITLES = {
  overview: ["Dashboard", "Trạng thái thật của hệ thống."],
  assistant: ["AI Assistant", "Trợ lý đọc trạng thái thật, không tự hành động."],
  discovery: ["TikTok Discovery", "Tìm video theo chủ đề, chỉ số thật từ nguồn."],
  trends: ["Trend Analyzer", "Điểm xu hướng và lý do mỗi video được chọn hoặc loại."],
  filter: ["Video Filter", "Mỗi lượt chỉ chọn một video tốt nhất."],
  caption: ["Caption & Hashtag Studio", "Soạn và sửa caption trước khi duyệt."],
  videos: ["Video Manager", "Thư viện video đã tải và đã xử lý."],
  editor: ["Video Editor", "Kiểm tra và cắt video bằng backend."],
  approval: ["Approval Center", "Duyệt tải video và duyệt đăng video là hai quyền riêng."],
  scheduler: ["Auto Scheduler", "Lịch chạy tự động, mỗi lượt một video."],
  studio: ["TikTok Studio", "Bản nháp. Không tự đăng công khai."],
  analytics: ["Analytics", "Thống kê hiệu quả từ dữ liệu thật."],
  history: ["History & Logs", "Lịch sử đăng bài và nhật ký hoạt động."],
  settings: ["Settings & Security", "Cấu hình và quyền truy cập."],
};

function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => {
    v.classList.toggle("active", v.dataset.view === name);
  });
  document.querySelectorAll(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
  const title = TITLES[name] || ["TOOLTDH", ""];
  el("view-title").textContent = title[0];
  el("view-sub").textContent = title[1];
  location.hash = name;
  loadView(name);
}

function loadView(name) {
  if (name === "overview") return loadOverview();
  if (name === "discovery") return loadDiscovery();
  if (name === "trends") return loadTrendView();
  if (name === "filter") return loadFilterView();
  if (name === "approval") return loadApprovals();
  if (name === "scheduler") return loadScheduler();
  if (name === "videos") return loadLibrary();
  if (name === "history") return loadHistory();
  if (name === "analytics") return loadAnalytics();
  if (name === "settings") return loadSettings();
  if (name === "studio") return loadStudio();
}

async function loadTrendView() {
  if (!state.result) await loadDiscovery();
  else renderTrends();
}

async function loadFilterView() {
  if (!state.result) await loadDiscovery();
  else renderFilter();
}

/* --------------------------------------------------------- overview */

async function loadOverview() {
  let data;
  try { data = await api("/overview"); } catch (e) { toast(e.message, "err"); return; }
  state.overview = data;

  el("mode-chip").textContent = "mode: " + (data.mode || "—");
  el("account-chip").textContent = "account: " + (data.expected_account || "—");

  const stopPill = el("stop-pill");
  stopPill.hidden = false;
  stopPill.querySelector(".dot").nextSibling.textContent = "";
  stopPill.childNodes[1].nodeValue = data.emergency_stop
    ? "Emergency stop active"
    : "Automation running";

  const c = data.counts || {};
  const cards = [
    ["Candidates", c.candidates, "video tìm thấy", "accent"],
    ["Chờ duyệt", c.awaiting_selection, "review mở", "warn"],
    ["Tasks", c.tasks, "tác vụ đã lưu", ""],
    ["Đã đăng", c.published, "bài trong history", "ok"],
    ["Thư viện", c.library, "video đã hash", ""],
    ["Blockers", (data.blockers || []).length, "cần xử lý", (data.blockers || []).length ? "danger" : ""],
  ];
  el("ov-stats").innerHTML = cards.map(([label, value, sub, kind]) =>
    '<div class="stat ' + (kind || "") + '">' +
    '<div class="stat-label">' + esc(label) + "</div>" +
    '<div class="stat-value">' + num(value) + "</div>" +
    '<div class="stat-sub">' + esc(sub) + "</div></div>"
  ).join("");

  el("ov-blocker-count").textContent = String((data.blockers || []).length);
  el("ov-blockers").innerHTML = (data.blockers || []).length
    ? (data.blockers || []).map((b) =>
        '<div class="notif"><div class="notif-kind">Blocker</div><div class="notif-msg">' +
        esc(b) + "</div></div>").join("")
    : '<div class="empty">Không có blocker.</div>';

  const s = data.schedule || {};
  el("ov-sched-state").textContent = s.enabled ? "đang bật" : "đang tắt";
  el("ov-sched-state").className = "tag " + (s.enabled ? "tag-ok" : "");
  el("ov-schedule").innerHTML =
    "<dl class='kv'>" +
    "<dt>Giờ chạy</dt><dd>" + esc(s.daily_time || "—") + "</dd>" +
    "<dt>Chủ đề</dt><dd>" + esc(s.topic || "—") + "</dd>" +
    "<dt>Lần chạy tiếp</dt><dd>" + esc(s.next_run || "—") + "</dd>" +
    "<dt>Số lượt đã chạy</dt><dd>" + num(s.run_count) + "</dd>" +
    "<dt>Lần gần nhất</dt><dd>" + esc((s.last_run && s.last_run.status) || "—") + "</dd>" +
    "</dl>";

  const tasks = data.recent_tasks || [];
  el("ov-tasks").innerHTML =
    "<thead><tr><th>Task</th><th>Trạng thái</th><th>Nguồn</th><th>Cập nhật</th></tr></thead><tbody>" +
    (tasks.length ? tasks.map((t) =>
      "<tr><td>" + esc(t.task_id) + "</td>" +
      "<td>" + tag(t.status || "—", statusKind(t.status)) + "</td>" +
      "<td class='muted'>" + esc(t.source_url || "—") + "</td>" +
      "<td class='muted'>" + esc(fmtDate(t.updated_at)) + "</td></tr>").join("")
      : emptyRow(4, "Chưa có tác vụ nào.")) +
    "</tbody>";
}

function statusKind(status) {
  const s = String(status || "").toUpperCase();
  if (["DRAFT_SAVED", "AWAITING_APPROVAL", "PUBLISHED", "COMPLETED"].includes(s)) return "ok";
  if (["BLOCKED", "FAILED", "REJECTED"].includes(s)) return "danger";
  if (["HOLD", "AWAITING_SELECTION", "SELECTED", "RUNNING"].includes(s)) return "warn";
  return "";
}

/* -------------------------------------------------------- discovery */

const RUN_STATUS = {
  IDLE: { label: "CHƯA CHẠY", kind: "" },
  SEARCHING: { label: "SEARCHING", kind: "tag-accent" },
  CANDIDATE_FOUND: { label: "CANDIDATE_FOUND", kind: "tag-ok" },
  NO_QUALIFIED_VIDEO: { label: "NO_QUALIFIED_VIDEO", kind: "tag-warn" },
  BLOCKED: { label: "BLOCKED", kind: "tag-danger" },
  ERROR: { label: "ERROR", kind: "tag-danger" },
};

function setRunStatus(status) {
  const info = RUN_STATUS[status] || { label: String(status || "IDLE"), kind: "" };
  const badge = el("disc-status");
  badge.textContent = info.label;
  badge.className = "tag " + (info.kind || "");
  state.status = status;
}

function readFilters() {
  const val = (id) => {
    const node = el(id);
    return node ? node.value.trim() : "";
  };
  return {
    min_views: val("disc-min-views"),
    max_views: val("disc-max-views"),
    min_likes: val("disc-min-likes"),
    min_comments: val("disc-min-comments"),
    min_shares: val("disc-min-shares"),
    max_duration: val("disc-max-duration"),
    max_days: val("disc-days"),
    must_include: val("disc-must"),
    exclude: val("disc-exclude"),
  };
}

async function loadDiscovery() {
  setRunStatus(state.status || "IDLE");
  try {
    const data = await api("/discovery/last");
    if (data && data.status) {
      state.result = data;
      state.candidates = data.candidates || [];
      state.scores = data.scores || [];
      state.rejected = data.rejected || [];
      state.selected = data.selected || null;
      state.selectedScore = data.selected_score || null;
      state.eligibility = data.eligibility || null;
      state.analyses = data.analyses || [];
      state.shortfallNote = data.shortfall_note || "";
      setRunStatus(data.status);
    }
  } catch (e) { /* the last result is optional */ }
  renderDiscovery();
}

function renderDiscovery() {
  const rows = state.candidates || [];
  el("disc-count").textContent = rows.length + " ứng viên";

  const blockers = (state.result && state.result.blockers) || [];
  el("disc-blockers").innerHTML = blockers.length
    ? blockers.map((b) => '<div class="notif"><div class="notif-kind">Blocker</div><div class="notif-msg">' +
        esc(b) + "</div></div>").join("")
    : "";

  const scores = state.scores || [];
  el("disc-table").innerHTML =
    "<thead><tr><th>#</th><th>Video</th><th>Views</th><th>Likes</th><th>Comments</th>" +
    "<th>Shares</th><th>Thời lượng</th><th>Đăng ngày</th><th>Điểm</th><th>Quyết định</th><th>Chi tiết</th></tr></thead><tbody>" +
    (rows.length ? rows.map((c, i) => {
      const score = scores.find((s) => s.video && s.video.source_url === c.source_url);
      const known = c.metrics_known !== false;
      const isSelected = state.selected && state.selected.source_url === c.source_url;
      return "<tr" + (isSelected ? " style='background:rgba(79,140,255,.09)'" : "") + ">" +
        "<td>" + (i + 1) + (isSelected ? " ★" : "") + "</td>" +
        "<td><a href='" + esc(c.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--accent)'>" +
          esc((c.title || c.source_url).slice(0, 60)) + "</a>" +
          "<div class='muted'>" + esc(c.creator || "") + "</div></td>" +
        "<td class='num'>" + metric(c.views, known) + "</td>" +
        "<td class='num'>" + metric(c.likes, known) + "</td>" +
        "<td class='num'>" + metric(c.comments, known) + "</td>" +
        "<td class='num'>" + metric(c.shares, known) + "</td>" +
        "<td class='num'>" + (c.duration_seconds ? c.duration_seconds.toFixed(1) + "s" : "—") + "</td>" +
        "<td class='muted'>" + esc(c.posted_at || "—") + "</td>" +
        "<td class='num'>" + (score ? score.score : "—") + "</td>" +
        "<td>" + (score ? tag(score.decision, statusKind(score.decision)) : "—") + "</td>" +
        "<td><button class='btn btn-xs' data-detail='" + esc(c.source_url) + "'>Xem</button>" +
        (isSelected ? " <button class='btn btn-xs' data-approve='" + esc(c.source_url) + "'>Duyệt</button>" : "") +
        "</td>" +
        "</tr>";
    }).join("") : emptyRow(11, "Chưa có kết quả. Bấm “Tìm kiếm” để chạy tìm kiếm thật.")) +
    "</tbody>";

  renderSelected();
  renderAnalysis();
  renderTrends();
  renderFilter();
}

/* The AI content analysis of every candidate. Only the candidates whose
   real content was read and judged as AI Music take part in the ranking. */
function renderAnalysis() {
  const analyses = state.analyses || [];
  const ranked = analyses.filter((a) => a.ranked !== false);
  const insufficient = analyses.filter(
    (a) => a.ranked === false && a.content_relevant !== false
  );
  const counter = el("disc-analysis-count");
  if (counter) {
    counter.textContent = analyses.length
      ? ranked.length + "/" + analyses.length + " video AI Music thật"
      : "Chưa có phân tích";
  }
  const box = el("disc-analysis");
  if (!box) return;

  if (!analyses.length) {
    box.innerHTML = '<div class="empty">Chưa có phân tích AI. Bấm “Tìm kiếm” để chạy phân tích nội dung thật.</div>';
    return;
  }

  const note = state.shortfallNote
    ? '<div class="notif"><div class="notif-kind">Lưu ý</div><div class="notif-msg">' + esc(state.shortfallNote) + "</div></div>"
    : "";

  const cards = ranked.map((a) => {
    const dims = (a.dimensions || []).map((d) => {
      const known = d.known !== false;
      return "<tr>" +
        "<td>" + esc(d.label) + "</td>" +
        "<td class='num'>" + (known ? d.points + "/" + d.max_points : "—") + "</td>" +
        "<td class='muted'>" + esc(known ? d.detail : "CHƯA ĐỦ DỮ LIỆU") + "</td>" +
        "</tr>";
    }).join("");
    const strengths = (a.strengths || []).map((s) => "<li>" + esc(s) + "</li>").join("");
    const weaknesses = (a.weaknesses || []).map((s) => "<li>" + esc(s) + "</li>").join("");
    const best = a.rank === 1;
    return "<div class='card' style='border-left:3px solid " + (best ? "var(--accent)" : "var(--line)") + "'>" +
      "<div class='row-between'>" +
        "<strong>" + (a.rank ? "#" + a.rank + " · " : "") + "@" + esc(a.creator || "—") +
        (best ? ' <span class="tag tag-accent">ĐỀ XUẤT TỐT NHẤT</span>' : "") + "</strong>" +
        "<span class='tag'>" + a.score + "/100</span>" +
      "</div>" +
      "<div class='muted'>" + esc(a.title || a.source_url || "") + "</div>" +
      "<div class='muted' style='margin-top:4px'>" +
        esc(a.summary || "") + "</div>" +
      "<div class='muted' style='margin-top:4px'>" +
        "Nội dung thật: " + (a.content_analyzed ? "đã phân tích " + (a.frame_count || 0) + " khung hình" : "chưa đọc được") +
        (a.provider ? " · " + esc(a.provider) : "") +
      "</div>" +
      "<table class='table'><thead><tr><th>Tiêu chí</th><th>Điểm</th><th>Lý do</th></tr></thead><tbody>" +
        dims + "</tbody></table>" +
      (strengths ? "<div><strong>Điểm mạnh</strong><ul>" + strengths + "</ul></div>" : "") +
      (weaknesses ? "<div><strong>Điểm yếu</strong><ul>" + weaknesses + "</ul></div>" : "") +
      "<div class='row-actions'>" +
        "<button class='btn btn-xs' data-preview-url='" + esc(a.source_url) + "'>Xem trước</button>" +
        "<button class='btn btn-xs' data-approve='" + esc(a.source_url) + "'>Duyệt</button>" +
        "<button class='btn btn-xs btn-danger' data-reject='" + esc(a.source_url) + "'>Từ chối</button>" +
      "</div>" +
      "</div>";
  }).join("");

  const missing = insufficient.length
    ? '<div class="card"><strong>Chưa đủ dữ liệu (' + insufficient.length + ")</strong>" +
      '<div class="muted">Các video này không được xếp hạng vì nội dung thật không đọc được hợp lệ. ' +
      "Chúng không phải kết quả và không được chọn.</div>" +
      insufficient.map((a) => "<div class='muted'>@" + esc(a.creator || "—") + " — " + esc(a.insufficient_reason || "không đọc được nội dung") + "</div>").join("") +
      "</div>"
    : "";

  const rejected = analyses.filter((a) => a.content_relevant === false);
  const notMusic = rejected.length
    ? '<div class="card"><strong>Không phải AI Music (' + rejected.length + ")</strong>" +
      '<div class="muted">Nội dung thật của các video này không phải AI Music, ' +
      "nên chúng bị loại và không được xếp hạng.</div>" +
      rejected.map((a) => "<div class='muted'>@" + esc(a.creator || "—") + " — " + esc(a.content_relevance_reason || a.insufficient_reason || "không phù hợp") + "</div>").join("") +
      "</div>"
    : "";

  box.innerHTML = note + cards + notMusic + missing;

  // The preview dropdown lists every candidate, so the admin can look at
  // any of them and not only at the recommended one.
  const select = el("disc-preview-select");
  if (select) {
    const current = select.value;
    select.innerHTML = '<option value="">— chọn video để xem trước —</option>' +
      analyses.map((a) => {
        const label = "#" + (a.rank || "-") + " · @" + (a.creator || "—") +
          " · " + (a.score || 0) + " điểm";
        return "<option value='" + esc(a.source_url) + "'>" + esc(label) + "</option>";
      }).join("");
    select.value = current;
  }
}

function renderSelected() {
  const card = el("disc-selected-card");
  const selected = state.selected;
  if (!selected) {
    card.hidden = true;
    el("disc-selected-score").textContent = "—";
    return;
  }
  card.hidden = false;
  const score = state.selectedScore;
  el("disc-selected-score").textContent = score ? "điểm " + score.score : "—";
  const known = selected.metrics_known !== false;
  el("disc-selected").innerHTML =
    "<dl class='kv'>" +
    "<dt>Tiêu đề</dt><dd>" + esc(selected.title || "—") + "</dd>" +
    "<dt>Creator</dt><dd>" + esc(selected.creator || "—") + "</dd>" +
    "<dt>URL</dt><dd><a href='" + esc(selected.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--accent)'>" +
      esc(selected.source_url) + "</a></dd>" +
    "<dt>Lượt xem</dt><dd>" + metric(selected.views, known) + "</dd>" +
    "<dt>Lượt thích</dt><dd>" + metric(selected.likes, known) + "</dd>" +
    "<dt>Bình luận</dt><dd>" + metric(selected.comments, known) + "</dd>" +
    "<dt>Chia sẻ</dt><dd>" + metric(selected.shares, known) + "</dd>" +
    "<dt>Thời lượng</dt><dd>" + (selected.duration_seconds ? selected.duration_seconds.toFixed(1) + "s" : "—") + "</dd>" +
    "<dt>Đăng ngày</dt><dd>" + esc(selected.posted_at || "—") + "</dd>" +
    "<dt>Điểm xu hướng</dt><dd>" + (score ? score.score + " — " + esc(score.reason) : "—") + "</dd>" +
    "</dl>";
}

/* ----------------------------------------------------------- trends */

function renderTrends() {
  const scores = state.scores || [];
  const rejected = state.rejected || [];
  el("trend-count").textContent = String(scores.length);
  el("trend-table").innerHTML =
    "<thead><tr><th>Video</th><th>Điểm</th><th>Quyết định</th><th>Chi tiết điểm</th></tr></thead><tbody>" +
    (scores.length ? scores.map((s) =>
      "<tr><td><span style='color:var(--accent)'>" + esc((s.video.title || s.video.source_url).slice(0, 50)) +
        "</span><div class='muted'>" + esc(s.video.creator || "") + "</div></td>" +
      "<td class='num'>" + s.score + "</td>" +
      "<td>" + tag(s.decision, statusKind(s.decision)) + "</td>" +
      "<td class='muted'>" + esc(s.reason) + "</td></tr>").join("")
      : emptyRow(4, "Chưa có dữ liệu xu hướng. Chạy tìm kiếm trước.")) +
    "</tbody>";

  el("trend-rejected").innerHTML = rejected.length
    ? rejected.map((r) =>
        '<div class="notif"><div class="notif-kind">' + esc(r.decision) + " · " + r.score + " điểm</div>" +
        '<div class="notif-msg">' + esc((r.title || r.source_url).slice(0, 70)) + "<br>" +
        '<span class="muted">' + esc(r.reason) + "</span></div></div>").join("")
    : '<div class="empty">Không có video nào bị loại.</div>';
}

/* ----------------------------------------------------------- filter */

function renderFilter() {
  const scores = state.scores || [];
  const rejected = state.rejected || [];
  const accepted = scores.filter((s) => s.decision === "ACCEPT");
  el("filter-reasons").innerHTML =
    (accepted.length
      ? '<div class="notif"><div class="notif-kind">Đạt điều kiện</div><div class="notif-msg">' +
        accepted.map((s) => esc((s.video.title || s.video.source_url).slice(0, 60)) + " — " + esc(s.reason)).join("<br>") +
        "</div></div>"
      : '<div class="notif"><div class="notif-kind">NO_QUALIFIED_VIDEO</div><div class="notif-msg">' +
        "Không có video nào đạt ngưỡng. Không chọn video kém chất lượng để lấp kết quả.</div></div>") +
    (rejected.length
      ? '<div class="notif"><div class="notif-kind">Bị loại</div><div class="notif-msg">' +
        rejected.map((r) => esc((r.title || r.source_url).slice(0, 60)) + " — " + esc(r.reason)).join("<br>") +
        "</div></div>"
      : "");

  const e = state.eligibility;
  if (!e || !e.checked) {
    el("filter-eligibility").innerHTML =
      '<div class="empty">' + esc((e && e.note) || "Chưa có video nào được chọn nên chưa kiểm tra khả năng tải.") + "</div>";
    return;
  }
  el("filter-eligibility").innerHTML =
    "<dl class='kv'>" +
    "<dt>Khả năng tải (kỹ thuật)</dt><dd>" +
      (e.download_capable ? tag("tải được", "ok") : tag("không tải được", "danger")) +
      (e.media_host ? " · " + esc(e.media_host) : "") + "</dd>" +
    "<dt>Quyền tái sử dụng</dt><dd>" +
      (e.reuse_permitted ? tag("được phép", "ok") : tag("cần xem xét", "danger")) + "</dd>" +
    "<dt>Lý do quyền</dt><dd class='muted'>" + esc(e.reuse_reason || "—") + "</dd>" +
    "<dt>Trạng thái tải</dt><dd>" + tag("chưa tải — chờ phê duyệt", "warn") + "</dd>" +
    "</dl>" +
    ((e.reasons && e.reasons.length)
      ? '<div class="notif"><div class="notif-kind">Lý do chặn</div><div class="notif-msg">' +
        e.reasons.map(esc).join("<br>") + "</div></div>"
      : "") +
    '<p class="note">' + esc(e.note || "") + "</p>";
}

/* -------------------------------------------------------- approvals */

async function loadApprovals() {
  try {
    const data = await api("/approvals");
    state.approvals = data.approvals || [];
  } catch (e) { toast(e.message, "err"); return; }
  setBadge("badge-approval", state.approvals.length);
  el("appr-count").textContent = String(state.approvals.length);

  el("appr-table").innerHTML =
    "<thead><tr><th>Task</th><th>Chủ đề</th><th>Trạng thái</th><th>Video</th><th>Cập nhật</th>" +
    "<th>Duyệt tải</th><th>Duyệt đăng</th></tr></thead><tbody>" +
    (state.approvals.length ? state.approvals.map((a) =>
      "<tr><td>" + esc(a.task_id) + "</td>" +
      "<td class='muted'>" + esc(a.topic || "—") + "</td>" +
      "<td>" + tag(a.status, statusKind(a.status)) + "</td>" +
      "<td class='muted'>" + esc((a.selected_url || "—").slice(0, 48)) + "</td>" +
      "<td class='muted'>" + esc(fmtDate(a.created_at)) + "</td>" +
      "<td><button class='btn btn-xs' data-appr='download' data-task='" + esc(a.task_id) + "'>Duyệt tải</button></td>" +
      "<td><button class='btn btn-xs' data-appr='publish' data-task='" + esc(a.task_id) + "'>Duyệt đăng</button></td>" +
      "</tr>").join("")
      : emptyRow(7, "Không có mục nào chờ duyệt.")) +
    "</tbody>";
}

/* --------------------------------------------------------- library */

async function loadLibrary() {
  try {
    const data = await api("/library");
    el("lib-count").textContent = String(data.count || 0);
    el("lib-table").innerHTML =
      "<thead><tr><th>SHA256</th><th>Task</th><th>Nguồn</th><th>File</th></tr></thead><tbody>" +
      ((data.entries || []).length ? data.entries.map((e) =>
        "<tr><td class='muted'>" + esc(String(e.sha256).slice(0, 20)) + "…</td>" +
        "<td>" + esc(e.task_id) + "</td>" +
        "<td class='muted'>" + esc((e.source || "—").slice(0, 46)) + "</td>" +
        "<td class='muted'>" + esc(e.path || "—") + "</td></tr>").join("")
        : emptyRow(4, "Thư viện còn trống.")) +
      "</tbody>";
  } catch (e) { toast(e.message, "err"); }
}

/* --------------------------------------------------------- history */

async function loadHistory() {
  try {
    const h = await api("/history");
    const entries = h.history || [];
    el("hist-count").textContent = String(entries.length);
    el("hist-table").innerHTML =
      "<thead><tr><th>Ngày</th><th>Nền tảng</th><th>Caption</th><th>URL</th><th>Trạng thái</th></tr></thead><tbody>" +
      (entries.length ? entries.map((e) =>
        "<tr><td class='muted'>" + esc(e.date || e.published_at || "—") + "</td>" +
        "<td>" + esc(e.platform || "—") + "</td>" +
        "<td class='muted'>" + esc((e.caption || "").slice(0, 60)) + "</td>" +
        "<td class='muted'>" + esc((e.posted_url || "—").slice(0, 40)) + "</td>" +
        "<td>" + tag(e.status || "—", statusKind(e.status)) + "</td></tr>").join("")
        : emptyRow(5, "Chưa có lịch sử đăng bài.")) +
      "</tbody>";
  } catch (e) { toast(e.message, "err"); }

  try {
    const l = await api("/logs");
    const logs = l.logs || [];
    el("log-table").innerHTML =
      "<thead><tr><th>Task</th><th>Trạng thái</th><th>Lý do</th><th>Cập nhật</th></tr></thead><tbody>" +
      (logs.length ? logs.map((t) =>
        "<tr><td>" + esc(t.task_id) + "</td>" +
        "<td>" + tag(t.status || "—", statusKind(t.status)) + "</td>" +
        "<td class='muted'>" + esc((t.reason || "").slice(0, 70)) + "</td>" +
        "<td class='muted'>" + esc(fmtDate(t.updated_at)) + "</td></tr>").join("")
        : emptyRow(4, "Chưa có nhật ký.")) +
      "</tbody>";
  } catch (e) { /* the log is optional */ }
}

/* -------------------------------------------------------- analytics */

async function loadAnalytics() {
  try {
    const a = await api("/analytics");
    const cards = [
      ["Đã đăng", a.published_count, "bài", "ok"],
      ["Views TB", a.average_views, "trung bình", "accent"],
      ["Likes TB", a.average_likes, "trung bình", ""],
      ["Video đã tải", a.downloaded_count, "trong thư viện", ""],
      ["Tasks", a.task_count, "tác vụ", ""],
      ["Reviews", a.review_count, "lượt review", "warn"],
    ];
    el("an-stats").innerHTML = cards.map(([label, value, sub, kind]) =>
      '<div class="stat ' + (kind || "") + '">' +
      '<div class="stat-label">' + esc(label) + "</div>" +
      '<div class="stat-value">' + num(value) + "</div>" +
      '<div class="stat-sub">' + esc(sub) + "</div></div>").join("");

    const d = a.decisions || {};
    el("an-decisions").innerHTML =
      "<thead><tr><th>Quyết định</th><th>Số video</th></tr></thead><tbody>" +
      Object.keys(d).map((k) =>
        "<tr><td>" + tag(k, statusKind(k)) + "</td><td class='num'>" + num(d[k]) + "</td></tr>").join("") +
      "</tbody>";
    if (!a.has_data) {
      el("an-decisions").innerHTML +=
        '<tfoot><tr><td colspan="2" class="empty">Chưa có dữ liệu hiệu quả. Chạy tìm kiếm thật để có số liệu.</td></tr></tfoot>';
    }
  } catch (e) { toast(e.message, "err"); }
}

/* -------------------------------------------------------- settings */

async function loadSettings() {
  try {
    const data = await api("/settings");
    const c = data.config || {};
    el("set-mode").value = c.mode || "approve";
    el("set-autopost").value = String(c.auto_post === true);
    if (c.topic) el("disc-topic").value = c.topic;
    if (c.schedule && c.schedule.daily_time) el("sched-time").value = c.schedule.daily_time;
  } catch (e) { toast(e.message, "err"); }

  try {
    const p = await api("/search-profiles");
    el("prof-table").innerHTML =
      "<thead><tr><th>Tên</th><th>Cập nhật</th><th></th></tr></thead><tbody>" +
      ((p.profiles || []).length ? p.profiles.map((pr) =>
        "<tr><td>" + esc(pr.name) + "</td>" +
        "<td class='muted'>" + esc(fmtDate(pr.updated_at || pr.created_at)) + "</td>" +
        "<td><button class='btn btn-xs' data-delprof='" + esc(pr.name) + "'>Xóa</button></td></tr>").join("")
        : emptyRow(3, "Chưa lưu cấu hình tìm kiếm nào.")) +
      "</tbody>";

    const select = el("disc-profiles");
    const current = select.value;
    select.innerHTML = '<option value="">— cấu hình đã lưu —</option>' +
      (p.profiles || []).map((pr) => '<option value="' + esc(pr.name) + '">' + esc(pr.name) + "</option>").join("");
    select.value = current;
  } catch (e) { /* profiles are optional */ }

  await loadPermissions();
}

async function loadPermissions() {
  try {
    const data = await api("/permissions");
    const rows = data.permissions || [];
    el("sec-allowlist").innerHTML =
      "<dl class='kv'>" +
      "<dt>Nguồn được cấp phép</dt><dd>" + num(data.valid_count) + " / " + num(data.total_count) + " hợp lệ</dd>" +
      "</dl>" +
      "<div class='table-wrap'><table class='table'>" +
      "<thead><tr><th>Creator</th><th>Quyền</th><th>Đã xác minh</th><th>Giấy phép đến</th><th>Trạng thái</th></tr></thead><tbody>" +
      (rows.length ? rows.map((r) =>
        "<tr><td>" + esc(r.creator) + "<div class='muted'>" + esc(r.source) + "</div></td>" +
        "<td>" + tag(r.rights || "—") + "</td>" +
        "<td>" + (r.rights_verified ? tag("có", "ok") : tag("không", "danger")) + "</td>" +
        "<td>" + esc(r.permit_date || "—") + "</td>" +
        "<td>" + (r.permit_valid
          ? tag("được phép", "ok")
          : tag(r.permit_reason || "cần xem xét", "danger")) + "</td></tr>").join("")
        : emptyRow(5, "Chưa cấu hình nguồn nào.")) +
      "</tbody></table></div>";
  } catch (e) { /* permissions are optional */ }
}

/* --------------------------------------------------------- studio */

async function loadStudio() {
  try {
    const d = await api("/overview");
    el("studio-account").textContent = d.expected_account || "—";
  } catch (e) { /* ignore */ }
  try {
    const t = await api("/tasks");
    const tasks = (t.tasks || []).filter((x) =>
      ["DRAFT_SAVED", "AWAITING_APPROVAL", "UPLOADED", "UPLOADING"].includes(x.status));
    el("studio-table").innerHTML =
      "<thead><tr><th>Task</th><th>Trạng thái</th><th>Bản nháp</th><th>URL đã đăng</th></tr></thead><tbody>" +
      (tasks.length ? tasks.map((x) =>
        "<tr><td>" + esc(x.task_id) + "</td>" +
        "<td>" + tag(x.status, statusKind(x.status)) + "</td>" +
        "<td class='muted'>" + esc(x.draft_reference || "—") + "</td>" +
        "<td class='muted'>" + esc(x.posted_url || "chưa đăng") + "</td></tr>").join("")
        : emptyRow(4, "Chưa có bản nháp nào.")) +
      "</tbody>";
  } catch (e) { toast(e.message, "err"); }
}

/* ------------------------------------------------------- scheduler */

async function loadScheduler() {
  try {
    const s = await api("/scheduler");
    el("sched-state").textContent = s.running ? "đang chạy" : (s.enabled ? "đã bật" : "đang tắt");
    el("sched-state").className = "tag " + (s.running ? "tag-ok" : "");
    if (s.topic) el("sched-topic").value = s.topic;
    if (s.daily_time) el("sched-time").value = s.daily_time;
    if (s.daily_limit) el("sched-limit").value = s.daily_limit;
    el("sched-runs").innerHTML =
      "<thead><tr><th>Thời điểm</th><th>Task</th><th>Trạng thái</th><th>Số video</th><th>Blocker</th></tr></thead><tbody>" +
      ((s.runs || []).length ? s.runs.map((r) =>
        "<tr><td class='muted'>" + esc(fmtDate(r.at)) + "</td>" +
        "<td>" + esc(r.task_id) + "</td>" +
        "<td>" + tag(r.status, statusKind(r.status)) + "</td>" +
        "<td class='num'>" + num(r.candidate_count) + "</td>" +
        "<td class='muted'>" + esc((r.blockers || []).join("; ").slice(0, 80)) + "</td></tr>").join("")
        : emptyRow(5, "Chưa có lượt chạy nào.")) +
      "</tbody>";
    const next = document.getElementById("sched-next");
    if (next) {
      next.textContent = s.next_run
        ? "Lần chạy tiếp theo: " + s.next_run
        : "Chưa có lần chạy tiếp theo.";
    }
  } catch (e) { toast(e.message, "err"); }
}

/* ------------------------------------------------------- assistant */

function assistantAnswer(question) {
  const q = String(question || "").toLowerCase();
  const o = state.overview || {};
  const c = o.counts || {};

  if (q.includes("blocker") || q.includes("lỗi") || q.includes("xử lý")) {
    const b = o.blockers || [];
    return b.length
      ? "Có " + b.length + " blocker:\n• " + b.join("\n• ") +
        "\n\nCần bạn xử lý trước khi tìm kiếm có kết quả."
      : "Không có blocker nào. Hệ thống đang ở trạng thái bình thường.";
  }
  if (q.includes("lịch") || q.includes("schedule") || q.includes("chạy")) {
    const s = o.schedule || {};
    return "Lịch: " + (s.enabled ? "đang bật" : "đang tắt") +
      ", chạy lúc " + (s.daily_time || "—") +
      ", lần tiếp theo " + (s.next_run || "—") +
      ", đã chạy " + (s.run_count || 0) + " lượt.\nChủ đề: " + (s.topic || "—") + ".";
  }
  if (q.includes("đủ điều kiện") || q.includes("chọn") || q.includes("video")) {
    const accepted = (state.scores || []).filter((s) => s.decision === "ACCEPT");
    if (!state.scores.length) {
      return "Chưa có dữ liệu chấm điểm. Chạy tìm kiếm ở mục TikTok Discovery trước.";
    }
    if (!accepted.length) {
      return "NO_QUALIFIED_VIDEO — chưa có video nào đạt ngưỡng. " +
        "Các video bị loại:\n" +
        (state.scores || []).map((s) =>
          "• " + ((s.video.title || s.video.source_url).slice(0, 50) + " — " + s.reason)).join("\n");
    }
    return "Có " + accepted.length + " video đạt điều kiện:\n" +
      accepted.map((s) => "• " + ((s.video.title || s.video.source_url).slice(0, 50) +
        " — điểm " + s.score)).join("\n") +
      "\n\nChỉ một video được chọn cho mỗi lượt, theo nguyên tắc 1 video tốt nhất.";
  }
  if (q.includes("xu hướng") || q.includes("trend")) {
    if (!(state.scores || []).length) {
      return "Chưa có dữ liệu xu hướng. Chạy tìm kiếm để có chỉ số thật.";
    }
    const top = (state.scores || []).slice(0, 5).map((s) =>
      "• " + s.score + " điểm — " + ((s.video.title || s.video.source_url).slice(0, 45)) +
      " (views " + s.video.views + ", likes " + s.video.likes + ")");
    return "Top xu hướng theo điểm:\n" + top.join("\n");
  }
  if (q.includes("đăng") || q.includes("publish") || q.includes("kết quả")) {
    return "Đã đăng: " + (c.published || 0) + " bài.\nVideo đã tải: " + (c.library || 0) +
      ".\nTasks: " + (c.tasks || 0) + ".\n\nauto_post đang là " +
      (o.auto_post ? "true" : "false") + " — mặc định không tự đăng.";
  }
  return "Tôi đọc trạng thái thật của hệ thống. Bạn có thể hỏi về: video đủ điều kiện, " +
    "xu hướng, blocker, lịch chạy, hoặc kết quả đã đăng.";
}

/* ---------------------------------------------------------- actions */

async function runDiscovery(resume) {
  const btn = el("btn-discover");
  const again = el("btn-discover-again");
  const stop = el("btn-discover-stop");
  const resumeBtn = el("btn-discover-resume");
  btn.disabled = true;
  again.disabled = true;
  if (resumeBtn) resumeBtn.disabled = true;
  stop.disabled = false;
  btn.textContent = resume ? "Đang phân tích…" : "Đang tìm…";
  setRunStatus("SEARCHING");
  try {
    const topic = el("disc-topic").value.trim();
    const job = await api("/discovery/search", {
      method: "POST",
      body: JSON.stringify({ topic, filters: readFilters(), resume: !!resume }),
    });
    state.jobId = job.job_id;
    toast(
      resume
        ? "Đang phân tích lại từ kết quả đã lưu (không tìm kiếm lại TikTok): " + job.job_id
        : "Đang tìm kiếm: " + job.job_id,
      "ok"
    );
    pollJob(job.job_id);
  } catch (e) {
    toast(e.message, "err");
    setRunStatus("ERROR");
    btn.disabled = false;
    again.disabled = false;
    if (resumeBtn) resumeBtn.disabled = false;
    stop.disabled = true;
    btn.textContent = "Tìm kiếm";
  }
}

async function pollJob(jobId) {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    let jobs;
    try { jobs = await api("/jobs"); } catch (e) { continue; }
    const found = (jobs.jobs || []).find((j) => j.job_id === jobId);
    if (!found) continue;
    if (found.status === "RUNNING") continue;
    const btn = el("btn-discover");
    btn.disabled = false;
    btn.textContent = "Tìm kiếm";
    el("btn-discover-again").disabled = false;
    el("btn-discover-stop").disabled = true;
    const resumeBtn = el("btn-discover-resume");
    if (resumeBtn) resumeBtn.disabled = false;

    const detail = found.detail || {};
    if (found.status === "COMPLETED" && detail.status) {
      state.result = detail;
      state.candidates = detail.candidates || [];
      state.scores = detail.scores || [];
      state.rejected = detail.rejected || [];
      state.selected = detail.selected || null;
      state.selectedScore = detail.selected_score || null;
      state.eligibility = detail.eligibility || null;
      state.analyses = detail.analyses || [];
      state.shortfallNote = detail.shortfall_note || "";
      setRunStatus(detail.status);
      renderDiscovery();
      const message = detail.status === "CANDIDATE_FOUND"
        ? "Đã chọn 1 video: " + (detail.selected || {}).source_url
        : detail.status;
      toast(message, detail.status === "CANDIDATE_FOUND" ? "ok" : "err");
    } else {
      setRunStatus("ERROR");
      toast(found.message || "Thất bại", "err");
    }
    await loadOverview();
    return;
  }
  const btn = el("btn-discover");
  btn.disabled = false;
  btn.textContent = "Tìm kiếm";
  el("btn-discover-again").disabled = false;
  el("btn-discover-stop").disabled = true;
}

async function stopDiscovery() {
  if (!state.jobId) return;
  try {
    await api("/discovery/stop", {
      method: "POST",
      body: JSON.stringify({ job_id: state.jobId }),
    });
    toast("Đã yêu cầu dừng tìm kiếm.", "ok");
    el("btn-discover-stop").disabled = true;
  } catch (e) { toast(e.message, "err"); }
}

function closeVideoDetail() {
  const modal = el("video-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.style.overflow = "";
  // The button that opened the modal gets the focus back, so the user can
  // keep working on the dashboard where they left off.
  if (state.lastDetailButton && document.contains(state.lastDetailButton)) {
    state.lastDetailButton.focus();
  }
  state.lastDetailButton = null;
}

function openVideoDetail(sourceUrl, trigger) {
  // The modal always opens, so the user never gets a blank panel. The
  // content is then filled from the backend, which is the record of the
  // run that produced this candidate.
  state.lastDetailButton = trigger || null;
  el("video-modal-title").textContent = "Chi tiết video";
  el("video-modal-body").innerHTML =
    '<div class="modal-loading"><span class="spinner"></span>Đang tải chi tiết video…</div>';
  el("video-modal").hidden = false;
  document.body.style.overflow = "hidden";
  el("btn-video-close").focus();
  loadVideoDetail(sourceUrl);
}

async function loadVideoDetail(sourceUrl) {
  try {
    const data = await api("/discovery/detail?source_url=" + encodeURIComponent(sourceUrl));
    renderVideoDetail(data);
  } catch (e) {
    // The reason is shown inside the modal, so the user is never left
    // looking at an empty panel.
    el("video-modal-title").textContent = "Chi tiết video";
    el("video-modal-body").innerHTML =
      '<div class="notif"><div class="notif-kind">Không lấy được chi tiết</div>' +
      '<div class="notif-msg">' + esc(e.message || "Không rõ nguyên nhân.") + "</div></div>" +
      '<p class="note">URL video: ' + esc(sourceUrl) + "</p>";
  }
}

function renderVideoDetail(data) {
  const candidate = data.candidate || {};
  const score = data.score || null;
  const eligibility = data.eligibility || {};
  const missing = data.missing_metrics || candidate.missing_metrics || [];
  const known = candidate.metrics_known !== false;

  el("video-modal-title").textContent = (candidate.title || "Chi tiết video").slice(0, 70);

  const rows = [];
  const add = (label, value) => rows.push(
    "<dt>" + esc(label) + "</dt><dd>" + value + "</dd>"
  );

  add("Tiêu đề", esc(candidate.title || "—"));
  add("URL nguồn", "<a href='" + esc(candidate.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--accent)'>" +
    esc(candidate.source_url) + "</a>");
  add("Creator", esc(candidate.creator || "—"));
  add("Nguồn", esc(candidate.source_name || "—"));
  add("Chủ đề", esc(candidate.topic || data.topic || "—"));
  add("Lượt xem", metric(candidate.views, known));
  add("Lượt thích", metric(candidate.likes, known));
  add("Bình luận", metric(candidate.comments, known));
  add("Chia sẻ", metric(candidate.shares, known));
  add("Thời lượng", candidate.duration_seconds ? candidate.duration_seconds.toFixed(1) + "s" : "—");
  add("Ngày đăng", esc(candidate.posted_at || "—"));
  // The platform's own AI label. When it published no label the fact is
  // unknown, so it is reported as unknown and not as "no".
  add("AI label", candidate.ai_label_known === false
    ? tag("chưa công bố", "")
    : (candidate.is_ai_generated ? tag("có", "ok") : tag("không", "")));
  add("Điểm xu hướng", score
    ? "<strong>" + score.score + "</strong> — " + esc(score.decision) +
      "<div class='muted'>" + esc(score.reason) + "</div>"
    : "—");
  add("Trạng thái tải", data.downloaded
    ? tag("đã tải", "warn")
    : tag("chưa tải — chờ phê duyệt", "warn"));
  add("Quyền sử dụng", eligibility.checked
    ? (eligibility.reuse_permitted
        ? tag("được phép tái sử dụng", "ok")
        : tag("chưa có quyền tái sử dụng", "danger")) +
      "<div class='muted'>" + esc(eligibility.reuse_reason || "—") + "</div>"
    : tag("chưa kiểm tra", ""));
  add("Khả năng tải", eligibility.checked
    ? (eligibility.download_capable ? tag("tải được", "ok") : tag("không tải được", "danger")) +
      (eligibility.media_host ? "<div class='muted'>" + esc(eligibility.media_host) + "</div>" : "")
    : tag("chưa kiểm tra", ""));
  add("Chế độ chạy", esc(data.mode || "—"));
  add("Trạng thái lượt tìm", esc(data.run_status || "—"));

  el("video-modal-body").innerHTML =
    "<dl class='kv'>" + rows.join("") + "</dl>" +
    (missing.length
      ? '<div class="notif"><div class="notif-kind">Không có dữ liệu</div><div class="notif-msg">' +
        "Nguồn không cung cấp: " + esc(missing.join(", ")) + "</div></div>"
      : "") +
    (eligibility.checked && eligibility.reasons && eligibility.reasons.length
      ? '<div class="notif"><div class="notif-kind">Lý do chặn tải</div><div class="notif-msg">' +
        eligibility.reasons.map(esc).join("<br>") + "</div></div>"
      : "") +
    '<p class="note">Khả năng tải là kiểm tra kỹ thuật. Quyền tái sử dụng là quyền pháp lý ' +
    "và không suy ra từ khả năng tải. Video chỉ được tải sau khi quản trị viên phê duyệt.</p>";
}

async function approveCandidate(sourceUrl) {
  // The chosen video goes into a review record, so the choice is auditable
  // and the download only happens after the admin approves it.
  try {
    const res = await api("/discovery/approve", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl, topic: el("disc-topic").value.trim() }),
    });
    toast("Đã tạo hồ sơ duyệt cho video. Chưa tải file nào.", "ok");
    await loadApprovals();
    if (res && res.task_id) el("cap-task").value = res.task_id;
  } catch (e) { toast(e.message, "err"); }
}

async function rejectCandidate(sourceUrl, reason) {
  // The decision is written down with its reason, so the same video is not
  // offered again and the admin can see why it was turned down.
  const why = (reason === undefined || reason === null)
    ? window.prompt("Lý do từ chối video này (có thể để trống):", "")
    : reason;
  if (why === null) return;
  try {
    await api("/discovery/reject", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl, reason: why }),
    });
    toast("Đã ghi nhận quyết định từ chối. Không tải video nào.", "ok");
    await loadDiscovery();
  } catch (e) { toast(e.message, "err"); }
}

/* The video preview. The file is streamed by the dashboard from the media
   that is already on disk. Nothing is downloaded into the library here.
   The player asks the endpoint directly, because the endpoint streams the
   file and answers the byte ranges the browser player asks for. */
function playPreview(sourceUrl) {
  const box = el("disc-preview-box");
  const stateLabel = el("disc-preview-state");
  const player = el("disc-preview-player");
  const still = el("disc-preview-still");
  if (!box) return;
  box.hidden = false;

  const taskId = el("cap-task") ? el("cap-task").value.trim() : "";
  const url = "/api/media/preview?source_url=" + encodeURIComponent(sourceUrl) +
    (taskId ? "&task_id=" + encodeURIComponent(taskId) : "");
  if (player) {
    player.src = url;
    player.hidden = false;
  }
  if (still) {
    still.hidden = true;
    still.removeAttribute("src");
  }
  if (stateLabel) {
    stateLabel.textContent = "Đang phát video đã có trên máy. Nếu không có file, ảnh khung hình thật sẽ hiện thay.";
  }

  if (player) {
    player.play().catch(() => {
      // The video is not on this machine yet. The frames that were read
      // from it are shown instead, so the admin still sees the real
      // content of the video.
      showPreviewStill(sourceUrl);
    });
  } else {
    showPreviewStill(sourceUrl);
  }
}

function showPreviewStill(sourceUrl) {
  const still = el("disc-preview-still");
  const stateLabel = el("disc-preview-state");
  const player = el("disc-preview-player");
  if (!still) return;
  const url = "/api/media/frames?source_url=" + encodeURIComponent(sourceUrl);
  still.src = url;
  still.hidden = false;
  if (player) player.hidden = true;
  if (stateLabel) {
    stateLabel.textContent =
      "Video chưa tải về máy nên chưa phát được. Đây là khung hình thật đã đọc từ video và là nội dung AI đã phân tích.";
  }
}

async function approve(taskId, kind) {
  try {
    const path = kind === "publish" ? "/approvals/publish" : "/approvals/download";
    await api(path, { method: "POST", body: JSON.stringify({ task_id: taskId }) });
    toast(kind === "publish"
      ? "Đã cấp quyền đăng cho " + taskId
      : "Đã cấp quyền tải cho " + taskId, "ok");
    await loadApprovals();
  } catch (e) { toast(e.message, "err"); }
}

async function loadCaption() {
  const taskId = el("cap-task").value.trim();
  if (!taskId) { toast("Nhập task id trước.", "err"); return; }
  try {
    const data = await api("/reviews");
    const review = (data.reviews || []).find((r) => r.task_id === taskId);
    if (!review) { toast("Không tìm thấy review cho task này.", "err"); return; }
    const selected = review.selected_url ||
      ((review.candidates || [])[0] || {}).source_url || "";
    el("cap-text").value = review.caption || "";
    el("cap-tags").value = (review.hashtags || []).join("\n");
    el("cap-body").innerHTML =
      "<dl class='kv'>" +
      "<dt>Task</dt><dd>" + esc(review.task_id) + "</dd>" +
      "<dt>Chủ đề</dt><dd>" + esc(review.topic) + "</dd>" +
      "<dt>Trạng thái</dt><dd>" + esc(review.status) + "</dd>" +
      "<dt>Video</dt><dd class='muted'>" + esc(selected) + "</dd>" +
      "<dt>Số ứng viên</dt><dd>" + num((review.candidates || []).length) + "</dd>" +
      "</dl>";
    el("cap-status").textContent = "Đã tải review";
  } catch (e) { toast(e.message, "err"); }
}

async function generateCaption() {
  const taskId = el("cap-task").value.trim();
  if (!taskId) { toast("Nhập task id trước.", "err"); return; }
  const btn = el("btn-cap-generate");
  btn.disabled = true;
  btn.textContent = "Đang tạo…";
  try {
    const res = await api("/caption/generate", {
      method: "POST",
      body: JSON.stringify({ task_id: taskId, style: el("cap-style").value }),
    });
    el("cap-text").value = res.caption || "";
    el("cap-tags").value = (res.hashtags || []).join("\n");
    el("cap-status").textContent = "AI: " + (res.provider || "?") + " · " + (res.status || "");
    el("cap-body").innerHTML =
      "<dl class='kv'>" +
      "<dt>Provider</dt><dd>" + esc(res.provider) + (res.model ? " (" + esc(res.model) + ")" : "") + "</dd>" +
      "<dt>Tiêu đề AI</dt><dd>" + esc(res.title || "—") + "</dd>" +
      "<dt>Ngôn ngữ</dt><dd>" + esc(res.language || "—") + "</dd>" +
      "<dt>Điểm nội dung</dt><dd>" + num(res.score) + (res.score_reason ? " — " + esc(res.score_reason) : "") + "</dd>" +
      "<dt>Video nguồn</dt><dd class='muted'>" + esc(res.source.url) + "</dd>" +
      "<dt>Lượt xem / thích</dt><dd>" + num(res.source.views) + " / " + num(res.source.likes) + "</dd>" +
      "</dl>" +
      '<div class="notif"><div class="notif-kind">Phân biệt nguồn</div><div class="notif-msg">' +
      esc(res.reference.note) + "</div></div>" +
      (res.error ? '<div class="notif"><div class="notif-kind">Lỗi</div><div class="notif-msg">' +
        esc(res.error) + "</div></div>" : "");
    toast("Đã tạo caption.", "ok");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "AI tạo caption";
  }
}

async function saveCaption() {
  const taskId = el("cap-task").value.trim();
  if (!taskId) { toast("Nhập task id trước.", "err"); return; }
  const hashtags = el("cap-tags").value.split("\n").map((s) => s.trim()).filter(Boolean);
  try {
    await api("/reviews/caption", {
      method: "POST",
      body: JSON.stringify({ task_id: taskId, caption: el("cap-text").value, hashtags }),
    });
    el("cap-status").textContent = "Đã lưu lúc " + new Date().toLocaleTimeString("vi-VN");
    toast("Đã lưu caption.", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function saveProfile() {
  const name = el("disc-topic").value.trim();
  if (!name) { toast("Nhập chủ đề trước khi lưu cấu hình.", "err"); return; }
  const profile = {
    name,
    language: el("disc-language").value,
    market: el("disc-market").value,
    days: el("disc-days").value,
    min_views: el("disc-min-views").value,
    max_views: el("disc-max-views").value,
    min_likes: el("disc-min-likes").value,
    min_comments: el("disc-min-comments").value,
    min_shares: el("disc-min-shares").value,
    max_duration: el("disc-max-duration").value,
    must_include: el("disc-must").value,
    exclude: el("disc-exclude").value,
  };
  try {
    await api("/search-profiles", { method: "POST", body: JSON.stringify(profile) });
    toast("Đã lưu cấu hình tìm kiếm.", "ok");
    await loadSettings();
  } catch (e) { toast(e.message, "err"); }
}

async function loadProfile(name) {
  if (!name) return;
  try {
    const p = await api("/search-profiles");
    const profile = (p.profiles || []).find((x) => x.name === name);
    if (!profile) return;
    el("disc-language").value = profile.language || "";
    el("disc-market").value = profile.market || "";
    el("disc-days").value = profile.days || "";
    el("disc-min-views").value = profile.min_views || "";
    el("disc-max-views").value = profile.max_views || "";
    el("disc-min-likes").value = profile.min_likes || "";
    el("disc-min-comments").value = profile.min_comments || "";
    el("disc-min-shares").value = profile.min_shares || "";
    el("disc-max-duration").value = profile.max_duration || "";
    el("disc-must").value = profile.must_include || "";
    el("disc-exclude").value = profile.exclude || "";
    toast("Đã nạp cấu hình “" + name + "”.", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function deleteProfile(name) {
  try {
    await api("/search-profiles/delete", { method: "POST", body: JSON.stringify({ name }) });
    toast("Đã xóa cấu hình.", "ok");
    await loadSettings();
  } catch (e) { toast(e.message, "err"); }
}

async function saveSchedule() {
  const days = Array.from(el("sched-days").querySelectorAll("input:checked")).map((i) => i.value);
  try {
    await api("/settings", {
      method: "POST",
      body: JSON.stringify({
        schedule: {
          enabled: true,
          daily_time: el("sched-time").value,
          frequency: el("sched-freq").value,
          days,
          daily_limit: Number(el("sched-limit").value) || 1,
          topic: el("sched-topic").value.trim(),
        },
      }),
    });
    await api("/scheduler/start", { method: "POST", body: JSON.stringify({}) });
    toast("Đã lưu và bật lịch.", "ok");
    await loadScheduler();
  } catch (e) { toast(e.message, "err"); }
}

async function runScheduleNow() {
  try {
    const job = await api("/discovery/run");
    toast("Đã chạy một lượt: " + job.job_id, "ok");
    pollJob(job.job_id);
  } catch (e) { toast(e.message, "err"); }
}

async function saveSettings() {
  try {
    await api("/settings", {
      method: "POST",
      body: JSON.stringify({
        mode: el("set-mode").value,
        auto_post: el("set-autopost").value === "true",
      }),
    });
    toast("Đã lưu cấu hình.", "ok");
    await loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

async function emergencyStop() {
  if (!confirm("Dừng toàn bộ automation ngay? Các tác vụ đang chạy sẽ không tiếp tục.")) return;
  try {
    await api("/emergency-stop", { method: "POST", body: JSON.stringify({}) });
    toast("Đã dừng toàn bộ automation.", "ok");
    await loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

async function emergencyStart() {
  try {
    await api("/emergency-start", { method: "POST", body: JSON.stringify({}) });
    toast("Đã cho phép automation chạy lại.", "ok");
    await loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

async function editVideo() {
  const file = el("edit-file").value.trim();
  if (!file) { toast("Nhập đường dẫn file.", "err"); return; }
  el("edit-output").textContent = "Đang kiểm tra…";
  try {
    const res = await fetch("/api/editor/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: file,
        start: Number(el("edit-start").value) || 0,
        end: Number(el("edit-end").value) || 0,
      }),
    });
    const data = await res.json();
    el("edit-output").textContent = res.ok
      ? JSON.stringify(data, null, 2)
      : "Lỗi: " + (data.error || res.status);
  } catch (e) {
    el("edit-output").textContent = "Lỗi: " + e.message;
  }
}

async function loadNotifications() {
  try {
    const data = await api("/notifications");
    const items = data.notifications || [];
    const unread = items.filter((n) => !n.read).length;
    setBadge("badge-notif", unread);
    el("notif-list").innerHTML = items.length
      ? items.map((n) =>
          '<div class="notif' + (n.read ? " read" : "") + '">' +
          '<div class="notif-kind">' + esc(n.kind) + "</div>" +
          '<div class="notif-msg">' + esc(n.message) + "</div>" +
          '<div class="notif-at">' + esc(fmtDate(n.at)) + "</div></div>").join("")
      : '<div class="empty">Không có thông báo.</div>';
  } catch (e) { /* ignore */ }
}

/* ------------------------------------------------------------- init */

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });

  el("btn-refresh").addEventListener("click", () => { loadView(state.view); loadNotifications(); });
  el("btn-discover").addEventListener("click", () => runDiscovery(false));
  el("btn-discover-again").addEventListener("click", () => runDiscovery(false));
  el("btn-discover-resume").addEventListener("click", () => runDiscovery(true));
  el("btn-discover-stop").addEventListener("click", stopDiscovery);
  // The approve and reject buttons of the chosen video. Nothing is
  // downloaded and nothing is published by either of them.
  el("btn-approve-selected").addEventListener("click", () => {
    if (!state.selected) { toast("Chưa có video nào được chọn.", "err"); return; }
    approveCandidate(state.selected.source_url);
  });
  el("btn-reject-selected").addEventListener("click", () => {
    if (!state.selected) { toast("Chưa có video nào được chọn.", "err"); return; }
    rejectCandidate(state.selected.source_url);
  });
  el("disc-preview-select").addEventListener("change", (e) => {
    const url = e.target.value;
    if (url) playPreview(url);
  });
  el("btn-video-close").addEventListener("click", closeVideoDetail);
  el("video-modal").addEventListener("click", (e) => {
    if (e.target === el("video-modal")) closeVideoDetail();
  });
  el("btn-save-profile").addEventListener("click", saveProfile);
  el("disc-profiles").addEventListener("change", (e) => loadProfile(e.target.value));
  el("btn-cap-load").addEventListener("click", loadCaption);
  el("btn-cap-generate").addEventListener("click", generateCaption);
  el("btn-cap-save").addEventListener("click", saveCaption);
  el("btn-sched-save").addEventListener("click", saveSchedule);
  el("btn-sched-start").addEventListener("click", async () => {
    try {
      await api("/scheduler/start", { method: "POST", body: JSON.stringify({}) });
      toast("Đã bật lịch chạy nền.", "ok");
      await loadScheduler();
    } catch (e) { toast(e.message, "err"); }
  });
  el("btn-sched-run").addEventListener("click", runScheduleNow);
  el("btn-sched-pause").addEventListener("click", async () => {
    try {
      await api("/scheduler/stop", { method: "POST", body: JSON.stringify({}) });
      await api("/settings", {
        method: "POST",
        body: JSON.stringify({ schedule: { enabled: false } }),
      });
      toast("Đã tạm dừng lịch.", "ok");
      await loadScheduler();
    } catch (e) { toast(e.message, "err"); }
  });
  el("btn-set-save").addEventListener("click", saveSettings);
  el("btn-emergency").addEventListener("click", emergencyStop);
  el("btn-emergency-start").addEventListener("click", emergencyStart);
  el("btn-edit").addEventListener("click", editVideo);
  el("btn-notifications").addEventListener("click", () => {
    const drawer = el("notif-drawer");
    drawer.hidden = !drawer.hidden;
    if (!drawer.hidden) loadNotifications();
  });
  el("btn-notif-close").addEventListener("click", () => { el("notif-drawer").hidden = true; });

  el("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = el("chat-text");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    const log = el("chat-log");
    log.insertAdjacentHTML("beforeend",
      '<div class="msg user">' + esc(text) + "</div>");
    log.insertAdjacentHTML("beforeend",
      '<div class="msg bot">' + esc(assistantAnswer(text)) + "</div>");
    log.scrollTop = log.scrollHeight;
  });

  document.querySelectorAll(".chip[data-q]").forEach((chip) => {
    chip.addEventListener("click", () => {
      el("chat-text").value = chip.dataset.q;
      el("chat-form").dispatchEvent(new Event("submit"));
    });
  });

  el("disc-table").addEventListener("click", (e) => {
    const detail = e.target.closest("[data-detail]");
    if (detail) { openVideoDetail(detail.dataset.detail, detail); return; }
    const approve = e.target.closest("[data-approve]");
    if (approve) approveCandidate(approve.dataset.approve);
  });
  // The AI analysis panel carries its own preview, approve and reject
  // buttons for every candidate it shows.
  el("disc-analysis").addEventListener("click", (e) => {
    const preview = e.target.closest("[data-preview-url]");
    if (preview) { playPreview(preview.dataset.previewUrl); return; }
    const approve = e.target.closest("[data-approve]");
    if (approve) { approveCandidate(approve.dataset.approve); return; }
    const reject = e.target.closest("[data-reject]");
    if (reject) rejectCandidate(reject.dataset.reject);
  });
  el("appr-table").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-appr]");
    if (btn) approve(btn.dataset.task, btn.dataset.appr);
  });
  el("prof-table").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-delprof]");
    if (btn) deleteProfile(btn.dataset.delprof);
  });
}

async function init() {
  bindEvents();
  const hash = location.hash.replace("#", "");
  showView(TITLES[hash] ? hash : "overview");
  await loadOverview();
  loadNotifications();
  setInterval(loadNotifications, 20000);
}

// The hash can change without a click, for example when the browser restores
// a previous view or the user edits the address.
window.addEventListener("hashchange", () => {
  const name = location.hash.replace("#", "");
  if (TITLES[name] && name !== state.view) showView(name);
});

// The Escape key closes the modal, so the user can get back to the
// dashboard without hunting for the close button.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const modal = el("video-modal");
  if (modal && !modal.hidden) { closeVideoDetail(); return; }
  const drawer = el("notif-drawer");
  if (drawer && !drawer.hidden) { drawer.hidden = true; }
});

document.addEventListener("DOMContentLoaded", init);
