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
  top5: [],
  needsReview: [],
  verification: null,
  topicQueries: [],
  queryStats: {},
  queryTotal: 0,
  funnel: null,
  appliedFilters: null,
  langMarketNote: "",
  queue: null,
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

// The line that says what the local vision analyzer really saw. It
// names the model when a model read the picture, says the certainty of
// the reading, and says plainly when the machine could not read the
// text in the picture. It never claims more than what was measured.
function visionLine(a) {
  const v = a && a.local_vision;
  if (!v || typeof v !== "object") return "";
  const bits = [];

  const reading = v.reading || {};
  if (reading.from_model && reading.model) {
    const seen = [];
    if (reading.scene) seen.push(reading.scene);
    (reading.objects || []).slice(0, 3).forEach((o) => {
      if (o && o.label) seen.push(o.label + " " + Math.round((o.confidence || 0) * 100) + "%");
    });
    bits.push(
      "Mô hình vision " + reading.model + ": " + (seen.length ? seen.join(", ") : "không mô tả") +
      (reading.frames_read ? " (" + reading.frames_read + " khung hình)" : "")
    );
    if (reading.can_tell_ai_origin === false) {
      bits.push("mô hình chỉ đặt tên được nội dung, chưa chứng minh được nguồn gốc AI");
    }
  } else {
    bits.push("Chưa có mô hình vision trên máy — chỉ đo được đặc trưng hình ảnh");
  }

  const ui = v.production_ui || {};
  if (ui.score) {
    bits.push("giao diện sản xuất nhạc " + Math.round(ui.score * 100) + "%");
  }

  const motion = v.motion || {};
  if (motion.frames_used >= 2) {
    bits.push("hình thay đổi " + Math.round((motion.change || 0) * 100) + "%, nhất quán " + Math.round((motion.consistency || 0) * 100) + "%");
  }

  if (v.ocr_available === false && v.ocr_missing) {
    bits.push("Chưa đọc được chữ trong hình (thiếu runtime OCR)");
  }

  if (v.missing_dependency) {
    bits.push(v.missing_dependency);
  }

  if (!bits.length) return "";
  return "<div class='muted' style='margin-top:4px'>" + esc(bits.join(" · ")) + "</div>";
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

/* P4-A.2 friendly labels: never show raw backend enums in the UI. */
function friendlyRights(rights) {
  const r = String(rights || "").toUpperCase();
  if (r === "ALLOWLISTED_PERMITTED") return "Đã cấp quyền";
  if (r === "RIGHTS_REQUIRED" || r === "NEEDS_PERMISSION_REVIEW") return "Chưa có quyền";
  if (!rights) return "—";
  return String(rights);
}

function friendlyPubStatus(status) {
  const s = String(status || "").toUpperCase();
  if (s === "PUBLISH_UNKNOWN") return "Chưa xác nhận đăng";
  if (s === "PUBLISHED") return "Đã đăng";
  if (s === "CAPTION_READY") return "Sẵn sàng duyệt";
  if (s === "DRAFT") return "Bản nháp";
  if (s === "APPROVED") return "Đã duyệt";
  if (s === "SCHEDULED") return "Đã lên lịch";
  if (s === "UPLOADING") return "Đang đăng";
  if (s === "RIGHTS_REQUIRED") return "Cần xác minh quyền";
  if (s === "FAILED") return "Có lỗi";
  if (!status) return "—";
  return String(status);
}

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes());
}

function fromLocalInput(local) {
  if (!local) return "";
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return String(local);
  return d.toISOString();
}

function friendlySchedule(iso) {
  if (!iso) return "Đăng ngay khi chạy";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("vi-VN", { hour12: false, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/* ================= P4-A.6 appearance, locale, status labels ================= */
/* The locale dictionary is the single source of truth for every user facing
   string. The theme is a pure CSS concern, so the palette lives in tokens and
   the script only flips the data-theme attribute on the root element. */

const LOCALE_KEY = "tooldh.locale";
const THEME_KEY = "tooldh.theme";

const I18N = {
  vi: {
    "nav.workspace": "Không gian làm việc",
    "nav.overview": "Tổng quan",
    "nav.projects": "Dự án",
    "nav.videos": "Video Lab",
    "nav.library": "Thư viện",
    "nav.publishing": "Xuất bản",
    "nav.advanced": "Nâng cao",
    "nav.settings": "Cài đặt",
    "nav.trends": "Trend Analyzer",
    "nav.filter": "Video Filter",
    "nav.caption": "Caption & Hashtag",
    "nav.editor": "Video Editor",
    "nav.approval": "Approval Center",
    "nav.studio": "TikTok Studio",
    "nav.analytics": "Analytics",
    "nav.history": "History & Logs",

    "auto.running": "Đang hoạt động",
    "auto.stopped": "Đang tạm dừng",
    "auto.emergency": "Dừng khẩn cấp",
    "auto.resume": "Tiếp tục hoạt động",
    "auto.pause": "Tạm dừng tự động hóa",
    "auto.stopSchedule": "Dừng lịch chạy",
    "auto.startSchedule": "Bật lịch chạy",
    "auto.refresh": "Làm mới dữ liệu",
    "auto.state": "Trạng thái tự động hóa",
    "auto.emergencyOn": "Dừng khẩn cấp đang bật. Mọi tác vụ tự động đều bị chặn.",
    "auto.emergencyOff": "Không có dừng khẩn cấp. Tự động hóa có thể chạy.",
    "auto.scheduleOn": "Lịch chạy tự động đang chạy.",
    "auto.scheduleConfigured": "Lịch chạy đã cấu hình nhưng chưa chạy.",
    "auto.scheduleOff": "Lịch chạy tự động đang tắt.",
    "auto.next": "Lượt kế tiếp",
    "auto.noNext": "Chưa có lượt kế tiếp.",
    "auto.confirmStop": "Dừng toàn bộ tự động hóa? Mọi tác vụ đang chạy sẽ bị chặn.",
    "auto.confirmPause": "Tạm dừng tự động hóa? Bạn có thể tiếp tục bất cứ lúc nào.",
    "auto.doneStop": "Đã dừng toàn bộ tự động hóa.",
    "auto.doneResume": "Đã cho phép tự động hóa chạy lại.",
    "auto.donePause": "Đã tạm dừng tự động hóa.",
    "auto.doneSchedule": "Đã cập nhật lịch chạy.",
    "auto.failed": "Không thể cập nhật trạng thái. Đã khôi phục hiển thị cũ.",
    "auto.autoPublishOff": "Auto Publish đang tắt",
    "auto.autoDownloadOff": "Auto Download đang tắt",

    "notif.title": "Thông báo",
    "notif.empty": "Không có thông báo mới.",
    "notif.viewAll": "Xem tất cả",
    "notif.critical": "Cần xử lý",
    "notif.info": "Thông tin",

    "overview.auto": "Tự động hóa",
    "overview.blockers": "Vấn đề cần xử lý",
    "overview.activity": "Hoạt động gần đây",
    "overview.viewAll": "Xem tất cả",
    "overview.nextAction": "Hành động kế tiếp",
    "overview.scheduledAt": "Thời gian",
    "overview.configure": "Cấu hình",
    "overview.noActivity": "Chưa có hoạt động.",
    "overview.noBlockers": "Không có vấn đề nào cần xử lý.",

    "settings.appearance": "Giao diện & ngôn ngữ",
    "settings.theme": "Giao diện",
    "settings.themeHelp": "Áp dụng ngay, không cần tải lại trang.",
    "settings.language": "Ngôn ngữ",
    "settings.languageHelp": "Đổi ngôn ngữ hiển thị ngay trên toàn bộ giao diện.",
    "theme.light": "Sáng",
    "theme.dark": "Tối",
    "theme.system": "Theo hệ thống",

    "tab.overview": "Tổng quan",
    "tab.results": "Kết quả",
    "tab.versions": "Phiên bản",
    "tab.publish": "Xuất bản",
    "tab.history": "Lịch sử",

    "p1.search.start": "Bắt đầu tìm kiếm",
    "p1.search.filters": "Thiết lập bộ lọc",
    "p1.search.topic": "Chủ đề dùng để tìm",
    "p1.search.idle": "Chưa tìm kiếm",
    "p1.search.running": "Đang tìm kiếm…",
    "p1.search.done": "Đã tìm kiếm",
    "p1.search.error": "Lỗi tìm kiếm",
    "p1.empty.title": "Chưa có kết quả nghiên cứu",
    "p1.empty.note": "Dự án chưa có phiên bản. Bấm “Bắt đầu tìm kiếm” để tạo phiên bản đầu tiên.",
    "p1.empty.noteRuns": "Phiên bản này chưa có video nào.",
    "p1.empty.topic": "Chủ đề: ",
    "p1.noResults": "Chưa có kết quả nghiên cứu.",
    "p1.preview.empty": "Chưa có video để xem trước.",

    "status.DRAFT": "Bản nháp",
    "status.CAPTION_READY": "Sẵn sàng duyệt",
    "status.APPROVED": "Đã duyệt",
    "status.SCHEDULED": "Đã lên lịch",
    "status.UPLOADING": "Đang đăng",
    "status.PUBLISHED": "Đã đăng",
    "status.PUBLISH_UNKNOWN": "Chưa xác nhận đăng",
    "status.RIGHTS_REQUIRED": "Cần xác minh quyền",
    "status.FAILED": "Có lỗi",
    "status.IDLE": "Đang chờ",
    "status.RUNNING": "Đang chạy",
    "status.PAUSED": "Đã tạm dừng",
    "status.COMPLETED": "Hoàn tất",
    "status.QUEUED": "Đang chờ chạy",
    "status.ALLOWLISTED_PERMITTED": "Đã cấp quyền",
    "status.NO_QUALIFIED_VIDEO": "Không có video đạt yêu cầu",
    "status.CANDIDATE_FOUND": "Đã tìm thấy video",

    "common.cancel": "Hủy",
    "common.close": "Đóng",
    "common.saving": "Đang lưu…",
    "common.loading": "Đang tải…",
    "common.empty": "Chưa có dữ liệu.",
  },
  en: {
    "nav.workspace": "Workspace",
    "nav.overview": "Overview",
    "nav.projects": "Projects",
    "nav.videos": "Video Lab",
    "nav.library": "Library",
    "nav.publishing": "Publishing",
    "nav.advanced": "Advanced",
    "nav.settings": "Settings",
    "nav.trends": "Trend Analyzer",
    "nav.filter": "Video Filter",
    "nav.caption": "Caption & Hashtag",
    "nav.editor": "Video Editor",
    "nav.approval": "Approval Center",
    "nav.studio": "TikTok Studio",
    "nav.analytics": "Analytics",
    "nav.history": "History & Logs",

    "auto.running": "Running",
    "auto.stopped": "Paused",
    "auto.emergency": "Emergency stop",
    "auto.resume": "Resume automation",
    "auto.pause": "Pause automation",
    "auto.stopSchedule": "Stop schedule",
    "auto.startSchedule": "Start schedule",
    "auto.refresh": "Refresh data",
    "auto.state": "Automation state",
    "auto.emergencyOn": "Emergency stop is on. Every automated task is blocked.",
    "auto.emergencyOff": "No emergency stop. Automation can run.",
    "auto.scheduleOn": "The automatic schedule is running.",
    "auto.scheduleConfigured": "The schedule is configured but not running.",
    "auto.scheduleOff": "The automatic schedule is off.",
    "auto.next": "Next run",
    "auto.noNext": "No next run scheduled.",
    "auto.confirmStop": "Stop all automation? Every running task will be blocked.",
    "auto.confirmPause": "Pause automation? You can resume it at any time.",
    "auto.doneStop": "All automation has been stopped.",
    "auto.doneResume": "Automation is allowed to run again.",
    "auto.donePause": "Automation has been paused.",
    "auto.doneSchedule": "The schedule has been updated.",
    "auto.failed": "The state could not be updated. The display was restored.",
    "auto.autoPublishOff": "Auto Publish is off",
    "auto.autoDownloadOff": "Auto Download is off",

    "notif.title": "Notifications",
    "notif.empty": "No new notifications.",
    "notif.viewAll": "View all",
    "notif.critical": "Needs attention",
    "notif.info": "Information",

    "overview.auto": "Automation",
    "overview.blockers": "Issues to handle",
    "overview.activity": "Recent activity",
    "overview.viewAll": "View all",
    "overview.nextAction": "Next action",
    "overview.scheduledAt": "Scheduled",
    "overview.configure": "Configure",
    "overview.noActivity": "No activity yet.",
    "overview.noBlockers": "No issues need handling.",

    "settings.appearance": "Appearance & language",
    "settings.theme": "Appearance",
    "settings.themeHelp": "Applies instantly, no reload needed.",
    "settings.language": "Language",
    "settings.languageHelp": "Switches the whole interface instantly.",
    "theme.light": "Light",
    "theme.dark": "Dark",
    "theme.system": "Follow system",

    "tab.overview": "Overview",
    "tab.results": "Results",
    "tab.versions": "Versions",
    "tab.publish": "Publishing",
    "tab.history": "History",

    "p1.search.start": "Start search",
    "p1.search.filters": "Filter settings",
    "p1.search.topic": "Topic used for the search",
    "p1.search.idle": "Not searched yet",
    "p1.search.running": "Searching…",
    "p1.search.done": "Search complete",
    "p1.search.error": "Search failed",
    "p1.empty.title": "No research results yet",
    "p1.empty.note": "This project has no version yet. Click “Start search” to create the first version.",
    "p1.empty.noteRuns": "This version has no video yet.",
    "p1.empty.topic": "Topic: ",
    "p1.noResults": "No research results yet.",
    "p1.preview.empty": "No video to preview yet.",

    "status.DRAFT": "Draft",
    "status.CAPTION_READY": "Ready for review",
    "status.APPROVED": "Approved",
    "status.SCHEDULED": "Scheduled",
    "status.UPLOADING": "Uploading",
    "status.PUBLISHED": "Published",
    "status.PUBLISH_UNKNOWN": "Publication unconfirmed",
    "status.RIGHTS_REQUIRED": "Rights need review",
    "status.FAILED": "Failed",
    "status.IDLE": "Waiting",
    "status.RUNNING": "Running",
    "status.PAUSED": "Paused",
    "status.COMPLETED": "Completed",
    "status.QUEUED": "Queued",
    "status.ALLOWLISTED_PERMITTED": "Rights granted",
    "status.NO_QUALIFIED_VIDEO": "No video met the filters",
    "status.CANDIDATE_FOUND": "Video found",

    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.saving": "Saving…",
    "common.loading": "Loading…",
    "common.empty": "No data yet.",
  },
};

const UI = {
  locale: "vi",
  theme: "light",
};

function t(key) {
  const dict = I18N[UI.locale] || I18N.vi;
  return dict[key] || (I18N.vi[key] || key);
}

/* The raw backend enums never reach the interface. They are mapped here so a
   new enum falls back to the original value instead of an empty label. */
function statusLabel(value) {
  const raw = String(value == null ? "" : value).toUpperCase();
  if (!raw) return "—";
  return t("status." + raw);
}

function readStored(key, allowed, fallback) {
  try {
    const value = localStorage.getItem(key);
    if (value && allowed.indexOf(value) !== -1) return value;
  } catch (_) { /* private mode */ }
  return fallback;
}

function storeValue(key, value) {
  try { localStorage.setItem(key, value); } catch (_) { /* private mode */ }
}

/* ----------------------- theme ----------------------- */

function systemPrefersDark() {
  try {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  } catch (_) { return false; }
}

function resolvedTheme() {
  if (UI.theme === "system") return systemPrefersDark() ? "dark" : "light";
  return UI.theme === "dark" ? "dark" : "light";
}

function applyTheme() {
  const theme = resolvedTheme();
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#1C1D1F" : "#EDEEEB");
}

function setTheme(theme) {
  UI.theme = ["light", "dark", "system"].indexOf(theme) !== -1 ? theme : "light";
  storeValue(THEME_KEY, UI.theme);
  applyTheme();
  const sel = el("set-theme");
  if (sel) sel.value = UI.theme;
}

/* ----------------------- locale ----------------------- */

const SUBTITLES = {
  vi: {
    "overview.sub": "Trạng thái thật của hệ thống.",
    "assistant.sub": "Trợ lý đọc trạng thái thật, không tự hành động.",
    "discovery.sub": "Tạo, tìm kiếm và mở dự án. Mỗi dự án giữ riêng phiên bản, video và lịch sử.",
    "trends.sub": "Điểm xu hướng và lý do mỗi video được chọn hoặc loại.",
    "filter.sub": "Mỗi lượt chỉ chọn một video tốt nhất.",
    "caption.sub": "Soạn và sửa caption trước khi duyệt.",
    "videos.sub": "Đo thật bằng FFprobe/FFmpeg, tải duy nhất 1 video đủ quyền.",
    "videoslib.sub": "Media đã tải, đã hash và đã xử lý.",
    "editor.sub": "Kiểm tra và cắt video bằng backend.",
    "approval.sub": "Duyệt tải video và duyệt đăng video là hai quyền riêng.",
    "scheduler.sub": "Caption → Duyệt → Lịch → Đăng. Chỉ ghi nhận đã đăng khi có URL xác minh.",
    "studio.sub": "Bản nháp. Không tự đăng công khai.",
    "analytics.sub": "Thống kê hiệu quả từ dữ liệu thật.",
    "history.sub": "Lịch sử đăng bài và nhật ký hoạt động.",
    "settings.sub": "Cấu hình, giao diện và quyền truy cập.",
  },
  en: {
    "overview.sub": "The real state of the system.",
    "assistant.sub": "A read only helper. It never acts on its own.",
    "discovery.sub": "Create, search and open projects. Every project keeps its own versions, videos and history.",
    "trends.sub": "Trend scores and the reason every video was selected or dropped.",
    "filter.sub": "Every run selects only the single best video.",
    "caption.sub": "Write and edit the caption before approval.",
    "videos.sub": "Measured with FFprobe/FFmpeg. Only one fully cleared video is downloaded.",
    "videoslib.sub": "Downloaded media, hashed and processed.",
    "editor.sub": "Inspect and cut video on the backend.",
    "approval.sub": "Approving a download and approving a publication are two separate rights.",
    "scheduler.sub": "Caption → Approve → Schedule → Publish. A post is only counted as published with a verified URL.",
    "studio.sub": "A draft. Nothing is published publicly.",
    "analytics.sub": "Performance from real data.",
    "history.sub": "Publication history and the activity log.",
    "settings.sub": "Configuration, appearance and access rights.",
  },
};

const TITLE_KEYS = {
  overview: ["nav.overview", "overview.sub", "nav.overview"],
  assistant: ["nav.assistant", "assistant.sub", "nav.assistant"],
  discovery: ["nav.projects", "discovery.sub", "nav.projects"],
  trends: ["nav.trends", "trends.sub", "nav.trends"],
  filter: ["nav.filter", "filter.sub", "nav.filter"],
  caption: ["nav.caption", "caption.sub", "nav.caption"],
  videos: ["nav.videos", "videos.sub", "nav.videos"],
  videoslib: ["nav.library", "videoslib.sub", "nav.library"],
  editor: ["nav.editor", "editor.sub", "nav.editor"],
  approval: ["nav.approval", "approval.sub", "nav.approval"],
  scheduler: ["nav.publishing", "scheduler.sub", "nav.publishing"],
  studio: ["nav.studio", "studio.sub", "nav.studio"],
  analytics: ["nav.analytics", "analytics.sub", "nav.analytics"],
  history: ["nav.history", "history.sub", "nav.history"],
  settings: ["nav.settings", "settings.sub", "nav.settings"],
};

function titleLocalized(name) {
  const entry = TITLE_KEYS[name];
  if (!entry) return TITLES[name] || ["TOOLTDH", "", ""];
  const subs = SUBTITLES[UI.locale] || SUBTITLES.vi;
  return [t(entry[0]), subs[entry[1]] || "", t(entry[2])];
}

/* The navigation labels are translated in place so the markup, the order and
   the advanced group stay exactly as they are. */
const NAV_LOCALE_KEYS = {
  overview: "nav.overview",
  discovery: "nav.projects",
  videos: "nav.videos",
  videoslib: "nav.library",
  scheduler: "nav.publishing",
  trends: "nav.trends",
  filter: "nav.filter",
  caption: "nav.caption",
  editor: "nav.editor",
  approval: "nav.approval",
  studio: "nav.studio",
  analytics: "nav.analytics",
  history: "nav.history",
  settings: "nav.settings",
};

function renderNavigation() {
  document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
    const key = NAV_LOCALE_KEYS[btn.dataset.view];
    if (!key) return;
    const label = btn.querySelector(".nav-item-label");
    if (label) label.textContent = t(key);
  });
  const group = document.querySelector("#nav .nav-group:not(.nav-toggle)");
  if (group) group.textContent = t("nav.workspace");
  const toggle = el("nav-advanced-toggle");
  if (toggle && toggle.childNodes[0] && toggle.childNodes[0].nodeType === 3) {
    toggle.childNodes[0].nodeValue = t("nav.advanced") + " ";
  }
}

function renderViewChrome() {
  const localized = titleLocalized(state.view);
  el("view-title").textContent = localized[0];
  el("view-sub").textContent = localized[1] || "";
  if (el("crumbs")) {
    el("crumbs").innerHTML = "<span>TOOLTDH Pro</span><span class='crumb-sep'>/</span><span>" +
      esc(localized[2] || localized[0]) + "</span>";
  }
  document.querySelectorAll("[data-i18n-tab]").forEach((tab) => {
    const value = t(tab.getAttribute("data-i18n-tab"));
    if (value) tab.textContent = value;
  });
}

function applyLocale() {
  UI.locale = readStored(LOCALE_KEY, ["vi", "en"], "vi");
  document.documentElement.setAttribute("lang", UI.locale);
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = t(node.getAttribute("data-i18n"));
    if (value) node.textContent = value;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const value = t(node.getAttribute("data-i18n-placeholder"));
    if (value) node.setAttribute("placeholder", value);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    const value = t(node.getAttribute("data-i18n-title"));
    if (value) node.setAttribute("title", value);
  });
  renderNavigation();
  renderViewChrome();
  renderAutomationControl();
  renderSettingsAppearance();
  if (typeof renderOverviewAutomation === "function") renderOverviewAutomation();
  // The project workspace has its own texts, so they follow the locale too.
  if (typeof renderTop5 === "function") renderTop5();
  if (typeof renderProjectEmptyState === "function") renderProjectEmptyState();
}

function setLocale(locale) {
  UI.locale = locale === "en" ? "en" : "vi";
  storeValue(LOCALE_KEY, UI.locale);
  applyLocale();
}

function renderSettingsAppearance() {
  const themeSel = el("set-theme");
  if (themeSel) themeSel.value = UI.theme;
  const localeSel = el("set-locale");
  if (localeSel) localeSel.value = UI.locale;
}

/* ---------------------------------------------------------- routing */

const TITLES = {
  overview: ["Tổng quan", "Trạng thái thật của hệ thống.", "Tổng quan"],
  assistant: ["AI Assistant", "Trợ lý đọc trạng thái thật, không tự hành động.", "Nâng cao / AI Assistant"],
  discovery: ["Dự án", "Tạo, tìm kiếm và mở dự án. Mỗi dự án giữ riêng phiên bản, video và lịch sử.", "Dự án"],
  trends: ["Trend Analyzer", "Điểm xu hướng và lý do mỗi video được chọn hoặc loại.", "Nâng cao / Trend Analyzer"],
  filter: ["Video Filter", "Mỗi lượt chỉ chọn một video tốt nhất.", "Nâng cao / Video Filter"],
  caption: ["Caption & Hashtag Studio", "Soạn và sửa caption trước khi duyệt.", "Nâng cao / Caption & Hashtag"],
  videos: ["Video Lab", "Đo thật bằng FFprobe/FFmpeg, tải duy nhất 1 video đủ quyền.", "Video Lab"],
  videoslib: ["Thư viện", "Media đã tải, đã hash và đã xử lý.", "Thư viện"],
  editor: ["Video Editor", "Kiểm tra và cắt video bằng backend.", "Nâng cao / Video Editor"],
  approval: ["Approval Center", "Duyệt tải video và duyệt đăng video là hai quyền riêng.", "Nâng cao / Approval Center"],
  scheduler: ["Xuất bản nội dung", "Caption → Duyệt → Lịch → Đăng. Chỉ ghi nhận đã đăng khi có URL xác minh.", "Xuất bản"],
  studio: ["TikTok Studio", "Bản nháp. Không tự đăng công khai.", "Nâng cao / TikTok Studio"],
  analytics: ["Analytics", "Thống kê hiệu quả từ dữ liệu thật.", "Nâng cao / Analytics"],
  history: ["History & Logs", "Lịch sử đăng bài và nhật ký hoạt động.", "Nâng cao / History & Logs"],
  settings: ["Cài đặt", "Cấu hình và quyền truy cập.", "Cài đặt"],
};

function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => {
    v.classList.toggle("active", v.dataset.view === name);
  });
  document.querySelectorAll(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
  const title = titleLocalized(name);
  el("view-title").textContent = title[0];
  el("view-sub").textContent = title[1] || "";
  if (el("crumbs")) el("crumbs").innerHTML = "<span>TOOLTDH Pro</span><span class='crumb-sep'>/</span><span>" + esc(title[2] || title[0]) + "</span>";
  location.hash = name;
  // A new page starts at the top so the workspace never opens halfway
  // through the previous page.
  window.scrollTo(0, 0);
  const content = el("content");
  if (content) content.scrollTop = 0;
  loadView(name);
}

function loadView(name) {
  if (name === "overview") return loadOverview();
  if (name === "discovery") return loadProjectSummary();
  if (name === "trends") return loadTrendView();
  if (name === "filter") return loadFilterView();
  if (name === "approval") return loadApprovals();
  if (name === "scheduler") return loadScheduler();
  if (name === "videos") return loadDiscovery();
  if (name === "videoslib") return loadLibrary();
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

  el("mode-chip").textContent = data.mode === "approve" ? "Chế độ duyệt thủ công" : "Chế độ tự động";
  el("account-chip").textContent = "Tài khoản: " + (data.expected_account || "—");

  // The header control always mirrors the confirmed backend state.
  automationState.overview = data;
  renderAutomationControl();

  // The project counts come from the project-scoped summary so the overview
  // never mixes numbers from different scopes.
  let projects = [];
  try {
    const sum = await api("/p1/projects/summary");
    projects = sum.projects || [];
  } catch (_) { /* offline ok */ }
  const activeProjects = projects.filter((p) => Number(p.versions || 0) > 0 || Number(p.publications || 0) > 0).length;
  const pendingApproval = projects.reduce((sum, p) => sum + Number(p.pending_approval || 0), 0);
  const verifiedPublished = projects.reduce((sum, p) => sum + Number(p.published_verified || 0), 0);

  const c = data.counts || {};
  const cards = [
    ["Dự án đang hoạt động", activeProjects, "có phiên bản hoặc bài đăng", "accent"],
    ["Chờ duyệt", pendingApproval, "bài cần bạn duyệt", pendingApproval ? "warn" : ""],
    ["Đã đăng (xác minh)", verifiedPublished, "có URL xác nhận", verifiedPublished ? "ok" : ""],
    ["Thư viện", c.library, "media đã tải", ""],
    ["Vấn đề", (data.blockers || []).length, "cần xử lý", (data.blockers || []).length ? "danger" : ""],
  ];
  el("ov-stats").innerHTML = cards.map(([label, value, sub, kind]) =>
    '<div class="stat ' + (kind || "") + '">' +
    '<div class="stat-label">' + esc(label) + "</div>" +
    '<div class="stat-value">' + num(value) + "</div>" +
    '<div class="stat-sub">' + esc(sub) + "</div></div>"
  ).join("");

  // Repeated blocker reasons are grouped so the overview stays short. A
  // filter rejection carries its own URL, so the reason is normalized before
  // the count is taken.
  const grouped = new Map();
  (data.blockers || []).forEach((b) => {
    const raw = String(b || "").trim();
    if (!raw) return;
    const key = normalizeBlocker(raw);
    const entry = grouped.get(key);
    if (entry) entry.count += 1;
    else grouped.set(key, { count: 1, sample: raw });
  });
  const blockerRows = Array.from(grouped.entries());
  el("ov-blocker-count").textContent = String(blockerRows.length);
  el("ov-blockers").innerHTML = blockerRows.length
    ? blockerRows.slice(0, 3).map(([reason, info]) =>
        '<div class="issue-group"><span class="issue-count">' + num(info.count) + '</span>' +
        '<span>' + esc(reason) + "</span></div>").join("") +
      (blockerRows.length > 3
        ? '<button class="link-btn" id="btn-ov-blocker-more">' + esc(t("overview.viewAll")) +
          " (" + num(blockerRows.length - 3) + ")</button>"
        : "")
    : '<div class="empty">' + esc(t("overview.noBlockers")) + "</div>";
  const moreBlockers = el("btn-ov-blocker-more");
  if (moreBlockers) moreBlockers.addEventListener("click", () => showView("history"));

  const s = data.schedule || {};
  el("ov-sched-state").textContent = s.enabled ? t("auto.running") : t("auto.stopped");
  el("ov-sched-state").className = "tag " + (s.enabled ? "tag-ok" : "");

  // At most five recent meaningful events, never a raw log dump.
  const events = [];
  (data.recent_tasks || []).forEach((t) => events.push({
    at: String(t.updated_at || ""),
    kind: String(t.status || ""),
    text: "Tác vụ " + (t.task_id || ""),
  }));
  (data.recent_reviews || []).forEach((r) => events.push({
    at: String(r.created_at || ""),
    kind: String(r.status || ""),
    text: "Review " + (r.topic || r.task_id || "") + " · " + num(r.candidate_count) + " ứng viên",
  }));
  events.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  const activity = el("ov-activity");
  if (activity) {
    activity.innerHTML = events.length
      ? events.slice(0, 5).map((e) =>
          '<div class="notif"><div class="notif-kind">' + esc(friendlySchedule(e.at)) + "</div>" +
          '<div class="notif-msg">' + esc(e.text) + " · " + tag(friendlyTaskStatus(e.kind), statusKind(e.kind)) + "</div></div>").join("")
      : '<div class="empty">' + esc(t("overview.noActivity")) + "</div>";
  }

  renderOverviewAutomation();
}

/* The automation card is a compact strip: the current state, the next
   scheduled action, the time and a link to the configuration. */
function renderOverviewAutomation() {
  const box = el("ov-schedule");
  if (!box) return;
  const data = automationState.overview || state.overview || {};
  const s = data.schedule || {};
  const facts = automationFacts();
  const scheduler = facts.scheduler || {};
  // The next run time comes from the live scheduler when it runs, and from the
  // stored schedule otherwise.
  const nextAt = scheduler.next_run || s.next_run || "";
  const nextText = nextAt ? friendlySchedule(nextAt) : t("auto.noNext");
  const topic = String(s.topic || scheduler.topic || "").trim();
  const label = facts.emergency ? t("auto.emergency") : (facts.scheduleEnabled ? t("auto.running") : t("auto.stopped"));
  const detail = facts.emergency ? t("auto.emergencyOn") : (topic ? topic : t("auto.scheduleOff"));
  box.innerHTML =
    '<div class="auto-strip">' +
    '<div class="auto-strip-main">' +
    '<span class="status-dot ' + (facts.emergency ? "is-emergency" : (facts.scheduleEnabled ? "is-running" : "is-stopped")) + '"></span>' +
    '<span class="auto-strip-label">' + esc(label) + "</span>" +
    '<span class="auto-strip-detail">' + esc(detail) + "</span>" +
    "</div>" +
    '<span class="auto-strip-detail">' + esc(t("overview.nextAction")) + ": " +
    esc(s.enabled ? t("auto.running") : t("auto.stopped")) + "</span>" +
    '<span class="auto-strip-detail">' + esc(t("overview.scheduledAt")) + ": " + esc(nextText) + "</span>" +
    '<button class="link-btn auto-strip-link" id="btn-ov-configure">' + esc(t("overview.configure")) + "</button>" +
    "</div>";
  const configure = el("btn-ov-configure");
  if (configure) configure.addEventListener("click", () => showView("scheduler"));
}

function friendlyTaskStatus(status) {
  const s = String(status || "").toUpperCase();
  if (!s) return "—";
  // The status labels live in the locale dictionary, so the overview and the
  // tables always show the same wording.
  const known = ["COMPLETED", "RUNNING", "FAILED", "BLOCKED", "AWAITING_SELECTION", "SELECTED",
    "DRAFT_SAVED", "AWAITING_APPROVAL", "PUBLISHED", "REJECTED", "HOLD", "QUEUED", "PAUSED"];
  if (known.indexOf(s) !== -1) return statusLabel(s);
  return String(status);
}

/* A filter rejection repeats the same reason for every video, but each line
   also carries its own URL and its own measured value. The URL and the number
   are removed so the reasons can be counted as one group instead of many
   near identical rows. */
function normalizeBlocker(raw) {
  let text = String(raw || "").trim();
  // "Loại theo bộ lọc — <url>: <reason>" becomes "<head> — <reason>".
  const match = text.match(/^(.*?)\s+—\s+\S*https?:\/\/\S*?\s*:\s*(.+)$/);
  if (match) {
    const reason = match[2].trim();
    const head = match[1].trim();
    text = head ? head + " — " + reason : reason;
  }
  // Any remaining URL is removed.
  text = text.replace(/https?:\/\/\S+/g, "");
  // The measured value differs for every video, so it is replaced by a
  // marker to let the same reason share one group.
  text = text.replace(/\b\d[\d.,]*\b/g, "#");
  return text.replace(/\s{2,}/g, " ").trim();
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
  // The badge belongs to the legacy discovery workspace. It is optional, so
  // a missing badge must never break the caller.
  if (badge) {
    badge.textContent = info.label;
    badge.className = "tag " + (info.kind || "");
  }
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
    min_duration: val("disc-min-duration"),
    max_days: val("disc-days"),
    must_include: val("disc-must"),
    must_include_any: val("disc-must-any"),
    subtopics: val("disc-subtopics"),
    language: val("disc-language"),
    market: val("disc-market"),
    exclude: val("disc-exclude"),
  };
}

async function loadDiscovery() {
  // When a project is open, its own saved result is shown. The global
  // discovery result of another project is never used here.
  if (p1state.projectId) {
    await loadProjectRunResult();
    loadQueue();
    return;
  }
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
      state.top5 = data.top5 || [];
      state.needsReview = data.needs_review || [];
      state.verification = data.verification || null;
      state.topicQueries = data.topic_queries || [];
      state.queryStats = data.query_stats || {};
      state.queryTotal = data.query_total_returned || 0;
      state.funnel = data.funnel || null;
      state.appliedFilters = data.applied_filters || data.filters || null;
      state.langMarketNote = data.language_market_note || "";
      setRunStatus(data.status);
    }
  } catch (e) { /* the last result is optional */ }
  renderDiscovery();
  loadQueue();
}

function renderDiscovery() {
  // The candidate table belongs to the open project. It is painted from the
  // project scoped run, so a result of another project can never appear here.
  const inScope = p1RunBelongsToCurrentScope();
  const rows = inScope ? (p1runstate.videos || []) : [];
  el("disc-count").textContent = rows.length ? rows.length + " ứng viên" : "0 ứng viên";

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
        "<td><a href='" + esc(c.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>" +
          esc((c.title || c.source_url).slice(0, 60)) + "</a>" +
          "<div class='muted'>" + esc(c.creator || "") + "</div></td>" +
        "<td class='num'>" + metric(c.views, known) + "</td>" +
        "<td class='num'>" + metric(c.likes, known) + "</td>" +
        "<td class='num'>" + metric(c.comments, known) + "</td>" +
        "<td class='num'>" + metric(c.shares, known) + "</td>" +
        "<td class='num'>" + (c.duration_seconds ? Number(c.duration_seconds).toFixed(1) + "s" : "—") + "</td>" +
        "<td class='muted'>" + esc(c.posted_at || "—") + "</td>" +
        "<td class='num'>" + (score ? score.score : num(c.score)) + "</td>" +
        "<td>" + (score ? tag(score.decision, statusKind(score.decision)) : tag(c.status, statusKind(c.status))) + "</td>" +
        "<td><button class='btn btn-xs' data-detail='" + esc(c.source_url) + "'>Xem</button>" +
        (isSelected ? " <button class='btn btn-xs' data-approve='" + esc(c.source_url) + "'>Duyệt</button>" : "") +
        "</td>" +
        "</tr>";
    }).join("") : emptyRow(11, t("p1.noResults"))) +
    "</tbody>";

  renderSelected();
  renderAnalysis();
  renderTrends();
  renderFilter();
  renderTop5();
}

function fmtAge(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return "—";
  return n === 1 ? "1 ngày" : n + " ngày";
}

/* The videos that still need a manual look. They come from the project
   scoped run, so they always belong to the open project. */
function renderNeedsReview() {
  const items = p1RunBelongsToCurrentScope() ? (p1runstate.videos || []) : [];
  const pending = items.filter((v) => String(v.status || "") !== "VERIFIED");
  if (!pending.length) return "";
  return '<div class="card" style="margin-top:8px"><strong>Cần xem lại (' + pending.length + ")</strong>" +
    '<div class="muted">Đạt điều kiện metadata nhưng nội dung chưa đủ bằng chứng. Không tự động đăng.</div>' +
    pending.slice(0, 5).map((n) =>
      "<div class='muted' style='margin-top:6px'><a href='" + esc(n.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>" +
      esc((n.title || n.source_url || "").slice(0, 80)) + "</a>" +
      "<div>@" + esc(n.creator || "") + " · " + num(n.views) + " views · đăng " + esc(n.posted_at || "—") +
      " · điểm xu hướng " + num(n.trend ?? n.trend_score ?? n.score ?? 0) + " · quyền: " + esc(n.rights || "—") + "</div>" +
      "<div>" + esc(n.reason || "") + (n.user_confirmed ? " · ĐÃ XÁC MINH THỦ CÔNG" : "") + "</div>" +
      "<div class='row' style='margin-top:4px'><button class='btn btn-xs' data-confirm-content='" + esc(n.source_url) + "'>Xác nhận nội dung</button>" +
      " <button class='btn btn-xs btn-danger' data-dismiss-content='" + esc(n.source_url) + "'>Loại bỏ</button></div></div>"
    ).join("") + "</div>";
}

/* The results of a project are painted from the project scoped run state
   only. The global discovery state belongs to another workspace and is never
   used here, so a result of an older project can never leak into the open
   project. */
function renderTop5() {
  const box = el("disc-top5");
  if (!box) return;
  const inScope = p1RunBelongsToCurrentScope();
  const cards = inScope ? (p1runstate.top5 || []) : [];
  const counter = el("disc-top5-count");
  if (counter) counter.textContent = cards.length ? cards.length + "/5 đề xuất" : "0 đề xuất";

  // The search facts are shown as a compact strip. The long query log is
  // deliberately kept out of the interface.
  const meta = [];
  const fl = inScope ? p1runstate.funnel : null;
  if (fl) {
    meta.push("RAW " + (fl.raw || 0) + " → DEDUP " + (fl.dedup || 0) +
      " → LỌC " + (fl.filtered || 0) + " → ĐẠT " + (fl.verified || 0));
  }
  const filters = inScope ? p1runstate.filters : null;
  if (filters) {
    const dur = (filters.min_duration || filters.max_duration)
      ? ("thời lượng " + (filters.min_duration || 0) + "–" + (filters.max_duration || "∞") + "s")
      : "thời lượng không giới hạn";
    meta.push("Lọc: views≥" + (filters.min_views || 0) + " · " + dur +
      " · ≤" + (filters.max_days || "∞") + " ngày");
  }
  const strip = el("disc-search-stats");
  if (strip) {
    strip.innerHTML = meta.length
      ? meta.map((m) => '<span class="info-chip">' + esc(m) + "</span>").join("")
      : '<span class="info-chip">' + esc(t("p1.noResults")) + "</span>";
  }
  if (!cards.length) {
    box.innerHTML = '<div class="empty">' + esc(t("p1.noResults")) + "</div>";
    return;
  }
  box.innerHTML = cards.map((c, i) => {
    const pick = !!c.pick;
    const status = String(c.status || (c.certainty === "HIGH" ? "VERIFIED" : "NEEDS_REVIEW"));
    const statusTag = status === "VERIFIED"
      ? ' <span class="tag tag-ok">VERIFIED</span>'
      : ' <span class="tag tag-warn">NEEDS_REVIEW</span>';
    const confirmedTag = c.user_confirmed ? ' <span class="tag tag-accent">ĐÃ XÁC MINH THỦ CÔNG</span>' : "";
    const posted = c.posted_at ? " · đăng " + esc(c.posted_at) : "";
    const dur = (c.duration_seconds ? Number(c.duration_seconds).toFixed(1) + "s" : (c.duration_unknown ? "thời lượng UNKNOWN" : "—"));
    let action = "";
    if (pick) {
      action = "<button class='btn btn-xs btn-primary' data-enqueue='" + esc(c.source_url) + "'>Xếp hàng</button>";
    } else if (status === "NEEDS_REVIEW") {
      if (c.user_confirmed) {
        action = "<button class='btn btn-xs btn-primary' data-enqueue='" + esc(c.source_url) + "'>Xếp hàng (đã xác minh thủ công)</button>"
          + " <button class='btn btn-xs btn-danger' data-dismiss-content='" + esc(c.source_url) + "'>Loại bỏ</button>";
      } else {
        action = "<button class='btn btn-xs' data-confirm-content='" + esc(c.source_url) + "'>Xác nhận nội dung</button>"
          + " <button class='btn btn-xs btn-danger' data-dismiss-content='" + esc(c.source_url) + "'>Loại bỏ</button>";
      }
    }
    return "<div class='top5-row" + (pick ? " is-pick" : "") + "'><div class='top5-rank'>" + (i + 1) + "</div>" +
      "<div><div class='top5-title'>" +
      "<a href='" + esc(c.source_url) + "' target='_blank' rel='noreferrer'>" +
      esc((c.title || c.source_url || "").slice(0, 80)) + "</a></div>" +
      "<div class='top5-meta'>@" + esc(c.creator || "") + " · " + num(c.views) + " views · " + dur + " · " +
      fmtAge(c.age_days) + posted + " · quyền: " + esc(c.rights || "—") + "</div>" +
      (c.reason ? "<div class='top5-meta'>" + esc(c.reason) + "</div>" : "") +
      "</div><div class='top5-side'><span class='top5-score'>" + num(c.score) + "đ</span>" +
      "<span>" + esc(c.certainty || "UNKNOWN") + statusTag + confirmedTag + "</span>" +
      (action ? "<div class='top5-actions'>" + action + "</div>" : "") +
      "</div></div>";
  }).join("") + renderNeedsReview();
}

async function loadQueue() {
  const box = el("queue-table");
  if (!box) return;
  try {
    const q = await api("/queue");
    state.queue = q;
    const tasks = q.tasks || [];
    box.innerHTML =
      "<thead><tr><th>Task</th><th>Nguồn</th><th>Lịch</th><th>Trạng thái</th></tr></thead><tbody>" +
      (tasks.length ? tasks.slice(-20).map((t) =>
        "<tr><td>" + esc(t.task_id) + "</td>" +
        "<td class='muted'>" + esc((t.source_url || "").slice(0, 60)) + "</td>" +
        "<td class='muted'>" + esc(fmtDate(t.scheduled_at)) + "</td>" +
        "<td>" + tag(t.status || "—", statusKind(t.status)) + "</td></tr>").join("")
        : emptyRow(4, "Hàng đợi trống. Xếp video đủ điều kiện từ TOP 5.")) +
      "</tbody>";
    const info = el("queue-info");
    if (info) {
      info.textContent =
        "Đang hoạt động: " + (q.active_task || "—") +
        " · Hôm nay dùng theo lịch · Tối đa " + (q.max_per_day ?? "—") + " bài/ngày" +
        " · " + (q.max_per_hour ?? "—") + " bài/giờ" +
        " · kiểm tra mỗi " + (q.check_every_hours ?? "—") + " giờ" +
        " · auto_post: " + (q.auto_post ? "BẬT" : "TẮT (approval mode)");
    }
  } catch (e) { box.innerHTML = "<tbody>" + emptyRow(4, "Không đọc được hàng đợi.") + "</tbody>"; }
}

async function enqueueTop5(sourceUrl) {
  try {
    const r = await api("/queue/enqueue", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl }),
    });
    toast("Đã xếp hàng: " + r.task_id + " (" + r.status + ")", "ok");
    await loadQueue();
  } catch (e) { toast(e.message, "err"); }
}

async function confirmContent(sourceUrl) {
  try {
    const r = await api("/discovery/confirm-content", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl }),
    });
    toast(r.note || "Đã xác minh thủ công.", "ok");
    await loadDiscovery();
  } catch (e) { toast(e.message, "err"); }
}

async function dismissContent(sourceUrl) {
  try {
    const r = await api("/discovery/dismiss-content", {
      method: "POST",
      body: JSON.stringify({ source_url: sourceUrl }),
    });
    toast(r.note || "Đã loại bỏ.", "ok");
    await loadDiscovery();
  } catch (e) { toast(e.message, "err"); }
}

/* The AI content analysis of every candidate. Only the candidates whose
   real content was read and judged as AI Music take part in the ranking.
   The list comes from the project scoped run, so it never shows a video of
   another project. */
function renderAnalysis() {
  const analyses = p1RunBelongsToCurrentScope() ? (p1runstate.videos || []) : [];
  const ranked = analyses.filter((a) => String(a.status || "") === "VERIFIED");
  const insufficient = analyses.filter(
    (a) => String(a.status || "") !== "VERIFIED" && String(a.rights || "") !== "REJECTED"
  );
  const counter = el("disc-analysis-count");
  if (counter) {
    counter.textContent = analyses.length
      ? ranked.length + "/" + analyses.length + " video đạt yêu cầu"
      : "Chưa có phân tích";
  }
  const box = el("disc-analysis");
  if (!box) return;

  if (!analyses.length) {
    box.innerHTML = '<div class="empty">Chưa có phân tích AI. Bấm “Bắt đầu tìm kiếm” để chạy phân tích nội dung thật.</div>';
    renderPreviewList([]);
    return;
  }

  const cards = ranked.map((a) => {
    const best = Number(a.rank || 0) === 1;
    return "<div class='card' style='border-left:3px solid " + (best ? "var(--accent)" : "var(--line)") + "'>" +
      "<div class='row-between'>" +
        "<strong>" + (a.rank ? "#" + a.rank + " · " : "") + "@" + esc(a.creator || "—") +
        (best ? ' <span class="tag tag-accent">ĐỀ XUẤT TỐT NHẤT</span>' : "") + "</strong>" +
        '<span class="tag">' + num(a.score) + "đ</span>" +
      "</div>" +
      "<div class='muted'>" + esc(a.title || a.source_url || "") + "</div>" +
      "<div class='muted' style='margin-top:4px'>" +
        "Lượt xem " + num(a.views) + " · lượt thích " + num(a.likes) + " · điểm xu hướng " + num(a.trend) +
      "</div>" +
      "<div class='muted' style='margin-top:4px'>" +
        "Quyền: " + esc(friendlyRights(a.rights)) +
      "</div>" +
      (a.reason ? "<div class='muted' style='margin-top:4px'>" + esc(a.reason) + "</div>" : "") +
      "<div class='row-actions'>" +
        "<button class='btn btn-xs' data-preview-url='" + esc(a.source_url) + "'>Xem trước</button>" +
      "</div>" +
      "</div>";
  }).join("");

  const missing = insufficient.length
    ? '<div class="card"><strong>Chưa đủ dữ liệu (' + insufficient.length + ")</strong>" +
      '<div class="muted">Các video này không được xếp hạng vì nội dung thật chưa đủ bằng chứng. ' +
      "Chúng không phải kết quả và không được chọn.</div>" +
      insufficient.map((a) => "<div class='muted'>@" + esc(a.creator || "—") + " — " + esc(a.reason || "không đủ bằng chứng") + "</div>").join("") +
      "</div>"
    : "";

  box.innerHTML = cards + missing;

  // The preview dropdown lists every candidate of this project only. When
  // there is no video, the dropdown stays hidden and an empty state is shown.
  renderPreviewList(analyses);
}

/* The preview list only contains the videos of the open project and version.
   An empty dropdown is never shown. */
function renderPreviewList(videos) {
  const select = el("disc-preview-select");
  const row = el("disc-preview-row");
  const empty = el("disc-preview-empty");
  const list = videos || [];
  if (select) {
    const current = select.value;
    if (!list.length) {
      select.innerHTML = "";
      select.value = "";
    } else {
      select.innerHTML = '<option value="">— chọn video để xem trước —</option>' +
        list.map((a) => {
          const label = "#" + (a.rank || "-") + " · @" + (a.creator || "—") +
            " · " + num(a.score) + " điểm";
          return "<option value='" + esc(a.source_url) + "'>" + esc(label) + "</option>";
        }).join("");
      // A video of another project is never kept selected.
      const stillThere = list.some((a) => a.source_url === current);
      select.value = stillThere ? current : "";
    }
  }
  if (row) row.hidden = !list.length;
  if (empty) empty.hidden = list.length > 0;
}

function renderSelected() {
  const card = el("disc-selected-card");
  // The selected video belongs to the open project only.
  const selected = p1RunBelongsToCurrentScope() ? state.selected : null;
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
    "<dt>URL</dt><dd><a href='" + esc(selected.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>" +
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
      "<tr><td><span style='color:var(--burgundy-ink)'>" + esc((s.video.title || s.video.source_url).slice(0, 50)) +
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
    if (s.max_per_day && el("sched-max-day")) el("sched-max-day").value = s.max_per_day;
    if (s.max_per_hour && el("sched-max-hour")) el("sched-max-hour").value = s.max_per_hour;
    if (s.check_every_hours && el("sched-check-hours")) el("sched-check-hours").value = s.check_every_hours;
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
    const q = s.queue || {};
    const qbox = el("sched-queue");
    if (qbox) {
      const tasks = q.tasks || [];
      qbox.innerHTML =
        "<thead><tr><th>Task</th><th>Nguồn</th><th>Lịch</th><th>Trạng thái</th></tr></thead><tbody>" +
        (tasks.length ? tasks.map((t) =>
          "<tr><td>" + esc(t.task_id) + "</td>" +
          "<td class='muted'>" + esc((t.source_url || "").slice(0, 60)) + "</td>" +
          "<td class='muted'>" + esc(fmtDate(t.scheduled_at)) + "</td>" +
          "<td>" + tag(t.status || "—", statusKind(t.status)) + "</td></tr>").join("")
          : emptyRow(4, "Hàng đợi trống. Xếp video đủ điều kiện từ TOP 5.")) +
        "</tbody>";
    }
    const qinfo = el("sched-queue-info");
    if (qinfo) {
      qinfo.textContent =
        "QUEUED: " + (q.queued ?? "—") +
        " · đang hoạt động: " + (q.active || "—") + (q.active_status ? " (" + q.active_status + ")" : "") +
        " · tối đa " + (s.max_per_day ?? "—") + " bài/ngày · " + (s.max_per_hour ?? "—") +
        " bài/giờ · kiểm tra mỗi " + (s.check_every_hours ?? "—") + " giờ" +
        (q.last_queue_run && q.last_queue_run.at ? " · lần xếp gần nhất: " + q.last_queue_run.at : "");
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
      state.top5 = detail.top5 || [];
      state.needsReview = detail.needs_review || [];
      state.verification = detail.verification || null;
      state.topicQueries = detail.topic_queries || [];
      state.queryStats = detail.query_stats || {};
      state.queryTotal = detail.query_total_returned || 0;
      state.funnel = detail.funnel || null;
      state.appliedFilters = detail.applied_filters || detail.filters || null;
      state.langMarketNote = detail.language_market_note || "";
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
  add("URL nguồn", "<a href='" + esc(candidate.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>" +
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
  // A video of another project is never played. The preview only accepts a
  // video that belongs to the open project and version.
  if (p1state.projectId) {
    const allowed = p1RunBelongsToCurrentScope() &&
      (p1runstate.videos || []).some((v) => v.source_url === sourceUrl);
    if (!allowed) {
      resetPreview();
      return;
    }
  }
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
    min_duration: (el("disc-min-duration") || {}).value || "",
    must_include: el("disc-must").value,
    must_include_any: (el("disc-must-any") || {}).value || "",
    subtopics: (el("disc-subtopics") || {}).value || "",
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
    if (el("disc-min-duration")) el("disc-min-duration").value = profile.min_duration || "";
    el("disc-must").value = profile.must_include || "";
    if (el("disc-must-any")) el("disc-must-any").value = profile.must_include_any || "";
    if (el("disc-subtopics")) el("disc-subtopics").value = profile.subtopics || "";
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
          max_per_day: Number(el("sched-max-day").value) || 1,
          max_per_hour: Number(el("sched-max-hour").value) || 1,
          check_every_hours: Number(el("sched-check-hours").value) || 1,
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

/* ============ global automation control (compact header + dropdown) ========= */
/* The backend keeps two distinct facts and the control never mixes them up:
   - emergency_stop is a persisted safety flag that every worker honours.
   - the background scheduler can be started and stopped on its own.
   A visible state is only shown after the server confirmed it, and a failed
   request restores the state that was on screen before. */

const automationState = {
  overview: null,
  scheduler: null,
  busy: false,
  pending: false,
};

function automationFacts() {
  const overview = automationState.overview || {};
  const scheduler = automationState.scheduler || {};
  const emergency = !!overview.emergency_stop;
  // The scheduler has two separate facts: it is configured (enabled) and the
  // worker is really alive (running). Only a running worker runs a task.
  const scheduleRunning = !!scheduler.running;
  return {
    emergency: emergency,
    scheduleEnabled: scheduleRunning,
    scheduleConfigured: !!scheduler.enabled,
    overview: overview,
    scheduler: scheduler,
  };
}

/* The label describes the safety state first, because that is the state that
   actually blocks the workers. */
function automationLabel(facts) {
  if (facts.emergency) return t("auto.emergency");
  if (!facts.scheduleEnabled) return t("auto.stopped");
  return t("auto.running");
}

function automationDotClass(facts) {
  if (automationState.busy) return "status-dot is-busy";
  if (facts.emergency) return "status-dot is-emergency";
  if (!facts.scheduleEnabled) return "status-dot is-stopped";
  return "status-dot is-running";
}

function renderAutomationControl() {
  const facts = automationFacts();
  const label = el("automation-label");
  const dot = el("automation-dot");
  if (label) label.textContent = automationState.busy ? t("common.saving") : automationLabel(facts);
  if (dot) {
    dot.className = automationDotClass(facts);
    dot.title = automationLabel(facts);
  }

  const stateLabel = el("automation-state-label");
  const stateDetail = el("automation-state-detail");
  if (stateLabel) stateLabel.textContent = automationLabel(facts);
  if (stateDetail) {
    const bits = [];
    bits.push(facts.emergency ? t("auto.emergencyOn") : t("auto.emergencyOff"));
    bits.push(facts.scheduleEnabled ? t("auto.scheduleOn")
      : (facts.scheduleConfigured ? t("auto.scheduleConfigured") : t("auto.scheduleOff")));
    if (overviewAutoPublishOff(facts.overview)) bits.push(t("auto.autoPublishOff"));
    stateDetail.textContent = bits.join(" ");
  }

  // The menu never shows two contradictory actions for the same fact.
  const toggle = el("menu-automation-toggle");
  if (toggle) {
    toggle.textContent = facts.emergency ? t("auto.resume") : t("auto.pause");
    toggle.dataset.action = facts.emergency ? "resume" : "pause";
    toggle.disabled = automationState.busy;
  }
  const emergencyItem = el("menu-automation-emergency");
  if (emergencyItem) {
    emergencyItem.hidden = facts.emergency;
    emergencyItem.textContent = t("auto.emergency");
    emergencyItem.disabled = automationState.busy;
  }
  const scheduleItem = el("menu-automation-scheduler");
  if (scheduleItem) {
    scheduleItem.textContent = facts.scheduleEnabled ? t("auto.stopSchedule") : t("auto.startSchedule");
    scheduleItem.disabled = automationState.busy;
  }
  const refreshItem = el("menu-automation-refresh");
  if (refreshItem) {
    refreshItem.textContent = t("auto.refresh");
    refreshItem.disabled = automationState.busy;
  }
}

/* Auto Publish is only reported as off. The control never turns it on. */
function overviewAutoPublishOff(overview) {
  if (!overview) return true;
  return !overview.auto_post;
}

async function refreshAutomationState() {
  try {
    const data = await api("/overview");
    automationState.overview = data;
  } catch (_) { /* keep the last known state */ }
  try {
    const data = await api("/scheduler");
    automationState.scheduler = data;
  } catch (_) { /* the scheduler may be off */ }
  renderAutomationControl();
  if (typeof renderOverviewAutomation === "function") renderOverviewAutomation();
}

/* The emergency stop is the safety flag, so it is the only action that asks
   for a confirmation before it is sent. */
async function runAutomationAction(action) {
  if (automationState.busy) return;
  if (action === "pause" || action === "stop") {
    const message = action === "stop" ? t("auto.confirmStop") : t("auto.confirmPause");
    if (!confirm(message)) return;
  }
  automationState.busy = true;
  renderAutomationControl();
  try {
    if (action === "resume") {
      await api("/emergency-start", { method: "POST", body: JSON.stringify({}) });
      toast(t("auto.doneResume"), "ok");
    } else if (action === "pause") {
      await api("/emergency-stop", { method: "POST", body: JSON.stringify({}) });
      toast(t("auto.donePause"), "ok");
    } else if (action === "stop") {
      await api("/emergency-stop", { method: "POST", body: JSON.stringify({}) });
      toast(t("auto.doneStop"), "ok");
    } else if (action === "schedule-start") {
      await api("/scheduler/start", { method: "POST", body: JSON.stringify({}) });
      toast(t("auto.doneSchedule"), "ok");
    } else if (action === "schedule-stop") {
      await api("/scheduler/stop", { method: "POST", body: JSON.stringify({}) });
      toast(t("auto.doneSchedule"), "ok");
    }
  } catch (e) {
    // The visible state is restored from the server, so a failed request can
    // never leave a wrong state on screen.
    toast(t("auto.failed"), "err");
  } finally {
    automationState.busy = false;
    await refreshAutomationState();
  }
}

/* The refresh only reloads data. It never starts a discovery and it never
   publishes anything. */
async function refreshDataOnly() {
  const btn = el("menu-automation-refresh");
  if (btn) btn.disabled = true;
  try {
    await loadView(state.view);
    await loadNotifications();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function closeMenus(except) {
  ["automation-menu", "notif-menu"].forEach((id) => {
    const menu = el(id);
    if (!menu || menu === except) return;
    menu.hidden = true;
  });
  ["btn-automation", "btn-notifications"].forEach((id) => {
    const btn = el(id);
    if (btn) btn.setAttribute("aria-expanded", "false");
  });
}

function toggleMenu(menuId, buttonId) {
  const menu = el(menuId);
  if (!menu) return;
  const wasOpen = !menu.hidden;
  closeMenus(wasOpen ? null : menu);
  menu.hidden = wasOpen;
  const btn = el(buttonId);
  if (btn) btn.setAttribute("aria-expanded", wasOpen ? "false" : "true");
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
    const html = items.length
      ? items.map((n) => {
          const kind = String(n.kind || "");
          const message = String(n.message || "");
          // A video that the filter dropped on purpose is not an error, so it
          // is reported as information and never counted as a critical alert.
          const critical = !isRoutineNotification(kind, message);
          return '<div class="notif' + (n.read ? " read" : "") + (critical ? " is-critical" : "") + '">' +
          '<div class="notif-kind">' + esc(kind) + "</div>" +
          '<div class="notif-msg">' + esc(notificationMessage(message)) + "</div>" +
          '<div class="notif-at">' + esc(fmtDate(n.at)) + "</div></div>";
        }).join("")
      : '<div class="empty">' + esc(t("notif.empty")) + "</div>";
    const list = el("notif-list");
    if (list) list.innerHTML = html;
    const menuList = el("notif-menu-list");
    if (menuList) {
      menuList.innerHTML = items.length
        ? items.slice(0, 12).map((n) => {
            const kind = String(n.kind || "");
            const message = String(n.message || "");
            const critical = !isRoutineNotification(kind, message);
            return '<div class="notif' + (n.read ? " read" : "") + (critical ? " is-critical" : "") + '">' +
              '<div class="notif-kind">' + esc(kind) + "</div>" +
              '<div class="notif-msg">' + esc(notificationMessage(message)) + "</div>" +
              '<div class="notif-at">' + esc(fmtDate(n.at)) + "</div></div>";
          }).join("")
        : '<div class="empty">' + esc(t("notif.empty")) + "</div>";
    }
  } catch (e) { /* ignore */ }
}

/* A normal filter rejection or a successful selection is part of the normal
   operation, so it is shown as information instead of as a critical alert. */
function isRoutineNotification(kind, message) {
  const text = String(message || "").toUpperCase();
  if (text.indexOf("NO_QUALIFIED_VIDEO") !== -1) return true;
  if (text.indexOf("ĐÃ CHỌN") !== -1 || text.indexOf("CANDIDATE_FOUND") !== -1) return true;
  if (String(kind).toLowerCase() === "discovery" && text.indexOf("ERROR") === -1) return true;
  return false;
}

/* The raw message is mapped to a readable label when it is a known enum. */
function notificationMessage(message) {
  const raw = String(message || "").trim();
  const upper = raw.toUpperCase();
  if (upper === "NO_QUALIFIED_VIDEO") return t("status.NO_QUALIFIED_VIDEO");
  if (upper === "CANDIDATE_FOUND") return t("status.CANDIDATE_FOUND");
  return raw;
}

/* ------------------------------------------------------------- init */

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
  const advToggle = el("nav-advanced-toggle");
  if (advToggle && !advToggle.dataset.bound) {
    advToggle.dataset.bound = "1";
    const flip = () => {
      const side = document.querySelector(".sidebar");
      if (!side) return;
      side.classList.toggle("hide-advanced");
      const hidden = side.classList.contains("hide-advanced");
      advToggle.setAttribute("aria-expanded", hidden ? "false" : "true");
      advToggle.textContent = hidden ? "Nâng cao ▸" : "Nâng cao ▾";
    };
    advToggle.addEventListener("click", flip);
    advToggle.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); }
    });
  }

  if (el("btn-ov-all-issues")) el("btn-ov-all-issues").addEventListener("click", () => showView("history"));
  if (el("btn-ov-all-history")) el("btn-ov-all-history").addEventListener("click", () => showView("history"));
  document.querySelectorAll(".tab[data-tab]").forEach((t) => {
    t.addEventListener("click", () => {
      const panel = t.closest(".view") || document;
      panel.querySelectorAll(".tab[data-tab]").forEach((x) => x.classList.toggle("active", x === t));
      const scope = t.closest(".view") || document;
      scope.querySelectorAll(".tab-panel[data-panel]").forEach((p) => {
        p.classList.toggle("active", p.dataset.panel === t.dataset.tab);
      });
    });
  });
  if (el("btn-p2-goto")) el("btn-p2-goto").addEventListener("click", () => showView("videos"));
  // The search button of the project workspace creates a version of the open
  // project. Without an open project it keeps the legacy discovery flow.
  el("btn-discover").addEventListener("click", () => {
    if (p1state.projectId) { p1Search(); return; }
    runDiscovery(false);
  });
  el("btn-discover-again").addEventListener("click", () => {
    if (p1state.projectId) { p1Search(); return; }
    runDiscovery(false);
  });
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
  el("btn-edit").addEventListener("click", editVideo);

  /* ---- global automation control ---- */
  if (el("btn-automation")) {
    el("btn-automation").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMenu("automation-menu", "btn-automation");
    });
  }
  if (el("menu-automation-toggle")) {
    el("menu-automation-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      const action = e.currentTarget.dataset.action;
      closeMenus(null);
      runAutomationAction(action);
    });
  }
  if (el("menu-automation-emergency")) {
    el("menu-automation-emergency").addEventListener("click", (e) => {
      e.stopPropagation();
      closeMenus(null);
      runAutomationAction("stop");
    });
  }
  if (el("menu-automation-scheduler")) {
    el("menu-automation-scheduler").addEventListener("click", (e) => {
      e.stopPropagation();
      const facts = automationFacts();
      closeMenus(null);
      runAutomationAction(facts.scheduleEnabled ? "schedule-stop" : "schedule-start");
    });
  }
  if (el("menu-automation-refresh")) {
    el("menu-automation-refresh").addEventListener("click", (e) => {
      e.stopPropagation();
      closeMenus(null);
      refreshDataOnly();
    });
  }

  /* ---- notification popover ---- */
  if (el("btn-notifications")) {
    el("btn-notifications").addEventListener("click", (e) => {
      e.stopPropagation();
      const opening = el("notif-menu").hidden;
      toggleMenu("notif-menu", "btn-notifications");
      if (opening) loadNotifications();
    });
  }
  if (el("btn-notif-menu-close")) {
    el("btn-notif-menu-close").addEventListener("click", (e) => {
      e.stopPropagation();
      closeMenus(null);
    });
  }
  if (el("btn-notif-open-all")) {
    el("btn-notif-open-all").addEventListener("click", (e) => {
      e.stopPropagation();
      closeMenus(null);
      showView("history");
    });
  }
  if (el("btn-top-settings")) {
    el("btn-top-settings").addEventListener("click", () => showView("settings"));
  }

  /* ---- appearance and locale ---- */
  if (el("set-theme")) {
    el("set-theme").addEventListener("change", (e) => setTheme(e.target.value));
  }
  if (el("set-locale")) {
    el("set-locale").addEventListener("change", (e) => setLocale(e.target.value));
  }

  // A click outside the menus closes them, and the escape key does the same.
  document.addEventListener("click", () => closeMenus(null));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenus(null);
  });

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
  const top5box = el("disc-top5");
  if (top5box) {
    top5box.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-enqueue]");
      if (btn) { enqueueTop5(btn.dataset.enqueue); return; }
      const confirm = e.target.closest("[data-confirm-content]");
      if (confirm) { confirmContent(confirm.dataset.confirmContent); return; }
      const dismiss = e.target.closest("[data-dismiss-content]");
      if (dismiss) dismissContent(dismiss.dataset.dismissContent);
    });
  }
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
  // The appearance and the locale are restored before the first render, so
  // the page never flashes the wrong theme or the wrong language.
  UI.theme = readStored(THEME_KEY, ["light", "dark", "system"], "light");
  applyTheme();
  applyLocale();

  bindEvents();
  bindP1();
  const hash = location.hash.replace("#", "");
  showView(TITLES[hash] ? hash : "overview");
  await loadOverview();
  await refreshAutomationState();
  loadNotifications();
  setInterval(loadNotifications, 20000);
  setInterval(refreshAutomationState, 30000);
}

/* ------------------------------------------------ P1 workspace (offline replay) */

const p1state = { projects: [], runs: [], projectId: "", runId: "" };

async function bindP1() {
  try {
    el("btn-p1-search").addEventListener("click", p1Search);
    el("btn-p1-open").addEventListener("click", p1Open);
    // The empty state offers the same search. It never starts on its own.
    if (el("btn-p1-search-empty")) el("btn-p1-search-empty").addEventListener("click", p1Search);
    // The filter area opens and closes. It is only a display control, it
    // never starts a search.
    if (el("btn-toggle-filters")) el("btn-toggle-filters").addEventListener("click", toggleProjectFilters);
    // The topic that is shown is the one that would really be sent.
    if (el("disc-topic")) el("disc-topic").addEventListener("input", renderProjectTopic);
    if (el("p1-project-topic")) el("p1-project-topic").addEventListener("input", renderProjectTopic);
    el("p1-run").addEventListener("change", async (e) => {
      p1state.runId = e.target.value;
      // The result of the previous version is dropped before the new one is
      // loaded, so the results of two versions are never mixed.
      resetP1RunState();
      renderDiscovery();
      renderProjectEmptyState();
      renderP1Header();
      if (p1state.runId) await loadProjectRunResult();
    });
    if (el("p1-runs-table")) el("p1-runs-table").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-run-open]");
      if (!btn) return;
      p1state.runId = btn.dataset.runOpen;
      if (el("p1-run")) el("p1-run").value = p1state.runId;
      p1Open();
    });
    if (el("btn-p2-detail")) el("btn-p2-detail").addEventListener("click", p2Detail);
    if (el("btn-p2-analyze")) el("btn-p2-analyze").addEventListener("click", p2Analyze);
    if (el("btn-p2-download")) el("btn-p2-download").addEventListener("click", p2Download);
    if (el("p2-auto") && !el("p2-auto").dataset.bound) {
      el("p2-auto").dataset.bound = "1";
      el("p2-auto").addEventListener("change", (e) => p2AutoToggle(e.target.value));
    }
    if (el("btn-p3-create")) el("btn-p3-create").addEventListener("click", p3Create);
    if (el("btn-p3-build")) el("btn-p3-build").addEventListener("click", p3Build);
    if (el("btn-p3-save")) el("btn-p3-save").addEventListener("click", p3Save);
    if (el("btn-p3-approve")) el("btn-p3-approve").addEventListener("click", p3Approve);
    if (el("btn-p3-schedule")) el("btn-p3-schedule").addEventListener("click", p3Schedule);
    if (el("btn-p3-run")) el("btn-p3-run").addEventListener("click", p3Run);
  } catch (e) {
    // A missing control is a real integration error, so it is reported
    // instead of being swallowed by one broad catch.
    console.error("bindP1 failed:", e);
    toast("Một số nút của workspace chưa gắn được. Xem console để biết chi tiết.", "err");
  }

  // P4-A.3 project workspace controls.
  try {
    if (el("btn-project-create")) el("btn-project-create").addEventListener("click", openProjectCreateModal);
    if (el("btn-project-back")) el("btn-project-back").addEventListener("click", closeProject);
    if (el("btn-project-modal-close")) el("btn-project-modal-close").addEventListener("click", closeProjectCreateModal);
    if (el("btn-project-cancel")) el("btn-project-cancel").addEventListener("click", closeProjectCreateModal);
    if (el("project-create-form")) el("project-create-form").addEventListener("submit", submitProjectCreate);
    if (el("project-search")) el("project-search").addEventListener("input", (e) => {
      projectstate.query = e.target.value;
      renderProjectList();
    });
    if (el("project-filter")) el("project-filter").addEventListener("change", (e) => {
      projectstate.filter = e.target.value;
      renderProjectList();
    });
    if (el("project-sort")) el("project-sort").addEventListener("change", (e) => {
      projectstate.sort = e.target.value;
      renderProjectList();
    });
    if (el("project-modal")) el("project-modal").addEventListener("click", (e) => {
      if (e.target === el("project-modal")) closeProjectCreateModal();
    });
    // The list is redrawn whenever it refreshes, so the click is handled
    // once on the container instead of once per row.
    if (el("project-list") && !el("project-list").dataset.bound) {
      el("project-list").dataset.bound = "1";
      el("project-list").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-act='open-project']");
        if (!btn) return;
        const row = btn.closest("[data-project-id]");
        if (!row) return;
        openProject(row.dataset.projectId);
      });
    }
  } catch (e) {
    console.error("project workspace binding failed:", e);
  }

  await loadP1Projects();
  await loadProjectSummary();
  await loadP3Settings();
}

async function loadP1Projects() {
  try {
    const data = await api("/p1/projects");
    p1state.projects = data.projects || [];
    // The project list is loaded for its own sake, so the workspace knows
    // the name and topic of every project. A selected project is only
    // cleared when it really is gone from the backend, and never while a
    // project detail is still loading.
    const known = (p1state.projects || []).some((p) => p.id === p1state.projectId);
    if (p1state.projectId && !known && !projectstate.loading) {
      p1state.projectId = "";
      p1state.runId = "";
    }
    await loadP1Runs();
  } catch (_) { /* offline ok */ }
}

/* ---------------- P4-A.3 project workspace ---------------- */

const projectstate = { summary: [], detail: null, query: "", filter: "all", sort: "updated", loading: "" };

/* The saved result of the project that is open right now. It is never shared
   with another project, and it is replaced completely when the project or the
   version changes, so a result of an older project can never appear here. */
const p1runstate = {
  projectId: "",
  runId: "",
  status: "",
  statusReason: "",
  queries: [],
  filters: null,
  funnel: null,
  top5: [],
  videos: [],
  plan: null,
  queryOutcomes: [],
  candidates: [],
  filterDecisions: [],
  loaded: false,
};

/* Everything that belongs to a result is cleared in one place. The global
   discovery state (state.result and friends) belongs to the legacy discovery
   workspace and is never used to paint a project result. */
function resetP1RunState() {
  p1runstate.projectId = "";
  p1runstate.runId = "";
  p1runstate.status = "";
  p1runstate.statusReason = "";
  p1runstate.queries = [];
  p1runstate.filters = null;
  p1runstate.funnel = null;
  p1runstate.top5 = [];
  p1runstate.videos = [];
  p1runstate.plan = null;
  p1runstate.queryOutcomes = [];
  p1runstate.candidates = [];
  p1runstate.filterDecisions = [];
  p1runstate.loaded = false;
  // A video that was playing belongs to the project that is left, so the
  // player is stopped and the preview is cleared with it.
  resetPreview();
}

/* The preview is cleared completely. No video of a previous project keeps
   playing and no old frame stays visible. */
function resetPreview() {
  const player = el("disc-preview-player");
  if (player) {
    try { player.pause(); } catch (_) { /* ignore */ }
    player.removeAttribute("src");
    player.hidden = true;
  }
  const still = el("disc-preview-still");
  if (still) {
    still.removeAttribute("src");
    still.hidden = true;
  }
  const select = el("disc-preview-select");
  if (select) {
    select.innerHTML = "";
    select.value = "";
  }
  const row = el("disc-preview-row");
  if (row) row.hidden = true;
  const empty = el("disc-preview-empty");
  if (empty) {
    empty.hidden = false;
    empty.textContent = t("p1.preview.empty");
  }
  const label = el("disc-preview-state");
  if (label) label.textContent = "—";
}

/* The results of the open project are only shown when the loaded data really
   belongs to that project and to the version that is selected. */
function p1RunBelongsToCurrentScope() {
  if (!p1state.projectId || !p1runstate.projectId) return false;
  if (String(p1runstate.projectId) !== String(p1state.projectId)) return false;
  if (!p1state.runId) return false;
  return String(p1runstate.runId) === String(p1state.runId);
}

/* The filter area opens and closes. It is a display control only, so it
   never starts a search and never changes the saved topic. */
function toggleProjectFilters() {
  const panel = el("project-filters");
  const button = el("btn-toggle-filters");
  if (!panel) return;
  const open = panel.hidden;
  panel.hidden = !open;
  if (button) {
    button.setAttribute("aria-expanded", open ? "true" : "false");
    const caret = button.querySelector(".caret");
    if (caret) caret.textContent = open ? "▴" : "▾";
  }
}

/* The topic that is really used for the next search. It is the explicit
   filter topic when there is one, otherwise the topic of the project. */
function renderProjectTopic() {
  const project = (p1state.projects || []).find((p) => p.id === p1state.projectId) || {};
  const configured = (el("disc-topic") && el("disc-topic").value) || "";
  const saved = (el("p1-project-topic") && el("p1-project-topic").value) ||
    String(project.topic || "");
  const topic = (configured.trim() || String(saved).trim());
  const box = el("p1-topic-display");
  if (box) box.textContent = topic || "—";
  // The empty state shows the topic of the project as well.
  const label = el("project-empty-topic");
  if (label) label.textContent = topic ? "Chủ đề: " + topic : "";
}

function projectFiltered() {
  const q = (projectstate.query || "").trim().toLowerCase();
  const filter = projectstate.filter || "all";
  let rows = (projectstate.summary || []).slice();
  if (q) {
    rows = rows.filter((p) =>
      String(p.name || "").toLowerCase().includes(q) ||
      String(p.topic || "").toLowerCase().includes(q));
  }
  if (filter === "pending") rows = rows.filter((p) => Number(p.pending_approval || 0) > 0);
  else if (filter === "issues") rows = rows.filter((p) => Number(p.blockers || 0) > 0);
  else if (filter === "active") {
    rows = rows.filter((p) => Number(p.versions || 0) > 0 || Number(p.publications || 0) > 0);
  }
  const sort = projectstate.sort || "updated";
  rows.sort((a, b) => {
    if (sort === "name") return String(a.name || a.topic || "").localeCompare(String(b.name || b.topic || ""), "vi");
    if (sort === "created") return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    return String(b.latest_activity || "").localeCompare(String(a.latest_activity || ""));
  });
  return rows;
}

function renderProjectList() {
  const box = el("project-list");
  if (!box) return;
  const rows = projectFiltered();
  const counter = el("project-count");
  if (counter) counter.textContent = rows.length + "/" + (projectstate.summary || []).length + " dự án";
  if (!rows.length) {
    box.innerHTML = "<div class='empty'>" +
      ((projectstate.summary || []).length
        ? "Không có dự án nào khớp bộ lọc hiện tại."
        : "Chưa có dự án. Bấm “Tạo dự án” để bắt đầu.") + "</div>";
    return;
  }
  box.innerHTML = rows.map((p) => {
    const issues = Number(p.blockers || 0);
    const pending = Number(p.pending_approval || 0);
    const bits = [];
    bits.push("<span class='tag'>" + num(p.versions) + " phiên bản</span>");
    bits.push("<span class='tag'>" + num(p.publications) + " bài đăng</span>");
    bits.push("<span class='tag" + (Number(p.published_verified || 0) ? " tag-ok" : "") + "'>" +
      num(p.published_verified) + " đã đăng (xác minh)</span>");
    if (pending) bits.push("<span class='tag tag-warn'>" + num(pending) + " chờ duyệt</span>");
    if (issues) bits.push("<span class='tag tag-danger'>" + num(issues) + " vấn đề</span>");
    return "<div class='project-row' data-project-id='" + esc(p.id) + "'>" +
      "<div class='project-row-main'>" +
      "<div class='project-row-title'>" + esc(p.name || p.topic || "Dự án") + "</div>" +
      "<div class='project-row-topic'>Chủ đề: " + esc(p.topic || "—") + "</div>" +
      "<div class='project-row-meta'>Cập nhật gần nhất: " + esc(friendlySchedule(p.latest_activity)) + "</div>" +
      "<div class='project-row-tags'>" + bits.join("") + "</div>" +
      "</div>" +
      "<div class='project-row-side'>" +
      "<button class='btn btn-primary' data-act='open-project'>Mở dự án</button>" +
      "</div></div>";
  }).join("");
}

async function loadProjectSummary() {
  try {
    const data = await api("/p1/projects/summary");
    projectstate.summary = data.projects || [];
    renderProjectList();
  } catch (e) {
    const box = el("project-list");
    if (box) box.innerHTML = "<div class='empty'>Không tải được danh sách dự án: " + esc(e.message) + "</div>";
  }
}

// The Video Lab and Publishing views show which project they belong to.
// The notice has to follow the project selection immediately, not only when
// one of those views is opened, so the scope is never ambiguous.
function renderProjectContext() {
  const project = (p1state.projects || []).find((p) => p.id === p1state.projectId) || null;
  const run = (p1state.runs || []).find((r) => r.id === p1state.runId) || null;
  const runId = p1state.runId || "";
  const p2ctx = el("p2-lab-context");
  if (p2ctx) {
    p2ctx.textContent = project
      ? ("Dự án: " + (project.name || project.topic || "—") +
         (runId ? " · Phiên bản: " + ((run && run.version) || runId) : " · Chưa mở phiên bản"))
      : "Chọn dự án và phiên bản ở trang Dự án trước.";
  }
  const p3ctx = el("p3-project-context");
  if (p3ctx) {
    p3ctx.textContent = project
      ? ("Dự án: " + (project.name || project.topic || "—") + " · " + (project.topic ? "chủ đề " + project.topic : ""))
      : "Chưa chọn dự án — đang hiển thị tất cả dự án.";
  }
}

async function openProject(projectId) {
  if (!projectId) return;
  projectstate.lastError = "";
  // The selected project is set first so every loader that runs in
  // parallel already sees the right project.
  p1state.projectId = projectId;
  p1state.runId = "";
  p3state.id = "";
  // The loading flag protects the selection while the project is loading.
  projectstate.loading = projectId;
  // The project list is loaded so the name and topic are known before the
  // header is rendered.
  if (!(p1state.projects || []).some((p) => p.id === projectId)) {
    try {
      const list = await api("/p1/projects");
      p1state.projects = list.projects || [];
    } catch (_) { /* offline ok */ }
  }
  // Every result of the previous project is dropped before the new project
  // is shown, so nothing of another project can appear here.
  resetP1RunState();
  state.top5 = [];
  state.funnel = null;
  state.candidates = [];
  state.selected = null;
  state.topicQueries = [];
  state.queryStats = {};
  state.queryTotal = 0;
  state.appliedFilters = null;
  state.needsReview = [];
  state.analyses = [];
  renderTop5();
  renderDiscovery();
  const detail = el("project-detail");
  if (detail) detail.hidden = false;
  const listCard = el("project-list");
  if (listCard) listCard.closest(".card").hidden = true;
  const head = el("project-search");
  if (head) head.closest(".card").hidden = true;
  renderProjectContext();
  await loadProjectDetail(projectId);
}

function closeProject() {
  const detail = el("project-detail");
  if (detail) detail.hidden = true;
  const listCard = el("project-list");
  if (listCard) listCard.closest(".card").hidden = false;
  const head = el("project-search");
  if (head) head.closest(".card").hidden = false;
  p1state.projectId = "";
  p1state.runId = "";
  p3state.id = "";
  // The saved result belongs to the project that is closed, so it goes with it.
  resetP1RunState();
  state.top5 = [];
  state.funnel = null;
  state.candidates = [];
  state.selected = null;
  state.topicQueries = [];
  state.queryStats = {};
  state.queryTotal = 0;
  state.appliedFilters = null;
  state.needsReview = [];
  state.analyses = [];
  renderTop5();
  renderDiscovery();
  renderP1Header();
  renderProjectList();
  renderProjectContext();
}

async function loadProjectDetail(projectId) {
  if (!projectId) return;
  projectstate.loading = projectId;
  try {
    // The project list may still be loading when a project is opened from
    // the list, so the names are loaded here as well.
    if (!(p1state.projects || []).some((p) => p.id === projectId)) {
      try {
        const list = await api("/p1/projects");
        p1state.projects = list.projects || [];
      } catch (_) { /* offline ok */ }
    }
    const data = await api("/p1/project?project_id=" + encodeURIComponent(projectId));
    projectstate.detail = data;
    // The backend returns the project itself, so the header never depends
    // on a second request.
    if (data.project && data.project.id === projectId) {
      const known = (p1state.projects || []).some((p) => p.id === projectId);
      if (!known) p1state.projects = (p1state.projects || []).concat([data.project]);
    }
    const project = data.project || (p1state.projects || []).find((p) => p.id === projectId) || {};
    const summary = (projectstate.summary || []).find((p) => p.id === projectId) || {};
    const name = project.name || summary.name || project.topic || summary.topic || "Dự án";
    const topic = project.topic || summary.topic || "";
    if (el("p1-project-name")) el("p1-project-name").textContent = name;
    if (el("p1-project-meta")) {
      el("p1-project-meta").textContent = "Chủ đề: " + (topic || "—") +
        " · " + num(summary.versions) + " phiên bản · " + num(summary.publications) + " bài đăng";
    }
    if (el("p1-project-topic")) el("p1-project-topic").value = topic;
    if (el("disc-topic")) el("disc-topic").value = topic;
    renderProjectTopic();
    renderProjectSummary(summary, data);
    renderProjectActivity(data);
    renderProjectPublications(data);
    renderP1Header();
    await loadP1Runs();
    renderProjectContext();
    // The saved result of this exact project is loaded. The backend refuses a
    // run that belongs to another project, so a result can never leak in.
    await loadProjectRunResult();
  } catch (e) {
    console.error("loadProjectDetail failed:", e);
    const box = el("project-summary");
    if (box) {
      box.innerHTML = "<div class='empty'>Không tải được chi tiết dự án: " + esc(e.message || String(e)) + "</div>";
    }
    toast(e.message || "Không tải được chi tiết dự án.", "err");
  }
  finally { projectstate.loading = ""; }
}

function renderProjectSummary(summary, detail) {
  const box = el("project-summary");
  if (!box) return;
  const runs = (detail && detail.runs) || [];
  const videos = (detail && detail.videos) || [];
  const pubs = (detail && detail.publications) || [];
  const verified = pubs.filter((p) => String(p.status || "") === "PUBLISHED" && String(p.posted_url || ""));
  const pending = pubs.filter((p) => ["DRAFT", "CAPTION_READY"].includes(String(p.status || "")));
  const blockers = pubs.filter((p) => ["RIGHTS_REQUIRED", "FAILED"].includes(String(p.status || "")));
  const items = [
    ["Video tìm thấy", videos.length, ""],
    ["Phiên bản", runs.length, ""],
    ["Bài đăng", pubs.length, ""],
    ["Đã đăng (xác minh)", verified.length, verified.length ? "ok" : ""],
    ["Chờ duyệt", pending.length, pending.length ? "warn" : ""],
    ["Vấn đề", blockers.length, blockers.length ? "danger" : ""],
  ];
  box.innerHTML = items.map(([label, value, kind]) =>
    '<div class="stat ' + (kind || "") + '">' +
    '<div class="stat-label">' + esc(label) + "</div>" +
    '<div class="stat-value">' + num(value) + "</div></div>").join("");
}

function renderProjectActivity(detail) {
  const box = el("project-activity");
  if (!box) return;
  const runs = ((detail && detail.runs) || []).slice().sort(
    (a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))
  ).slice(0, 5);
  const pubs = ((detail && detail.publications) || []).slice().sort(
    (a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))
  ).slice(0, 5);
  const events = [];
  runs.forEach((r) => events.push({
    at: String(r.created_at || ""),
    text: "Đã lưu phiên bản " + (r.version || r.id),
    kind: "",
  }));
  pubs.forEach((p) => events.push({
    at: String(p.updated_at || p.created_at || ""),
    text: "Bài đăng " + (p.id || "") + " — " + friendlyPubStatus(p.status),
    kind: statusKind(p.status),
  }));
  events.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  if (!events.length) {
    box.innerHTML = "<div class='empty'>Chưa có hoạt động. Mở một phiên bản đã lưu hoặc chạy tìm kiếm mới.</div>";
    return;
  }
  box.innerHTML = events.slice(0, 5).map((e) =>
    '<div class="notif"><div class="notif-kind">' + esc(friendlySchedule(e.at)) + "</div>" +
    '<div class="notif-msg">' + esc(e.text) + "</div></div>").join("");
}

function renderProjectPublications(detail) {
  const box = el("project-pubs");
  if (!box) return;
  const pubs = (detail && detail.publications) || [];
  const counter = el("project-pub-count");
  if (counter) counter.textContent = String(pubs.length);
  if (!pubs.length) {
    box.innerHTML = "<div class='empty'>Dự án này chưa có bài đăng nào.</div>";
    return;
  }
  box.innerHTML = pubs.map((p) =>
    '<div class="notif" data-pub-id="' + esc(p.id) + '">' +
    '<div class="notif-kind">' + esc(friendlyPubStatus(p.status)) + "</div>" +
    '<div class="notif-msg">Tài khoản: @' + esc(p.account || "—") +
    " · Lịch: " + esc(friendlySchedule(p.scheduled_at)) +
    (p.posted_url ? " · <a href='" + esc(p.posted_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>xem bài đăng</a>" : "") +
    "</div></div>").join("");
}

function openProjectCreateModal() {
  const modal = el("project-modal");
  if (!modal) return;
  modal.hidden = false;
  if (el("project-name")) el("project-name").value = "";
  if (el("project-topic")) el("project-topic").value = "";
  clearProjectFormErrors();
  const first = el("project-name");
  if (first) first.focus();
}

function closeProjectCreateModal() {
  const modal = el("project-modal");
  if (modal) modal.hidden = true;
}

function clearProjectFormErrors() {
  [["project-name-error", "project-name"], ["project-topic-error", "project-topic"]].forEach(([errId, inputId]) => {
    const err = el(errId);
    if (err) { err.hidden = true; err.textContent = ""; }
    const input = el(inputId);
    if (input) input.removeAttribute("aria-invalid");
  });
}

async function submitProjectCreate(e) {
  if (e) e.preventDefault();
  clearProjectFormErrors();
  const name = ((el("project-name") && el("project-name").value) || "").trim();
  const topic = ((el("project-topic") && el("project-topic").value) || "").trim();
  let invalid = false;
  if (!name) {
    const err = el("project-name-error");
    if (err) { err.textContent = "Nhập tên dự án."; err.hidden = false; }
    if (el("project-name")) el("project-name").setAttribute("aria-invalid", "true");
    invalid = true;
  }
  if (!topic) {
    const err = el("project-topic-error");
    if (err) { err.textContent = "Nhập chủ đề tìm kiếm."; err.hidden = false; }
    if (el("project-topic")) el("project-topic").setAttribute("aria-invalid", "true");
    invalid = true;
  }
  if (invalid) return;
  const submit = el("btn-project-submit");
  if (submit) { submit.disabled = true; submit.textContent = "Đang tạo…"; }
  try {
    const res = await api("/p1/projects", { method: "POST", body: JSON.stringify({ name, topic }) });
    const created = (res && res.project) || {};
    closeProjectCreateModal();
    await loadP1Projects();
    await loadProjectSummary();
    toast("Đã tạo dự án " + (created.name || name) + ".", "ok");
    if (created.id) openProject(created.id);
  } catch (err) {
    toast(err.message || "Không tạo được dự án.", "err");
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = "Tạo dự án"; }
  }
}

async function loadP1Runs() {
  const sel = el("p1-run");
  if (!sel) return;
  if (!p1state.projectId) { sel.innerHTML = "<option value=''>—</option>"; resetP1RunState(); renderTop5(); return; }
  const wanted = p1state.runId;
  const forProject = p1state.projectId;
  try {
    const data = await api("/p1/runs?project_id=" + encodeURIComponent(forProject));
    // The project may have changed while the request was in flight.
    if (forProject !== p1state.projectId) return;
    p1state.runs = data.runs || [];
    sel.innerHTML = p1state.runs.map((r) =>
      "<option value='" + esc(r.id) + "'>" + esc(r.version) + " · " + esc(r.created_at || "") + "</option>").join("")
      || "<option value=''>— chưa có phiên bản —</option>";
    // Keep the selected version when it still exists in this project. When a
    // project is opened, the newest version is the one that is shown.
    const stillThere = p1state.runs.some((r) => r.id === wanted);
    if (stillThere) {
      p1state.runId = wanted;
      sel.value = wanted;
    } else if (p1state.runs.length) {
      const newest = p1state.runs[p1state.runs.length - 1];
      p1state.runId = newest.id;
      sel.value = newest.id;
    } else {
      // The project has no version at all, so there is no result either.
      p1state.runId = "";
      resetP1RunState();
    }
    renderP1Header();
    renderDiscovery();
  } catch (_) { /* offline ok */ }
}

/* The saved result of the selected version of the open project. The backend
   checks that the run belongs to the project, so a result of another project
   is rejected instead of being displayed. */
async function loadProjectRunResult() {
  const forProject = p1state.projectId;
  const forRun = p1state.runId;
  if (!forProject || !forRun) {
    resetP1RunState();
    renderDiscovery();
    renderProjectEmptyState();
    return;
  }
  try {
    const res = await api("/p1/run?project_id=" + encodeURIComponent(forProject) +
      "&run_id=" + encodeURIComponent(forRun));
    // The project or the version may have changed while the request was in
    // flight, so the answer is dropped when it is no longer the current scope.
    if (forProject !== p1state.projectId || forRun !== p1state.runId) return;
    const run = res.run || {};
    if (String(run.project_id || "") !== String(forProject)) {
      resetP1RunState();
      renderDiscovery();
      renderProjectEmptyState();
      return;
    }
    p1runstate.projectId = forProject;
    p1runstate.runId = forRun;
    p1runstate.queries = parseJsonField(run.queries_json, []);
    p1runstate.filters = parseJsonField(run.filters_json, null);
    p1runstate.funnel = parseJsonField(run.funnel_json, null);
    p1runstate.top5 = parseJsonField(run.top5_json, []);
    p1runstate.videos = run.videos || [];
    // The logical status is resolved from the data the run really holds, so
    // a historical empty run is never shown as a false success.
    p1runstate.status = resolveP1RunStatus(run, p1runstate.funnel, p1runstate.videos);
    // The full research dataset of the run. A historical run without these
    // fields still loads, it simply shows no plan and no diagnostics.
    const snapshot = parseJsonField(run.snapshot_json, {}) || {};
    p1runstate.plan = snapshot.plan || null;
    p1runstate.statusReason = String(snapshot.status_reason || "");
    p1runstate.queryOutcomes = snapshot.query_outcomes || [];
    p1runstate.candidates = snapshot.candidates || [];
    p1runstate.filterDecisions = snapshot.filter_decisions || [];
    p1runstate.loaded = true;
    // The whole result view is painted again, so the counter, the table and
    // the preview follow the run that was just loaded.
    renderDiscovery();
    renderProjectEmptyState();
    renderP1SearchPlan();
    renderP1Funnel();
    renderP1Diagnostics();
    setP1RunStatus(p1runstate.status, p1runstate.statusReason);
  } catch (e) {
    // A missing or foreign run leaves the project without a result.
    if (forProject !== p1state.projectId || forRun !== p1state.runId) return;
    resetP1RunState();
    renderDiscovery();
    renderProjectEmptyState();
    renderP1SearchPlan();
    renderP1Funnel();
    renderP1Diagnostics();
  }
}

/* The search plan of the open run: the directions that were searched and
   why each of them belongs to the topic. */
function renderP1SearchPlan() {
  const box = el("p1-search-plan");
  const counter = el("p1-plan-count");
  if (!box) return;
  const plan = p1runstate.plan;
  const specs = (plan && plan.queries) || [];
  if (!specs.length) {
    box.innerHTML = '<div class="empty">Chưa có kế hoạch. Bấm “Bắt đầu tìm kiếm” để tạo kế hoạch truy vấn.</div>';
    if (counter) counter.textContent = "Chưa có kế hoạch";
    return;
  }
  if (counter) {
    counter.textContent = specs.length + " truy vấn" +
      (plan.confidence ? " · độ tin cậy " + plan.confidence : "");
  }
  const dims = (plan.dimensions || []).map((d) => '<span class="filter-chip">' + esc(d) + "</span>").join(" ");
  const notes = (plan.notes || []).map((n) => '<div class="muted small">' + esc(n) + "</div>").join("");
  box.innerHTML =
    (dims ? '<div class="row wrap">' + dims + "</div>" : "") +
    '<div class="table-wrap"><table class="table"><thead><tr>' +
    "<th>#</th><th>Truy vấn</th><th>Nhóm</th><th>Vì sao thuộc chủ đề</th>" +
    "</tr></thead><tbody>" +
    specs.map((q, i) =>
      "<tr><td>" + (i + 1) + "</td>" +
      "<td><strong>" + esc(q.query || "") + "</strong></td>" +
      "<td><span class='tag'>" + esc(q.group || "") + "</span></td>" +
      "<td class='muted'>" + esc(q.reason || "") + "</td></tr>"
    ).join("") +
    "</tbody></table></div>" +
    notes;
}

/* The compact funnel summary. Every counter is shown, including the ones
   that are zero, so an empty run shows where it became empty. */
const P1_FUNNEL_LABELS = [
  ["RAW_RETURNED", "Nguồn trả về"],
  ["PARSED", "Đã phân tích"],
  ["DEDUPLICATED", "Sau loại trùng"],
  ["USER_FILTER_PASSED", "Qua bộ lọc"],
  ["RELEVANT", "Liên quan (verified)"],
  ["NEEDS_REVIEW", "Cần xem xét"],
  ["RANKED", "Đã xếp hạng"],
  ["TOP5", "TOP 5"],
];

function renderP1Funnel() {
  const box = el("p1-funnel");
  const statusEl = el("p1-funnel-status");
  if (!box) return;
  const funnel = p1runstate.funnel;
  if (!funnel) {
    box.innerHTML = '<div class="empty">Chưa có dữ liệu phễu.</div>';
    if (statusEl) statusEl.textContent = "—";
    return;
  }
  // The counter is read under its documented name first, then under the
  // legacy short name, so a historical run renders correctly too.
  const LEGACY_NAMES = {
    RAW_RETURNED: "raw",
    PARSED: "parsed",
    DEDUPLICATED: "dedup",
    USER_FILTER_PASSED: "filtered",
    RELEVANT: "verified",
    NEEDS_REVIEW: "needs_review",
    RANKED: "ranked",
    TOP5: "top5",
  };
  const value = (key) => {
    const raw = funnel[key];
    if (raw !== undefined && raw !== null) return raw;
    const legacy = LEGACY_NAMES[key];
    if (legacy && funnel[legacy] !== undefined && funnel[legacy] !== null) {
      return funnel[legacy];
    }
    return 0;
  };
  if (statusEl) {
    const label = (P1_RUN_LABELS[p1runstate.status] || ["—", ""])[0];
    statusEl.textContent = label;
    statusEl.title = p1runstate.statusReason || "";
  }
  box.innerHTML =
    '<div class="funnel-strip">' +
    P1_FUNNEL_LABELS.map(([key, label]) =>
      '<div class="funnel-step"><div class="funnel-value">' + esc(String(value(key))) +
      '</div><div class="funnel-label">' + esc(label) + "</div></div>"
    ).join("") +
    "</div>" +
    (p1runstate.statusReason ? '<div class="muted small">' + esc(p1runstate.statusReason) + "</div>" : "");
}

/* The expandable diagnostics: per-query status, counts and reasons. */
function renderP1Diagnostics() {
  const box = el("p1-diagnostics");
  if (!box) return;
  const outcomes = p1runstate.queryOutcomes || [];
  if (!outcomes.length) {
    box.innerHTML = '<div class="empty">Chưa có chẩn đoán.</div>';
    return;
  }
  const rows = outcomes.map((o, i) =>
    "<tr><td>" + (i + 1) + "</td>" +
    "<td>" + esc(o.query || "") + "</td>" +
    "<td><span class='tag'>" + esc(o.status || "") + "</span></td>" +
    "<td class='num'>" + esc(String(o.raw_count === undefined ? 0 : o.raw_count)) + "</td>" +
    "<td class='num'>" + esc(String(o.attempts === undefined ? 0 : o.attempts)) + "</td>" +
    "<td class='muted'>" + esc(o.started_at || "") + " → " + esc(o.ended_at || "") + "</td>" +
    "<td class='muted'>" + esc(o.note || "") + "</td></tr>"
  ).join("");
  const decisions = (p1runstate.filterDecisions || []).map((d) =>
    "<li>" + esc(d) + "</li>").join("");
  box.innerHTML =
    "<h4>Kết quả từng truy vấn</h4>" +
    '<div class="table-wrap"><table class="table"><thead><tr>' +
    "<th>#</th><th>Truy vấn</th><th>Trạng thái</th><th>Raw</th><th>Lần thử</th><th>Thời gian</th><th>Lý do</th>" +
    "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
    (decisions
      ? "<h4>Video bị bộ lọc loại (" + (p1runstate.filterDecisions || []).length + ")</h4><ul class='small'>" + decisions + "</ul>"
      : "");
}

function parseJsonField(raw, fallback) {
  if (raw === null || raw === undefined || raw === "") return fallback;
  try {
    const value = JSON.parse(raw);
    return value === null || value === undefined ? fallback : value;
  } catch (_) {
    return fallback;
  }
}

/* The empty state of a project that has no research result yet. It only
   shows the project name, the topic and the button that starts a search. */
function renderProjectEmptyState() {
  const box = el("project-empty");
  if (!box) return;
  const hasResult = p1RunBelongsToCurrentScope() && (p1runstate.videos || []).length > 0;
  const hasRuns = (p1state.runs || []).length > 0;
  box.hidden = hasResult;
  const topic = el("p1-project-topic");
  const topicText = topic && topic.value ? topic.value.trim() : "";
  const label = el("project-empty-topic");
  if (label) label.textContent = topicText ? t("p1.empty.topic") + topicText : "";
  const note = el("project-empty-note");
  if (note) {
    note.textContent = hasRuns ? t("p1.empty.noteRuns") : t("p1.empty.note");
  }
}

function renderP1Header() {
  // The project name comes from the loaded projects, and falls back to the
  // summary so the header is correct even before the list is loaded.
  let proj = (p1state.projects || []).find((p) => p.id === p1state.projectId) || null;
  if (!proj) {
    const sum = (projectstate.summary || []).find((p) => p.id === p1state.projectId) || null;
    if (sum) proj = { id: sum.id, name: sum.name, topic: sum.topic };
  }
  // The header is always rendered from the current project state.
  if (!p1state.projectId) {
    if (el("p1-project-name")) el("p1-project-name").textContent = "Dự án";
    if (el("p1-project-meta")) el("p1-project-meta").textContent = "Chưa chọn dự án.";
    return;
  }
  if (el("p1-project-name")) {
    el("p1-project-name").textContent = proj ? (proj.name || proj.topic || "Dự án") : "Dự án";
  }
  const run = (p1state.runs || []).find((r) => r.id === p1state.runId) || (p1state.runs || [])[0] || null;
  if (el("p1-project-meta")) {
    el("p1-project-meta").textContent = proj
      ? ("Chủ đề: " + (proj.topic || "—") + " · Phiên bản: " + (run ? (run.version || run.id) : "chưa có") + " · " + (p1state.runs || []).length + " phiên bản")
      : "Chưa chọn dự án.";
  }
  const box = el("p1-runs-table");
  if (box) {
    const rows = p1state.runs || [];
    box.innerHTML = "<thead><tr><th>Version</th><th>Thời gian</th><th></th></tr></thead><tbody>" +
      (rows.length ? rows.map((r) =>
        "<tr" + (r.id === p1state.runId ? " class='sel'" : "") + "><td>" + esc(r.version || r.id) + "</td>" +
        "<td class='muted'>" + esc(r.created_at || "—") + "</td>" +
        "<td><button class='btn btn-xs' data-run-open='" + esc(r.id) + "'>Mở</button></td></tr>").join("")
        : emptyRow(3, "Chưa có version. Bấm “Tìm kiếm” để lưu version mới.")) + "</tbody>";
  }
}

/* The filter payload of the project search.

   Every field is read from the DOM VALUE, never from the placeholder. An
   empty field is sent as 0 / "", which the backend reads as "no
   constraint". There is no default market, language, age or metric limit,
   and the strict preset is only sent when the user explicitly selects it. */
function p1Filters() {
  const g = (id) => {
    const node = el(id);
    return node ? String(node.value || "").trim() : "";
  };
  const num = (id) => {
    const raw = g(id);
    if (raw === "") return 0;
    const value = Number(raw);
    return Number.isFinite(value) ? value : 0;
  };
  const filters = {
    min_views: num("disc-min-views"),
    max_views: num("disc-max-views"),
    min_likes: num("disc-min-likes"),
    min_comments: num("disc-min-comments"),
    min_shares: num("disc-min-shares"),
    min_duration: num("disc-min-duration"),
    max_duration: num("disc-max-duration"),
    max_days: num("disc-days"),
    must_include: g("disc-must"),
    must_include_any: g("disc-must-any"),
    subtopics: g("disc-subtopics"),
    exclude: g("disc-exclude"),
    // Language and market cannot be verified from the source payload. They
    // are recorded as a note, never as a filter that pretends to work.
    language: "",
    market: "",
  };
  // The strict preset is an explicit, opt-in compatibility mode.
  if (g("disc-preset") === "strict") {
    filters.strict_preset = true;
  }
  return filters;
}

/* The list of constraints that are really active, so the user can see
   them before the search runs. */
function p1ActiveFilterLabels() {
  const labels = [];
  const g = (id) => {
    const node = el(id);
    return node ? String(node.value || "").trim() : "";
  };
  const num = (id) => {
    const raw = g(id);
    if (raw === "") return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  };
  const push = (label, value) => { if (value !== null && value !== "") labels.push(label + ": " + value); };
  push("Lượt xem tối thiểu", num("disc-min-views"));
  push("Lượt xem tối đa", num("disc-max-views"));
  push("Lượt thích tối thiểu", num("disc-min-likes"));
  push("Bình luận tối thiểu", num("disc-min-comments"));
  push("Chia sẻ tối thiểu", num("disc-min-shares"));
  push("Thời lượng tối thiểu", num("disc-min-duration"));
  push("Thời lượng tối đa", num("disc-max-duration"));
  push("Đăng trong N ngày", num("disc-days"));
  push("Bắt buộc (ALL)", g("disc-must"));
  push("Ít nhất một (ANY)", g("disc-must-any"));
  push("Chủ đề con ưu tiên", g("disc-subtopics"));
  push("Loại trừ", g("disc-exclude"));
  if (g("disc-preset") === "strict") labels.push("Preset nghiêm ngặt (5000 views · 30–60s · ≤30 ngày)");
  return labels;
}

function renderP1ActiveFilters() {
  const box = el("filter-active-summary");
  if (!box) return;
  const labels = p1ActiveFilterLabels();
  if (!labels.length) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = "<strong>Đang áp dụng:</strong> " +
    labels.map((x) => '<span class="filter-chip">' + esc(x) + "</span>").join(" ");
}

/* The logical run states of a search. They are never reduced to a single
   "success" when the run actually found nothing. A historical run with the
   old "COMPLETED" status is mapped onto the closest logical state, so an
   old run is never shown as a false success. */
const P1_RUN_LABELS = {
  COMPLETED_WITH_RESULTS: ["Hoàn tất — có kết quả", "tag-ok"],
  COMPLETED_EMPTY: ["Hoàn tất — không có kết quả", "tag-warn"],
  PARTIAL: ["Hoàn tất một phần", "tag-warn"],
  SOURCE_FAILED: ["Nguồn thất bại", "tag-warn"],
  SOURCE_BLOCKED: ["Nguồn bị chặn", "tag-warn"],
  CANCELLED: ["Đã dừng", "tag-warn"],
  RUNNING: ["Đang tìm kiếm", "tag-accent"],
  // The historical status of a run that was stored before the logical
  // statuses existed. It is resolved from the stored data, never assumed.
  COMPLETED: ["Hoàn tất (lịch sử cũ)", "tag-warn"],
};

/* Resolve the logical status of a stored run. The new statuses are used as
   they are. A legacy "COMPLETED" run is resolved from the data it really
   holds, so an old empty run is never shown as a success. */
function resolveP1RunStatus(run, funnel, videos) {
  const raw = String((run && run.status) || "").trim();
  if (raw && raw !== "COMPLETED") return raw;
  const count = Array.isArray(videos) ? videos.length : 0;
  if (count > 0) return "COMPLETED_WITH_RESULTS";
  const rawCount = Number((funnel || {}).raw ?? (funnel || {}).RAW_RETURNED ?? 0) || 0;
  if (rawCount > 0) {
    // The run collected videos but none of them qualified. That is an
    // empty result with a known reason, not a success.
    return "COMPLETED_EMPTY";
  }
  return "COMPLETED_EMPTY";
}

function setP1RunStatus(status, reason) {
  const tagEl = el("p1-search-state");
  if (!tagEl) return;
  const entry = P1_RUN_LABELS[status] || [t("p1.search.idle"), ""];
  tagEl.textContent = entry[0];
  tagEl.className = "tag " + entry[1];
  if (reason) tagEl.title = reason;
}

async function p1Search() {
  if (!p1state.projectId) { toast("Chọn dự án trước.", "err"); return; }
  // The search topic comes from the selected project, or from an explicit
  // edit in the project search configuration. It never falls back to the
  // new-project input of another workspace.
  const project = (p1state.projects || []).find((p) => p.id === p1state.projectId) || {};
  const configured = (el("disc-topic") && el("disc-topic").value) || "";
  const topic = (configured.trim() || String(project.topic || "")).trim();
  if (!topic) { toast("Chưa có chủ đề cho dự án này.", "err"); return; }
  // The search only runs when the user presses the button. It never starts
  // by itself when a project is opened.
  const button = el("btn-p1-search");
  if (button) button.disabled = true;
  setProjectSearchState("running");
  const forProject = p1state.projectId;
  // One idempotency key per click. A double click is blocked by the
  // disabled button, and the key makes a retry safe.
  const retryKey = "ui-" + forProject + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  try {
    toast("Đang lập kế hoạch và thu thập (LIVE TikTok)…", "");
    const res = await api("/p1/search", {
      method: "POST",
      body: JSON.stringify({
        project_id: forProject,
        topic,
        filters: p1Filters(),
        retry_key: retryKey,
      }),
    });
    // The project may have changed while the search was running.
    if (forProject !== p1state.projectId) return;
    const run = res.run || {};
    const status = res.status || run.status || "COMPLETED_WITH_RESULTS";
    const reason = res.status_reason || "";
    setP1RunStatus(status, reason);
    await loadP1Runs();
    await loadProjectRunResult();
    await loadP2Videos({ videos: p1runstate.videos || [] });
    if (status === "COMPLETED_WITH_RESULTS") {
      toast("Đã lưu version " + (run.version || "") + " — " +
        ((p1runstate.videos || []).length) + " video.", "ok");
    } else {
      // An empty, partial or blocked run is never reported as a success.
      toast((P1_RUN_LABELS[status] || [status, ""])[0] + (reason ? ": " + reason : ""), "err");
    }
  } catch (e) {
    setProjectSearchState("error");
    toast(e.message, "err");
  } finally {
    if (button) button.disabled = false;
  }
}

/* The search area shows what is really happening: idle, running, done or
   failed. It never shows a success that did not happen. */
function setProjectSearchState(phase) {
  const tagEl = el("p1-search-state");
  if (!tagEl) return;
  const map = {
    idle: [t("p1.search.idle"), ""],
    running: [t("p1.search.running"), "tag-accent"],
    done: [t("p1.search.done"), "tag-ok"],
    error: [t("p1.search.error"), "tag-warn"],
  };
  const entry = map[phase] || map.idle;
  tagEl.textContent = entry[0];
  tagEl.className = "tag " + entry[1];
}

async function p1Open() {
  if (!p1state.projectId || !p1state.runId) { toast("Chọn project và version.", "err"); return; }
  const forProject = p1state.projectId;
  const forRun = p1state.runId;
  try {
    const res = await api("/p1/run?project_id=" + encodeURIComponent(forProject) +
      "&run_id=" + encodeURIComponent(forRun));
    // The project or the version may have changed while it was loading.
    if (forProject !== p1state.projectId || forRun !== p1state.runId) return;
    const run = res.run || {};
    p1runstate.projectId = forProject;
    p1runstate.runId = forRun;
    p1runstate.queries = parseJsonField(run.queries_json, []);
    p1runstate.filters = parseJsonField(run.filters_json, null);
    p1runstate.funnel = parseJsonField(run.funnel_json, null);
    p1runstate.top5 = parseJsonField(run.top5_json, []);
    p1runstate.videos = run.videos || [];
    p1runstate.status = resolveP1RunStatus(run, p1runstate.funnel, p1runstate.videos);
    const snapshot = parseJsonField(run.snapshot_json, {}) || {};
    p1runstate.plan = snapshot.plan || null;
    p1runstate.statusReason = String(snapshot.status_reason || "");
    p1runstate.queryOutcomes = snapshot.query_outcomes || [];
    p1runstate.candidates = snapshot.candidates || [];
    p1runstate.filterDecisions = snapshot.filter_decisions || [];
    p1runstate.loaded = true;
    renderDiscovery();
    renderProjectEmptyState();
    renderP1SearchPlan();
    renderP1Funnel();
    renderP1Diagnostics();
    setP1RunStatus(p1runstate.status, p1runstate.statusReason);
    await loadP2Videos(run);
    toast("Đã mở " + (run.version || "") + " offline (không gọi TikTok).", "ok");
  } catch (e) { toast(e.message, "err"); }
}

/* ------------------------------------------------ P2 video lab */

async function loadP2Videos(run) {
  const sel = el("p2-video");
  if (!sel) return;
  renderProjectContext();
  const vids = (run && run.videos) || [];
  if (!vids.length) { sel.innerHTML = "<option value=''>—</option>"; return; }
  sel.innerHTML = vids.map((v) =>
    "<option value='" + esc(v.id) + "'>#" + (v.rank || "-") + " · @" + esc(v.creator || "") +
    " · " + (v.score || 0) + "đ · " + esc(friendlyRights(v.rights)) + "</option>").join("");
  try {
    const s = await api("/p2/settings");
    el("p2-auto").value = (s && s.auto_download_best) ? "on" : "off";
    const st = el("p2-lab-state");
    if (st) st.textContent = (s && s.auto_download_best) ? "Tự động tải: Bật" : "Tự động tải: Tắt";
  } catch (_) { /* ignore */ }
}

async function p2AutoToggle(changed) {
  // One real settings request. The control shows the progress, reflects the
  // confirmed server state, and rolls back when the request fails.
  const sel = el("p2-auto");
  if (!sel) return;
  const wanted = sel.value;
  const previous = changed === "on" ? "off" : "on";
  sel.disabled = true;
  try {
    const res = await api("/p2/settings", { method: "POST", body: JSON.stringify({ enabled: wanted === "on" }) });
    const confirmed = res && typeof res.auto_download_best !== "undefined" ? res.auto_download_best : wanted === "on";
    sel.value = confirmed ? "on" : "off";
    const st = el("p2-lab-state");
    if (st) st.textContent = sel.value === "on" ? "Tự động tải: Bật" : "Tự động tải: Tắt";
    toast(sel.value === "on" ? "Đã bật tự động tải video." : "Đã tắt tự động tải video.", "ok");
  } catch (e) {
    sel.value = previous;
    toast(e.message || "Không lưu được cài đặt tự động tải.", "err");
  } finally {
    sel.disabled = false;
  }
}

async function p2Detail() {
  const vid = el("p2-video").value || "";
  if (!p1state.projectId || !p1state.runId || !vid) { toast("Chọn project/run/video.", "err"); return; }
  try {
    const res = await api("/p2/video?project_id=" + encodeURIComponent(p1state.projectId) +
      "&run_id=" + encodeURIComponent(p1state.runId) + "&video_id=" + encodeURIComponent(vid));
    const v = res.video || {};
    el("p2-lab-state").textContent = "rank #" + (v.rank || "-");
    el("p2-lab-out").innerHTML = "<dl class='kv'>" +
      "<dt>URL</dt><dd><a href='" + esc(v.source_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>" + esc(v.source_url) + "</a></dd>" +
      "<dt>Creator</dt><dd>" + esc(v.creator || "—") + "</dd>" +
      "<dt>Metrics</dt><dd>" + num(v.views) + " views · " + num(v.likes) + " likes · " + (v.duration || 0) + "s</dd>" +
      "<dt>Trend score</dt><dd><strong>" + (v.score || 0) + "</strong></dd>" +
      "<dt>Reason</dt><dd>" + esc(v.reason || "—") + "</dd>" +
      "<dt>Rights</dt><dd>" + esc(v.rights_status || "—") + "</dd></dl>";
  } catch (e) { toast(e.message, "err"); }
}

async function p2Analyze() {
  const vid = el("p2-video").value || "";
  if (!p1state.projectId || !p1state.runId || !vid) { toast("Chọn project/run/video.", "err"); return; }
  try {
    toast("Đang đo MP4 thật…", "");
    const res = await api("/p2/video/analyze", { method: "POST",
      body: JSON.stringify({ project_id: p1state.projectId, run_id: p1state.runId, video_id: vid }) });
    const a = res.analysis || {};
    const sb = (a.storyboard || []).map((s) =>
      "<div class='muted'>@" + s.t + "s · " + s.bytes + " bytes · " + esc(s.image) + "</div>").join("");
    el("p2-lab-out").innerHTML = "<dl class='kv'>" +
      "<dt>Duration</dt><dd>" + (a.duration || 0).toFixed(2) + "s (đo thật)</dd>" +
      "<dt>FPS/Res</dt><dd>" + esc(String(a.fps || "—")) + " · " + (a.width || "?") + "x" + (a.height || "?") + " · " + esc(a.vcodec || "") + "</dd>" +
      "<dt>Audio</dt><dd>" + (a.audio && a.audio.has_audio ? ("có · " + esc(String(a.audio.codec || "")) + " · mean " + esc(String(a.audio.mean_volume_db)) + "dB · peak " + esc(String(a.audio.peak_volume_db)) + "dB") : "không có track") + (a.cache_hit ? " · CACHE" : "") + "</dd>" +
      "<dt>Scenes</dt><dd>" + ((a.scenes || []).join(", ") || "—") + " (" + (a.scenes || []).length + " điểm cắt đo thật)</dd>" +
      "<dt>SHA256</dt><dd>" + esc(String(a.sha256 || "").slice(0, 24)) + "… · " + esc(a.analyzer_version || "") + "</dd></dl>" +
      "<div><strong>Storyboard (" + (a.storyboard || []).length + " keyframes)</strong>" + sb + "</div>";
    toast(a.cache_hit ? "Đã lấy từ cache (không phân tích lại)." : "Đã đo xong MP4.", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function p2Download() {
  if (!p1state.projectId || !p1state.runId) { toast("Chọn dự án và phiên bản.", "err"); return; }
  try {
    // The auto-download toggle owns its own settings request. This button
    // only performs the download action, so flipping the switch never
    // downloads anything by accident.
    toast("Đang chọn video đủ quyền điểm cao nhất (chỉ 1)…", "");
    const res = await api("/p2/auto-download", { method: "POST",
      body: JSON.stringify({ project_id: p1state.projectId, run_id: p1state.runId }) });
    if ((res.status || "") === "RIGHTS_REQUIRED") {
      el("p2-lab-out").innerHTML = "<div class='notif'><div class='notif-kind'>RIGHTS_REQUIRED</div><div class='notif-msg'>" +
        esc(res.reason || "") + " · đã bỏ qua " + (res.skipped || []).length + " video không quyền, không tải video nào.</div></div>";
      toast("RIGHTS_REQUIRED: không tải video trái phép.", "err");
      return;
    }
    el("p2-lab-out").innerHTML = "<dl class='kv'>" +
      "<dt>Trạng thái</dt><dd>" + esc(res.status || "") + (res.duplicate ? " · KHÔNG TRÙNG (cache/library)" : "") + "</dd>" +
      "<dt>Video</dt><dd>" + esc(res.source_url || "") + " · " + (res.chosen_score || 0) + "đ</dd>" +
      "<dt>File</dt><dd>" + esc(res.local_path || "") + "</dd>" +
      "<dt>Bỏ qua</dt><dd>" + (res.skipped || []).length + " video không quyền</dd></dl>";
    toast(res.status === "DOWNLOADED" ? "Đã tải 1 video tốt nhất." : "Đã xử lý (không trùng): " + (res.status || ""), res.status === "DOWNLOAD_FAILED" ? "err" : "ok");
  } catch (e) { toast(e.message, "err"); }
}

const _bindP1orig = typeof bindP1 !== "undefined" ? bindP1 : null;

/* ------------------------------------------------ P3 publishing */
const p3state = { id: "" };

async function loadP3Settings() {
  renderProjectContext();
  try {
    const s = await api("/p3/settings");
    if (el("p3-auto")) el("p3-auto").value = s && s.auto_publish ? "on" : "off";
    if (el("p3-state")) {
      const on = !!(s && s.auto_publish);
      el("p3-state").textContent = on ? "Auto Publish: Bật" : "Auto Publish: Tắt";
      el("p3-state").className = "tag " + (on ? "tag-ok" : "");
    }
  } catch (_) { /* ignore */ }
  try {
    const r = await api("/p1/run?project_id=" + encodeURIComponent(p1state.projectId || "") +
      "&run_id=" + encodeURIComponent(p1state.runId || ""));
    const vids = (r && r.run && r.run.videos) || [];
    const sel = el("p3-video");
    if (sel) sel.innerHTML = vids.map((v) =>
      "<option value='" + esc(v.id) + "'>#" + (v.rank || "-") + " · @" + esc(v.creator || "") + " · " + esc(friendlyRights(v.rights)) + "</option>").join("")
      || "<option value=''>—</option>";
  } catch (_) { /* ignore */ }
  await p3Refresh();
  if (el("p3-auto") && !el("p3-auto").dataset.bound) {
    el("p3-auto").dataset.bound = "1";
    el("p3-auto").addEventListener("change", async (e) => {
      const sel = e.target;
      const wanted = sel.value;
      const previous = wanted === "on" ? "off" : "on";
      if (wanted === "on") {
        const ok = window.confirm(
          "Bật tự động xuất bản?\n\n" +
          "Các bài đã được duyệt và đến giờ sẽ có thể được đăng tự động. " +
          "Bài chưa duyệt vẫn không được đăng."
        );
        if (!ok) { sel.value = previous; return; }
      }
      sel.disabled = true;
      try {
        await api("/p3/settings", { method: "POST", body: JSON.stringify({ enabled: wanted === "on" }) });
        toast(wanted === "on" ? "Đã bật tự động xuất bản." : "Đã tắt tự động xuất bản.", "ok");
      } catch (err) {
        sel.value = previous;
        toast(err.message || "Không lưu được cài đặt tự động xuất bản.", "err");
      } finally {
        sel.disabled = false;
      }
      await loadP3Settings();
    });
  }
}

async function p3Refresh() {
  try {
    const res = await api("/p3/publications");
    let pubs = res.publications || [];
    // The publishing workspace follows the selected project so publications
    // from another project never leak into the current view.
    if (p1state.projectId) {
      pubs = pubs.filter((p) => String(p.project_id || "") === String(p1state.projectId));
    }
    const box = el("p3-list");
    if (!box) return;
    if (!pubs.length) {
      box.innerHTML = "<div class='empty'>Chưa có publication. Chọn video và bấm “Tạo publication”.</div>";
      renderP3Side(null);
      return;
    }
    box.innerHTML = pubs.map((p) => "<div class='notif' data-pid='" + esc(p.id) + "'>" +
      "<div class='notif-kind'>" + esc(p.id) + " · " + esc(friendlyPubStatus(p.status)) + "</div>" +
      "<div class='notif-msg'>media: " + esc(p.media_path || "(chưa tải)") + " · đích: @" + esc(p.account || "—") +
      " · lịch: " + esc(friendlySchedule(p.scheduled_at)) + (p.posted_url ? " · <a href='" + esc(p.posted_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>xem bài đăng</a>" : "") +
      (p.error ? " · lỗi: " + esc(p.error) : "") + "</div>" +
      "<div class='row'><button class='btn' data-act='pick'>Chọn</button></div></div>").join("");
    box.querySelectorAll("[data-act='pick']").forEach((b) => b.addEventListener("click", () => {
      const pid = b.closest("[data-pid]").dataset.pid;
      selectP3Publication(pid, pubs);
    }));
    const current = pubs.find((x) => x.id === p3state.id) || pubs[0];
    if (current) selectP3Publication(current.id, pubs, true);
  } catch (_) { /* ignore */ }
}

function selectP3Publication(pid, pubs, silent) {
  p3state.id = pid;
  const list = Array.isArray(pubs) ? pubs : [];
  const p = list.find((x) => x.id === pid) || {};
  if (el("p3-caption")) el("p3-caption").value = p.caption || "";
  if (el("p3-tags")) el("p3-tags").value = (p.hashtags || []).join("\n");
  if (el("p3-account") && p.account) el("p3-account").value = p.account;
  if (el("p3-schedule")) el("p3-schedule").value = toLocalInput(p.scheduled_at || "");
  renderP3Side(p);
  if (!silent) toast("Đã chọn " + pid + " (" + friendlyPubStatus(p.status) + ").", "ok");
}

function renderP3Side(p) {
  const set = (id, text) => { const n = el(id); if (n) n.textContent = text; };
  if (!p || !p.id) {
    set("p3-side-id", "—");
    set("p3-side-status", "—");
    set("p3-side-rights", "—");
    set("p3-side-account", "—");
    set("p3-side-caption", "—");
    set("p3-side-approval", "—");
    set("p3-side-schedule", "—");
    if (el("p3-side-link")) el("p3-side-link").innerHTML = "";
    if (el("p3-side-next")) el("p3-side-next").textContent = "Tạo hoặc chọn một publication để bắt đầu.";
    return;
  }
  set("p3-side-id", p.id || "—");
  set("p3-side-status", friendlyPubStatus(p.status));
  set("p3-side-rights", p.rights ? friendlyRights(p.rights) : (p.media_path ? "Đã có file" : "—"));
  set("p3-side-account", p.account ? "@" + p.account : "—");
  set("p3-side-caption", p.caption ? (String(p.caption).slice(0, 80) + (String(p.caption).length > 80 ? "…" : "")) : "Chưa có caption");
  const st = String(p.status || "").toUpperCase();
  set("p3-side-approval", (st === "APPROVED" || st === "SCHEDULED" || st === "PUBLISHED") ? "Đã duyệt" : "Chưa duyệt");
  set("p3-side-schedule", friendlySchedule(p.scheduled_at));
  if (el("p3-side-link")) {
    el("p3-side-link").innerHTML = p.posted_url
      ? "<a href='" + esc(p.posted_url) + "' target='_blank' rel='noreferrer' style='color:var(--burgundy-ink)'>Mở bài đã đăng</a>"
      : "";
  }
  if (el("p3-side-next")) {
    let next = "Soạn caption, sau đó bấm “Duyệt bài”.";
    if (st === "PUBLISHED" && p.posted_url) next = "Bài đã đăng. Không cần thao tác thêm.";
    else if (st === "PUBLISH_UNKNOWN") next = "Chưa xác minh đăng bài. Kiểm tra TikTok Studio trước khi xử lý tiếp.";
    else if (st === "SCHEDULED") next = "Bài đã lên lịch. Chờ đến giờ chạy hoặc bấm “Chạy Auto Publish”.";
    else if (st === "APPROVED") next = "Bài đã duyệt. Đặt lịch đăng ở mục 03.";
    else if (!p.caption) next = "Tạo caption mẫu, chỉnh sửa rồi bấm “Lưu caption”.";
    el("p3-side-next").textContent = next;
  }
}

function _p3vid() {
  return (el("p3-video") && el("p3-video").value) || "";
}

async function p3Create() {
  if (!p1state.projectId || !p1state.runId || !_p3vid()) { toast("Chọn project/run/video để tạo publication.", "err"); return; }
  try {
    const r = await api("/p3/publication", { method: "POST",
      body: JSON.stringify({ project_id: p1state.projectId, run_id: p1state.runId, video_id: _p3vid() }) });
    p3state.id = (r.publication || {}).id || "";
    toast(r.deduplicated ? "Đã có publication (không trùng): " + p3state.id : "Đã tạo publication: " + p3state.id, "ok");
  } catch (e) { toast(e.message, "err"); }
  await p3Refresh();
}

async function p3Build() {
  if (!p3state.id) { toast("Tạo/chọn publication trước.", "err"); return; }
  try {
    const r = await api("/p3/caption/build", { method: "POST", body: JSON.stringify({ publication_id: p3state.id }) });
    if (el("p3-caption")) el("p3-caption").value = r.caption || "";
    if (el("p3-tags")) el("p3-tags").value = (r.hashtags || []).join("\n");
    toast("Caption tạo từ template (không AI).", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function p3Save() {
  if (!p3state.id) { toast("Tạo/chọn publication trước.", "err"); return; }
  try {
    const tags = (el("p3-tags").value || "").split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
    await api("/p3/caption/save", { method: "POST",
      body: JSON.stringify({ publication_id: p3state.id, caption: el("p3-caption").value || "", hashtags: tags }) });
    toast("Đã lưu caption.", "ok");
  } catch (e) { toast(e.message, "err"); }
  await p3Refresh();
}

async function p3Approve() {
  if (!p3state.id) { toast("Tạo/chọn publication trước.", "err"); return; }
  try {
    await api("/p3/approve", { method: "POST", body: JSON.stringify({ publication_id: p3state.id }) });
    toast("Đã duyệt " + p3state.id + " (duyệt ≠ đã đăng).", "ok");
  } catch (e) { toast(e.message, "err"); }
  await p3Refresh();
}

async function p3Schedule() {
  if (!p3state.id) { toast("Tạo/chọn publication trước.", "err"); return; }
  try {
    const local = (el("p3-schedule") && el("p3-schedule").value) || "";
    await api("/p3/schedule", { method: "POST", body: JSON.stringify({
      publication_id: p3state.id,
      scheduled_at: fromLocalInput(local),
      account: (el("p3-account") && el("p3-account").value) || "" }) });
    toast("Đã đặt lịch.", "ok");
  } catch (e) { toast(e.message, "err"); }
  await p3Refresh();
}

async function p3Run() {
  try {
    const r = await api("/p3/run-due", { method: "POST", body: JSON.stringify({}) });
    toast("Auto Publish: " + (r.status || "") + " · " + (r.outcomes || []).length + " việc.", (r.status === "OK") ? "ok" : "");
  } catch (e) { toast(e.message, "err"); }
  await p3Refresh();
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
