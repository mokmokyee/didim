/* ========================================
   디딤 (DiDim) — working prototype
   ======================================== */
(function () {
  "use strict";

  const STORAGE = {
    user: "didim_user_v2",
    saved: "didim_saved_ids_v2",
    recentSearch: "didim_recent_searches_v2",
    recentView: "didim_recent_views_v2",
    loggedIn: "didim_logged_in_v2",
    signupDraft: "didim_signup_draft_v1",
  };

  const INTERESTS = [
    "교육", "IT·기술", "디자인", "예술", "환경", "사회공헌",
    "창업", "금융", "마케팅", "콘텐츠", "기타",
  ];
  const REGIONS = [
    "전국", "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
  ];
  const METHODS = ["온라인", "오프라인", "온·오프라인 병행"];

  let PROGRAMS = [];

  /* ---------- Utils ---------- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function parseDate(str) {
    if (!str) return null;
    const p = str.split("-").map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }

  function today() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function daysUntil(endDateStr) {
    const end = parseDate(endDateStr);
    if (!end) return null;
    return Math.round((end - today()) / 86400000);
  }

  function enrich(p) {
    if (!p) return null;
    const calculated = daysUntil(p.recruitmentEndDate);
    const dDay = calculated === null && p.dDay !== undefined ? p.dDay : calculated;
    let status = p.status;
    if (dDay !== null && dDay < 0) status = "closed";
    else if (status !== "closed") status = "open";
    return Object.assign({}, p, { dDay: dDay, computedStatus: status });
  }

  function allPrograms() {
    return PROGRAMS.map(enrich);
  }

  function getProgramById(id) {
    return enrich(PROGRAMS.find((p) => String(p.id) === String(id)) || null);
  }

  function formatDate(str) {
    if (!str) return "-";
    const [y, m, d] = str.split("-");
    return y + "." + m + "." + d;
  }

  function dDayText(dDay) {
    if (dDay === null || dDay === undefined) return "-";
    if (dDay < 0) return "마감";
    if (dDay === 0) return "D-Day";
    return "D-" + dDay;
  }

  function dDayClass(dDay) {
    if (dDay === null || dDay < 0) return "badge-dday is-closed";
    if (dDay <= 3) return "badge-dday is-urgent";
    if (dDay <= 7) return "badge-dday is-warn";
    return "badge-dday";
  }

  function statusLabel(p) {
    if (p.computedStatus === "closed" || p.dDay < 0) return "모집 종료";
    if (p.dDay <= 7) return "마감 임박";
    return "모집 중";
  }

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function saveJSON(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function isLoggedIn() {
    return localStorage.getItem(STORAGE.loggedIn) === "1";
  }

  function getUser() {
    const user = loadJSON(STORAGE.user, null);
    if (user && Object.prototype.hasOwnProperty.call(user, "preferredMethods")) {
      delete user.preferredMethods;
      saveJSON(STORAGE.user, user);
    }
    return user;
  }

  function setUser(user) {
    saveJSON(STORAGE.user, user);
  }

  function toFrontendUser(profile) {
    if (!profile) return null;
    const birthDate = profile.birth_date || profile.birthDate || "";
    return Object.assign({}, profile, {
      name: profile.name || "",
      email: profile.email || "",
      birthDate: birthDate,
      age: birthDate ? Math.max(0, today().getFullYear() - Number(birthDate.split("-")[0])) : profile.age,
      userType: profile.user_type || profile.userType || "",
      interests: profile.interest_display_values || profile.interests || [],
      interestKeywords: profile.interest_keywords || [],
      preferredRegions: profile.preferred_regions || profile.preferredRegions || [],
      notificationSettings: profile.notification_settings || profile.notificationSettings || defaultNotifSettings(),
    });
  }

  function toBackendProfile(user) {
    return {
      name: user.name || "",
      email: user.email || "",
      birth_date: user.birthDate || "",
      user_type: user.userType || "",
      interest_display_values: user.interests || [],
      preferred_regions: user.preferredRegions || [],
      notification_settings: user.notificationSettings || defaultNotifSettings(),
    };
  }

  function getSignupDraft() {
    try {
      const draft = JSON.parse(sessionStorage.getItem(STORAGE.signupDraft)) || {};
      let changed = false;
      if (Object.prototype.hasOwnProperty.call(draft, "preferredMethods")) {
        delete draft.preferredMethods;
        changed = true;
      }
      if (changed) {
        sessionStorage.setItem(STORAGE.signupDraft, JSON.stringify(draft));
      }
      return draft;
    } catch (e) {
      return {};
    }
  }

  function setSignupDraft(patch) {
    const draft = Object.assign(getSignupDraft(), patch);
    sessionStorage.setItem(STORAGE.signupDraft, JSON.stringify(draft));
    return draft;
  }

  function clearSignupDraft() {
    sessionStorage.removeItem(STORAGE.signupDraft);
  }

  function defaultNotifSettings() {
    return { deadline7: true, deadline3: true, deadline1: true, newInterest: true };
  }

  function getSavedIds() {
    return loadJSON(STORAGE.saved, []);
  }

  function setSavedIds(ids) {
    saveJSON(STORAGE.saved, ids);
  }

  function isSaved(id) {
    return getSavedIds().map(String).includes(String(id));
  }

  function toggleSave(id) {
    const ids = getSavedIds().map(String);
    const value = String(id);
    const idx = ids.indexOf(value);
    if (idx >= 0) ids.splice(idx, 1);
    else ids.unshift(value);
    setSavedIds(ids);
    return idx < 0;
  }

  function getRecentSearches() {
    return loadJSON(STORAGE.recentSearch, []);
  }

  function pushRecentSearch(q) {
    if (!q || !q.trim()) return;
    const list = getRecentSearches().filter((x) => x !== q.trim());
    list.unshift(q.trim());
    saveJSON(STORAGE.recentSearch, list.slice(0, 8));
  }

  function getRecentViews() {
    return loadJSON(STORAGE.recentView, []);
  }

  function pushRecentView(id) {
    const list = getRecentViews().map(String).filter((x) => x !== String(id));
    list.unshift(String(id));
    saveJSON(STORAGE.recentView, list.slice(0, 10));
  }

  function showToast(msg) {
    let wrap = $(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      document.body.appendChild(wrap);
    }
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(function () { el.remove(); }, 2400);
  }

  function heartSvg(filled) {
    if (filled) {
      return '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
  }

  function saveBtnHtml(id) {
    const saved = isSaved(id);
    return (
      '<button type="button" class="save-btn' +
      (saved ? " is-saved" : "") +
      '" data-save="' +
      id +
      '" aria-label="' +
      (saved ? "저장 해제" : "저장") +
      '" aria-pressed="' +
      saved +
      '">' +
      heartSvg(saved) +
      "</button>"
    );
  }

  function programCardHtml(p) {
    const closed = p.computedStatus === "closed";
    return (
      '<article class="program-card">' +
      '<a class="card-link" href="detail.html?id=' + p.id + '">' +
      '<div class="program-card__thumb' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      '<span class="program-card__thumb-label">' + p.type + "</span></div>" +
      '<div class="program-card__body">' +
      '<span class="badge badge-type' + (p.type === "공모전" ? " is-contest" : "") + '">' + p.type + "</span>" +
      '<h3 class="program-card__title">' + escapeHtml(p.title) + "</h3>" +
      '<p class="program-card__summary">' + escapeHtml(p.summary) + "</p>" +
      '<div class="program-card__meta">' +
      "<span>" + escapeHtml(p.organization) + "</span>" +
      "<span>" + escapeHtml(p.target) + "</span>" +
      "<span>" + escapeHtml(p.method) + "</span>" +
      "<span>" + escapeHtml(p.region) + "</span>" +
      "</div>" +
      '<div class="program-card__foot">' +
      '<div class="program-card__stats">' +
      (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + "</span>" : "") +
      "<span>조회 " + p.viewCount.toLocaleString("ko-KR") + "</span>" +
      (closed ? '<span class="badge badge-status is-closed">모집 종료</span>' : "") +
      "</div></div></div></a>" +
      '<div style="padding:0 14px 14px;display:flex;justify-content:flex-end">' +
      saveBtnHtml(p.id) +
      "</div></article>"
    );
  }

  function newsCardHtml(p) {
    return (
      '<article class="news-card">' +
      '<a href="detail.html?id=' + p.id + '" class="news-card__thumb' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      escapeHtml(p.type) + "</a>" +
      '<a href="detail.html?id=' + p.id + '" class="news-card__body" style="text-decoration:none;color:inherit">' +
      (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + "</span>" : "") +
      "<h3>" + escapeHtml(p.title) + "</h3>" +
      '<div class="news-card__meta">' +
      (p.target ? "<span>" + escapeHtml(p.target) + "</span>" : "") +
      (p.recruitmentEndDate ? "<span>" + formatDate(p.recruitmentEndDate) + " 마감</span>" : "") +
      (p.region ? "<span>" + escapeHtml(p.region) + "</span>" : "") +
      (p.method ? "<span>" + escapeHtml(p.method) + "</span>" : "") +
      "</div></a>" +
      saveBtnHtml(p.id) +
      "</article>"
    );
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bindSaveButtons(root) {
    (root || document).addEventListener("click", async function (e) {
      const btn = e.target.closest("[data-save]");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      const id = btn.getAttribute("data-save");
      const nowSaved = toggleSave(id);
      btn.classList.toggle("is-saved", nowSaved);
      btn.setAttribute("aria-pressed", String(nowSaved));
      btn.setAttribute("aria-label", nowSaved ? "저장 해제" : "저장");
      btn.innerHTML = heartSvg(nowSaved);
      try {
        await window.DiDimAPI.setSaved(id, nowSaved);
        showToast(nowSaved ? "저장 목록에 추가했어요" : "저장을 해제했어요");
      } catch (error) {
        toggleSave(id);
        btn.classList.toggle("is-saved", !nowSaved);
        btn.setAttribute("aria-pressed", String(!nowSaved));
        btn.setAttribute("aria-label", !nowSaved ? "저장 해제" : "저장");
        btn.innerHTML = heartSvg(!nowSaved);
        showToast(error.message);
      }
      document.dispatchEvent(new CustomEvent("didim:saved-changed"));
    });
  }

  /* ---------- Notifications ---------- */
  function buildNotifications() {
    const user = getUser();
    const settings = (user && user.notificationSettings) || defaultNotifSettings();
    const items = [];
    const saved = allPrograms().filter((p) => isSaved(p.id) && p.computedStatus !== "closed");

    saved.forEach(function (p) {
      if (p.dDay === 7 && settings.deadline7) {
        items.push({ title: "마감 7일 전", body: "「" + p.title + "」 마감이 일주일 남았어요." });
      }
      if (p.dDay === 3 && settings.deadline3) {
        items.push({ title: "마감 3일 전", body: "「" + p.title + "」 마감이 임박했어요." });
      }
      if (p.dDay === 1 && settings.deadline1) {
        items.push({ title: "마감 하루 전", body: "「" + p.title + "」 내일 마감이에요." });
      }
    });

    if (settings.newInterest && user && user.interests && user.interests.length) {
      const fresh = allPrograms()
        .filter(function (p) {
          return p.computedStatus === "open" && p.category.some(function (c) {
            return user.interests.indexOf(c) >= 0;
          });
        })
        .sort(function (a, b) { return b.createdAt.localeCompare(a.createdAt); })[0];
      if (fresh) {
        items.push({
          title: "관심 분야 새 프로그램",
          body: "「" + fresh.title + "」이(가) 관심 분야와 관련 있어요.",
        });
      }
    }
    return items;
  }

  function initNotifUI() {
    const btn = $("[data-notif-toggle]");
    const panel = $("[data-notif-panel]");
    const list = $("[data-notif-list]");
    const dot = $("[data-notif-dot]");
    if (!btn || !panel || !list) return;

    function render() {
      const items = buildNotifications();
      if (dot) dot.hidden = items.length === 0;
      if (!items.length) {
        list.innerHTML = '<div class="notif-empty">새 알림이 없어요</div>';
        return;
      }
      list.innerHTML = items
        .map(function (n) {
          return '<div class="notif-item"><strong>' + escapeHtml(n.title) + "</strong>" + escapeHtml(n.body) + "</div>";
        })
        .join("");
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      panel.classList.toggle("is-open");
      render();
    });
    document.addEventListener("click", function () {
      panel.classList.remove("is-open");
    });
    panel.addEventListener("click", function (e) { e.stopPropagation(); });
    render();
  }

  /* ---------- Common shell helpers ---------- */
  function setActiveNav() {
    const page = document.body.dataset.page || "";
    $$(".top-nav a, .bottom-nav a, .ed-nav a, .gh-pillnav a").forEach(function (a) {
      const key = a.getAttribute("data-nav");
      if (!key) return;
      a.classList.toggle("is-active", key === page);
    });
  }

  /* ---------- Home ---------- */
  function galleryCardHtml(p) {
    return (
      '<article class="ed-gcard">' +
      '<a href="detail.html?id=' + p.id + '" class="ed-gcard__media' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      escapeHtml(p.type) +
      "</a>" +
      '<div class="ed-gcard__body">' +
      '<a href="detail.html?id=' + p.id + '"><h3>' + escapeHtml(p.title) + "</h3></a>" +
      '<div class="ed-gcard__meta">' +
      "<span>" + escapeHtml(p.organization) + "</span>" +
      "<span>" + escapeHtml(p.target) + "</span>" +
      "</div>" +
      '<div class="ed-gcard__foot">' +
      (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + "</span>" : "") +
      saveBtnHtml(p.id) +
      "</div></div></article>"
    );
  }

  function closingItemHtml(p) {
    return (
      '<article class="ed-close-item">' +
      '<a href="detail.html?id=' + p.id + '" class="ed-close-item__thumb' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      escapeHtml(p.type) +
      "</a>" +
      '<a href="detail.html?id=' + p.id + '" style="min-width:0;text-decoration:none;color:inherit">' +
      "<h3>" + escapeHtml(p.title) + "</h3>" +
      "<p>" + escapeHtml([p.target, p.recruitmentEndDate ? formatDate(p.recruitmentEndDate) + " 마감" : "", p.region].filter(Boolean).join(" · ")) + "</p>" +
      "</a>" +
      saveBtnHtml(p.id) +
      "</article>"
    );
  }

  function initMobileNav() {
    const toggle = $(".menu-toggle");
    const nav = $(".mobile-nav");
    const overlay = $(".mobile-overlay");
    if (!toggle || !nav) return;

    function setOpen(open) {
      nav.classList.toggle("is-open", open);
      if (overlay) overlay.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      document.body.style.overflow = open ? "hidden" : "";
    }

    toggle.addEventListener("click", function () {
      setOpen(!nav.classList.contains("is-open"));
    });
    if (overlay) overlay.addEventListener("click", function () { setOpen(false); });
    $$(".mobile-nav a").forEach(function (a) {
      a.addEventListener("click", function () { setOpen(false); });
    });
  }

  function glassCardHtml(p) {
    return (
      '<article class="gh-card">' +
      '<a href="detail.html?id=' + p.id + '" class="gh-card__media' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      escapeHtml(p.type) +
      "</a>" +
      '<div class="gh-card__body">' +
      '<a href="detail.html?id=' + p.id + '"><h3>' + escapeHtml(p.title) + "</h3></a>" +
      '<div class="gh-card__meta">' +
      "<span>" + escapeHtml(p.organization) + "</span>" +
      "<span>" + escapeHtml(p.target) + "</span>" +
      "</div>" +
      '<div class="gh-card__foot">' +
      (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + "</span>" : "") +
      saveBtnHtml(p.id) +
      "</div></div></article>"
    );
  }

  function glassRowHtml(p) {
    return (
      '<article class="gh-row">' +
      '<a href="detail.html?id=' + p.id + '" class="gh-row__thumb' + (p.type === "공모전" ? " is-contest" : "") + '">' +
      escapeHtml(p.type) +
      "</a>" +
      '<a href="detail.html?id=' + p.id + '" style="min-width:0;text-decoration:none;color:inherit">' +
      "<h3>" + escapeHtml(p.title) + "</h3>" +
      "<p>" + escapeHtml([p.target, p.recruitmentEndDate ? formatDate(p.recruitmentEndDate) + " 마감" : "", p.region].filter(Boolean).join(" · ")) + "</p>" +
      "</a>" +
      saveBtnHtml(p.id) +
      "</article>"
    );
  }

  function initHome() {
    if (document.body.dataset.page !== "home") return;
    const form = $("#home-search-form");
    const input = $("#home-search");
    const suggest = $("#search-suggest");
    const popular = $("#popular-list");
    const urgent = $("#urgent-list");

    const programs = allPrograms().filter((p) => p.computedStatus !== "closed");
    const popularList = programs.slice().sort((a, b) => b.viewCount - a.viewCount).slice(0, 8);
    const urgentList = programs
      .filter((p) => p.dDay >= 0 && p.dDay <= 10)
      .sort((a, b) => a.dDay - b.dDay)
      .slice(0, 4);

    const isEditorial = document.body.classList.contains("editorial");
    const isGlass = document.body.classList.contains("glass-home");

    if (popular) {
      if (isGlass) popular.innerHTML = popularList.map(glassCardHtml).join("");
      else if (isEditorial) popular.innerHTML = popularList.map(galleryCardHtml).join("");
      else popular.innerHTML = popularList.map(programCardHtml).join("");
    }
    if (urgent) {
      if (isGlass) urgent.innerHTML = urgentList.map(glassRowHtml).join("");
      else if (isEditorial) urgent.innerHTML = urgentList.map(closingItemHtml).join("");
      else urgent.innerHTML = urgentList.map(newsCardHtml).join("");
    }

    function renderSuggest() {
      if (!suggest) return;
      const recent = getRecentSearches();
      const defaults = ["장학금", "공모전", "IT·기술", "고등학생", "디자인", "창업"];
      const chips = (recent.length ? recent : defaults).slice(0, 6);
      suggest.innerHTML = chips
        .map(function (c) {
          return '<button type="button" class="chip" data-suggest="' + escapeHtml(c) + '">' + escapeHtml(c) + "</button>";
        })
        .join("");
    }
    renderSuggest();

    if (suggest) {
      suggest.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-suggest]");
        if (!btn || !input) return;
        input.value = btn.getAttribute("data-suggest");
        form && form.requestSubmit();
      });
    }

    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const q = (input && input.value.trim()) || "";
        const type = ($("#home-type") && $("#home-type").value) || "";
        const target = ($("#home-target") && $("#home-target").value) || "";
        const category = ($("#home-field") && $("#home-field").value) || "";
        pushRecentSearch(q || type || target || category);
        const params = new URLSearchParams();
        if (q) params.set("q", q);
        if (type) params.set("type", type);
        if (target) params.set("target", target);
        if (category) params.set("category", category);
        const qs = params.toString();
        window.location.href = "programs.html" + (qs ? "?" + qs : "");
      });
    }
  }

  /* ---------- Programs ---------- */
  function initPrograms() {
    if (document.body.dataset.page !== "programs") return;
    const listEl = $("#programs-list");
    const countEl = $("#result-count");
    const tagsEl = $("#active-filters");
    const sortEl = $("#sort-select");
    const searchEl = $("#programs-search");
    const resetBtn = $("#filter-reset");
    const clearSearch = $("#search-clear");
    const panel = $("#filter-panel");
    const toggle = $("#filter-toggle");
    const closeBtn = $("#filter-close");
    const applyBtn = $("#filter-apply");
    const backdrop = $("#filter-backdrop");
    const urlParams = new URLSearchParams(location.search);
    let currentSearch = urlParams.get("q") || "";
    let renderSequence = 0;

    if (searchEl) searchEl.value = currentSearch;
    [["type", urlParams.get("type")], ["target", urlParams.get("target")], ["category", urlParams.get("category")]]
      .forEach(function (entry) {
        const name = entry[0];
        const value = entry[1];
        if (!value) return;
        if (name === "type") {
          const all = $('input[name="type"][value="전체"]');
          if (all) all.checked = false;
        }
        const input = $('input[name="' + name + '"][value="' + value + '"]');
        if (input) input.checked = true;
      });

    function openFilter(open) {
      if (!panel) return;
      panel.classList.toggle("is-open", open);
      if (backdrop) backdrop.classList.toggle("is-open", open);
    }

    function getFilters() {
      return {
        type: $$('input[name="type"]:checked').map((el) => el.value).filter((v) => v !== "전체"),
        target: $$('input[name="target"]:checked').map((el) => el.value),
        category: $$('input[name="category"]:checked').map((el) => el.value),
        region: $$('input[name="region"]:checked').map((el) => el.value),
        sort: (sortEl && sortEl.value) || "recommend",
        page_size: 100,
      };
    }

    function renderTags() {
      if (!tagsEl) return;
      const filters = getFilters();
      const tags = [];
      filters.type.forEach((v) => tags.push({ key: "type", value: v }));
      filters.target.forEach((v) => tags.push({ key: "target", value: v }));
      filters.category.forEach((v) => tags.push({ key: "category", value: v }));
      filters.region.forEach((v) => tags.push({ key: "region", value: v }));
      if (currentSearch) tags.push({ key: "q", value: currentSearch });
      tagsEl.innerHTML = tags.length
        ? tags.map(function (tag) {
            return '<button type="button" class="chip is-filter" data-remove-key="' +
              tag.key + '" data-remove-value="' + escapeHtml(tag.value) + '">' +
              escapeHtml(tag.value) + ' <span class="chip-remove" aria-hidden="true">×</span></button>';
          }).join("") +
          '<button type="button" class="btn btn-ghost btn-sm" id="clear-all-filters">전체 초기화</button>'
        : "";
    }

    async function render() {
      const sequence = ++renderSequence;
      renderTags();
      if (listEl) listEl.innerHTML = '<div class="empty-state"><p>프로그램을 불러오는 중이에요.</p></div>';
      try {
        const filters = getFilters();
        const result = currentSearch
          ? await window.DiDimAPI.searchOpportunities(Object.assign({ query: currentSearch }, filters))
          : await window.DiDimAPI.listOpportunities(filters);
        if (sequence !== renderSequence) return;
        PROGRAMS = result.items;
        if (countEl) countEl.innerHTML = "총 <strong>" + result.total + "</strong>개";
        if (!listEl) return;
        if (!PROGRAMS.length) {
          listEl.innerHTML =
            '<div class="empty-state"><h3>검색 결과가 없어요</h3><p>다른 검색어나 필터로 다시 찾아보세요.</p>' +
            '<button type="button" class="btn btn-primary" id="empty-reset">필터 초기화</button></div>';
          const emptyReset = $("#empty-reset");
          if (emptyReset) emptyReset.addEventListener("click", resetAll);
          return;
        }
        listEl.innerHTML = '<div class="card-grid">' + PROGRAMS.map(enrich).map(programCardHtml).join("") + "</div>";
      } catch (error) {
        if (sequence !== renderSequence || !listEl) return;
        if (countEl) countEl.innerHTML = "총 <strong>0</strong>개";
        listEl.innerHTML = '<div class="empty-state"><h3>프로그램을 불러오지 못했어요</h3><p>' +
          escapeHtml(error.message) + '</p></div>';
      }
    }

    function resetAll() {
      $$("#filter-panel input[type=checkbox]").forEach(function (el) {
        el.checked = el.name === "type" && el.value === "전체";
      });
      currentSearch = "";
      if (searchEl) searchEl.value = "";
      render();
    }

    if (toggle) toggle.addEventListener("click", function () { openFilter(true); });
    if (closeBtn) closeBtn.addEventListener("click", function () { openFilter(false); });
    if (applyBtn) applyBtn.addEventListener("click", function () { openFilter(false); render(); });
    if (backdrop) backdrop.addEventListener("click", function () { openFilter(false); });

    if (tagsEl) {
      tagsEl.addEventListener("click", function (event) {
        if (event.target.closest("#clear-all-filters")) return resetAll();
        const chip = event.target.closest("[data-remove-key]");
        if (!chip) return;
        const key = chip.getAttribute("data-remove-key");
        const value = chip.getAttribute("data-remove-value");
        if (key === "q") {
          currentSearch = "";
          if (searchEl) searchEl.value = "";
        } else {
          const input = $('input[name="' + key + '"][value="' + value + '"]');
          if (input) input.checked = false;
          if (key === "type" && !$$('input[name="type"]:checked').length) {
            const all = $('input[name="type"][value="전체"]');
            if (all) all.checked = true;
          }
        }
        render();
      });
    }

    $$('input[name="type"]').forEach(function (input) {
      input.addEventListener("change", function () {
        if (input.value === "전체" && input.checked) {
          $$('input[name="type"]').forEach(function (other) { if (other !== input) other.checked = false; });
        } else if (input.checked) {
          const all = $('input[name="type"][value="전체"]');
          if (all) all.checked = false;
        }
        render();
      });
    });
    $$('#filter-panel input:not([name="type"])').forEach(function (input) {
      input.addEventListener("change", render);
    });
    if (sortEl) sortEl.addEventListener("change", render);
    if (clearSearch) {
      clearSearch.addEventListener("click", function () {
        currentSearch = "";
        if (searchEl) {
          searchEl.value = "";
          searchEl.focus();
        }
        render();
      });
    }
    if (resetBtn) resetBtn.addEventListener("click", resetAll);
    const searchForm = $("#programs-search-form");
    if (searchForm) {
      searchForm.addEventListener("submit", function (event) {
        event.preventDefault();
        currentSearch = (searchEl && searchEl.value.trim()) || "";
        pushRecentSearch(currentSearch);
        render();
      });
    }
    render();
  }


  /* ---------- Detail ---------- */
  async function initDetail() {
    if (document.body.dataset.page !== "detail") return;
    const id = new URLSearchParams(location.search).get("id");
    const root = $("#detail-root");
    if (!root) return;
    if (!id) {
      root.innerHTML = '<div class="container"><div class="empty-state"><h3>프로그램을 찾을 수 없어요</h3></div></div>';
      return;
    }
    root.innerHTML = '<div class="container"><div class="empty-state"><p>프로그램 정보를 불러오는 중이에요.</p></div></div>';

    try {
      const p = enrich(await window.DiDimAPI.getOpportunity(id));
      if (!p) throw new Error("프로그램을 찾을 수 없습니다.");
      const existingIndex = PROGRAMS.findIndex((item) => String(item.id) === String(p.id));
      if (existingIndex >= 0) PROGRAMS[existingIndex] = p;
      else PROGRAMS.push(p);
      pushRecentView(p.id);

      const closed = p.computedStatus === "closed" || (p.dDay !== null && p.dDay < 0);
      const validApplicationUrl = /^https?:\/\//i.test(p.applicationUrl || "");
      const panel = function (title, value) {
        return value ? '<div class="detail-panel"><h2>' + title + '</h2><p>' + escapeHtml(value) + '</p></div>' : "";
      };
      const info = [];
      if (p.organization) info.push(["주최·주관", p.organization]);
      if (p.target) info.push(["모집 대상", p.target]);
      if (p.ageRequirement) info.push(["나이/학년", p.ageRequirement]);
      if (p.category.length) info.push(["관련 분야", p.category.join(", ")]);
      if (p.method) info.push(["진행 방식", p.method]);
      if (p.region) info.push(["활동 지역", p.region]);
      if (p.recruitmentStartDate || p.recruitmentEndDate) {
        info.push(["모집 기간", [formatDate(p.recruitmentStartDate), formatDate(p.recruitmentEndDate)].filter((v) => v !== "-").join(" ~ ")]);
      }
      if (p.dDay !== null) info.push(["D-Day", dDayText(p.dDay)]);
      info.push(["조회수", p.viewCount.toLocaleString("ko-KR")]);
      if (p.contact) info.push(["문의처", p.contact]);

      const primaryAction = closed
        ? '<button type="button" class="btn btn-primary is-disabled" disabled>모집 종료</button>'
        : validApplicationUrl
          ? '<a class="btn btn-primary" href="' + escapeHtml(p.applicationUrl) + '" target="_blank" rel="noopener noreferrer">지원하러 가기</a>'
          : '<button type="button" class="btn btn-primary is-disabled" disabled>지원 링크 없음</button>';

      root.innerHTML =
        '<div class="detail-hero"><div class="container">' +
        '<div class="detail-hero__thumb' + (p.type === "공모전" ? " is-contest" : "") + '">' + escapeHtml(p.type) + '</div>' +
        '<span class="badge badge-type' + (p.type === "공모전" ? " is-contest" : "") + '">' + escapeHtml(p.type) + '</span> ' +
        (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + '</span> ' : "") +
        (closed ? '<span class="badge badge-status is-closed">모집 종료</span>' : '<span class="badge badge-status">모집 중</span>') +
        '<h1 class="detail-title">' + escapeHtml(p.title) + '</h1>' +
        (p.summary ? '<p style="color:var(--text-2)">' + escapeHtml(p.summary) + '</p>' : "") +
        '<div class="detail-actions">' + primaryAction +
        '<button type="button" class="btn btn-outline" id="detail-save">' + (isSaved(p.id) ? "저장됨" : "저장하기") + '</button>' +
        '<button type="button" class="btn btn-ghost" id="detail-share">링크 공유</button>' +
        '</div></div></div>' +
        '<div class="container detail-grid"><div>' +
        panel("프로그램 소개", p.description) +
        panel("활동 내용", p.activities) +
        panel("지원 자격", p.requirements) +
        panel("제출 서류", p.documents) +
        panel("혜택", p.benefits) +
        '</div><aside class="sticky-cta"><div class="detail-panel"><h2>기본 정보</h2><dl class="info-list">' +
        info.map(function (entry) {
          return '<dt>' + escapeHtml(entry[0]) + '</dt><dd>' + escapeHtml(entry[1]) + '</dd>';
        }).join("") +
        '</dl></div></aside></div>';

      const saveBtn = $("#detail-save");
      if (saveBtn) {
        saveBtn.addEventListener("click", async function () {
          const nowSaved = toggleSave(p.id);
          try {
            await window.DiDimAPI.setSaved(p.id, nowSaved);
            saveBtn.textContent = nowSaved ? "저장됨" : "저장하기";
            showToast(nowSaved ? "저장했어요" : "저장을 해제했어요");
          } catch (error) {
            toggleSave(p.id);
            showToast(error.message);
          }
        });
      }
      const shareBtn = $("#detail-share");
      if (shareBtn) {
        shareBtn.addEventListener("click", async function () {
          try {
            if (navigator.share) await navigator.share({ title: p.title, url: location.href });
            else {
              await navigator.clipboard.writeText(location.href);
              showToast("링크를 복사했어요");
            }
          } catch (error) {
            showToast("공유를 취소했어요");
          }
        });
      }
    } catch (error) {
      root.innerHTML = '<div class="container"><div class="empty-state"><h3>프로그램을 불러오지 못했어요</h3><p>' +
        escapeHtml(error.message) + '</p><a class="btn btn-primary" href="programs.html">프로그램으로 돌아가기</a></div></div>';
    }
  }


  /* ---------- Recommend ---------- */
  function recommendReason(p, user) {
    if (user.interests && user.interests.some((i) => p.category.indexOf(i) >= 0)) {
      const hit = user.interests.find((i) => p.category.indexOf(i) >= 0);
      return "회원님의 관심 분야인 " + hit + "과 관련된 프로그램이에요.";
    }
    if (user.userType && p.target === user.userType) {
      return user.userType + "을 대상으로 모집 중인 " + p.type + "이에요.";
    }
    const saved = getSavedIds();
    if (saved.length) {
      const savedProgs = saved.map(getProgramById);
      const cats = {};
      savedProgs.forEach(function (sp) {
        (sp.category || []).forEach(function (c) { cats[c] = true; });
      });
      if (p.category.some((c) => cats[c])) {
        return "저장한 프로그램과 비슷한 " + p.type + "이에요.";
      }
    }
    if (user.preferredRegions && user.preferredRegions.indexOf(p.region) >= 0) {
      return "선호 지역(" + p.region + ")에서 진행되는 프로그램이에요.";
    }
    return "회원님께 어울릴 수 있는 프로그램이에요.";
  }

  function scoreProgram(p, user) {
    let s = 0;
    if (!user) return p.viewCount;
    if (user.userType && p.target === user.userType) s += 30;
    if (user.userType === "기타" && p.target === "기타") s += 20;
    (user.interests || []).forEach(function (i) {
      if (p.category.indexOf(i) >= 0) s += 20;
    });
    if ((user.preferredRegions || []).indexOf(p.region) >= 0) s += 12;
    if ((user.preferredRegions || []).indexOf("전국") >= 0) s += 4;
    const saved = getSavedIds().map(getProgramById);
    saved.forEach(function (sp) {
      if (sp.category.some((c) => p.category.indexOf(c) >= 0)) s += 8;
    });
    if (user.age) {
      // soft boost open programs
      s += 2;
    }
    s += Math.min(p.viewCount / 500, 5);
    return s;
  }

  async function initRecommend() {
    if (document.body.dataset.page !== "recommend") return;
    const root = $("#recommend-root");
    if (!root) return;

    if (!isLoggedIn() || !getUser()) {
      root.innerHTML =
        '<div class="empty-state"><h3>로그인하면 맞춤 추천을 받을 수 있어요</h3>' +
        '<p>나이와 관심 분야를 알려주시면 더 정확한 프로그램을 추천해 드려요.</p>' +
        '<a class="btn btn-primary" href="login.html">로그인 / 회원가입</a></div>';
      return;
    }

    root.innerHTML = '<div class="empty-state"><p>맞춤 프로그램을 찾는 중이에요.</p></div>';
    try {
      const user = getUser();
      const list = (await window.DiDimAPI.recommendations(20)).map(enrich);
      PROGRAMS = list;
      if (!list.length) {
        root.innerHTML =
          '<div class="empty-state"><h3>아직 추천할 프로그램이 없어요</h3>' +
          '<p>관심 분야를 수정하면 더 잘 맞는 프로그램을 찾아드릴게요.</p>' +
          '<a class="btn btn-primary" href="mypage.html#edit-profile">관심 분야 수정하기</a></div>';
        return;
      }
      root.innerHTML =
        '<p style="color:var(--text-2);margin-bottom:14px">' +
        escapeHtml(user.name || "회원") + '님을 위한 추천 ' + list.length + '개</p>' +
        '<div class="stack">' +
        list.map(function (p) {
          return (
            '<article class="news-card" style="grid-template-columns:88px 1fr auto">' +
            '<a href="detail.html?id=' + encodeURIComponent(p.id) + '" class="news-card__thumb' +
            (p.type === "공모전" ? " is-contest" : "") + '" style="text-decoration:none">' +
            escapeHtml(p.type) + '</a><div class="news-card__body">' +
            '<div class="reason-chip">' + escapeHtml(p.recommendationReason) + '</div>' +
            '<a href="detail.html?id=' + encodeURIComponent(p.id) + '"><h3>' + escapeHtml(p.title) + '</h3></a>' +
            '<div class="news-card__meta"><span>' + escapeHtml(p.type) + '</span>' +
            (p.target ? '<span>' + escapeHtml(p.target) + '</span>' : "") +
            (p.category.length ? '<span>' + escapeHtml(p.category.join(", ")) + '</span>' : "") +
            (p.recruitmentEndDate ? '<span>' + formatDate(p.recruitmentEndDate) + '</span>' : "") +
            (p.dDay !== null ? '<span class="' + dDayClass(p.dDay) + '">' + dDayText(p.dDay) + '</span>' : "") +
            '</div></div>' + saveBtnHtml(p.id) + '</article>'
          );
        }).join("") + '</div>';
    } catch (error) {
      root.innerHTML = '<div class="empty-state"><h3>추천을 불러오지 못했어요</h3><p>' +
        escapeHtml(error.message) + '</p></div>';
    }
  }


  /* ---------- Saved ---------- */
  async function initSaved() {
    if (document.body.dataset.page !== "saved") return;
    const root = $("#saved-root");
    const tabs = $$("[data-saved-tab]");
    const sortEl = $("#saved-sort");
    let tab = "all";
    let sequence = 0;

    async function render() {
      const requestSequence = ++sequence;
      if (root) root.innerHTML = '<div class="empty-state"><p>저장한 프로그램을 불러오는 중이에요.</p></div>';
      const sortValue = (sortEl && sortEl.value) || "deadline-asc";
      const serverSort = sortValue === "recent" ? "saved_at" : sortValue;
      try {
        const result = await window.DiDimAPI.saved(tab, serverSort);
        if (requestSequence !== sequence || !root) return;
        const items = result.items.map(enrich);
        PROGRAMS = items;
        setSavedIds(items.map((item) => String(item.id)));
        if (!items.length) {
          root.innerHTML = tab === "all"
            ? '<div class="empty-state"><h3>아직 저장한 프로그램이 없어요</h3><p>관심 있는 장학금과 공모전을 찾아보세요.</p>' +
              '<a class="btn btn-primary" href="programs.html">프로그램 둘러보기</a></div>'
            : '<div class="empty-state"><h3>이 상태에 해당하는 프로그램이 없어요</h3><p>다른 탭을 확인해 보세요.</p></div>';
          return;
        }
        root.innerHTML = '<div class="stack">' + items.map(newsCardHtml).join("") + '</div>';
      } catch (error) {
        if (requestSequence !== sequence || !root) return;
        root.innerHTML = '<div class="empty-state"><h3>저장 목록을 불러오지 못했어요</h3><p>' +
          escapeHtml(error.message) + '</p></div>';
      }
    }

    tabs.forEach(function (button) {
      button.addEventListener("click", function () {
        tab = button.getAttribute("data-saved-tab");
        tabs.forEach((item) => item.classList.toggle("is-active", item === button));
        render();
      });
    });
    if (sortEl) sortEl.addEventListener("change", render);
    document.addEventListener("didim:saved-changed", render);
    render();
  }


  /* ---------- Auth / MyPage / Signup ---------- */
  function initLogin() {
    if (document.body.dataset.page !== "login") return;
    const googleBtn = $("#google-login");
    if (googleBtn) {
      googleBtn.addEventListener("click", async function () {
        googleBtn.disabled = true;
        try {
          const firebaseUser = await window.DiDimAPI.signInGoogle();
          if (!firebaseUser && !window.DiDimAPI.hasFirebase()) {
            const existing = getUser();
            if (existing && existing.name) {
              localStorage.setItem(STORAGE.loggedIn, "1");
              location.href = "mypage.html";
            } else location.href = "signup.html";
            return;
          }
          try {
            const profile = toFrontendUser(await window.DiDimAPI.getUserProfile());
            setUser(profile);
            localStorage.setItem(STORAGE.loggedIn, "1");
            showToast("환영합니다, " + profile.name + "님");
            setTimeout(function () { location.href = "mypage.html"; }, 400);
          } catch (error) {
            if (error.status !== 404) throw error;
            setSignupDraft({ name: firebaseUser.displayName || "", email: firebaseUser.email || "" });
            location.href = "signup.html?provider=google";
          }
        } catch (error) {
          showToast(error.message || "로그인하지 못했어요");
          googleBtn.disabled = false;
        }
      });
    }
  }

  /* ---------- Multi-step signup wizard ---------- */
  const SIGNUP_STEPS = ["signup", "signup-scholarship", "signup-career", "signup-password", "signup-email"];

  function signupStepIndex() {
    return SIGNUP_STEPS.indexOf(document.body.dataset.page);
  }

  function paintSignupProgress() {
    const idx = signupStepIndex();
    if (idx < 0) return;
    const total = SIGNUP_STEPS.length;
    $$(".signup-progress span").forEach(function (dot, i) {
      dot.classList.toggle("is-done", i < idx);
      dot.classList.toggle("is-active", i === idx);
    });
    const label = $(".signup-step-label");
    if (label) label.textContent = "STEP " + (idx + 1) + " / " + total;
  }

  function invalidGroup(el) {
    const g = el && el.closest(".form-group");
    if (g) g.classList.add("is-invalid");
  }

  function clearInvalidGroups() {
    $$(".form-group").forEach((g) => g.classList.remove("is-invalid"));
  }

  function goToSignupStep(page) {
    location.href = page + ".html";
  }

  function initSignupStep1() {
    if (document.body.dataset.page !== "signup") return;
    const form = $("#signup-form");
    if (!form) return;
    paintSignupProgress();

    const draft = getSignupDraft();
    const name = $("#signup-name");
    const email = $("#signup-email");
    const birth = $("#signup-birth");
    if (name && draft.name) name.value = draft.name;
    if (email && draft.email) email.value = draft.email;
    if (birth && draft.birthDate) birth.value = draft.birthDate;

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      clearInvalidGroups();
      let ok = true;
      if (!name || !name.value.trim()) { invalidGroup(name); ok = false; }
      if (!email || !email.value.trim() || email.value.indexOf("@") < 0) { invalidGroup(email); ok = false; }
      if (!birth || !birth.value) { invalidGroup(birth); ok = false; }
      if (!ok) return;

      setSignupDraft({
        name: name.value.trim(),
        email: email.value.trim(),
        birthDate: birth.value,
      });
      goToSignupStep("signup-scholarship");
    });
  }

  function initSignupStep2() {
    if (document.body.dataset.page !== "signup-scholarship") return;
    const form = $("#signup-form");
    if (!form) return;
    paintSignupProgress();

    const draft = getSignupDraft();
    if (!draft.name) { goToSignupStep("signup"); return; }
    if (draft.userType) {
      const r = $('input[name="userType"][value="' + draft.userType + '"]');
      if (r) { r.checked = true; const lab = r.closest("label"); if (lab) lab.classList.add("is-checked"); }
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearInvalidGroups();
      const type = $('input[name="userType"]:checked');
      if (!type) {
        const tg = $("#userType-group");
        if (tg) tg.classList.add("is-invalid");
        return;
      }
      setSignupDraft({ userType: type.value });
      goToSignupStep("signup-career");
    });
  }

  function initSignupStep3() {
    if (document.body.dataset.page !== "signup-career") return;
    const form = $("#signup-form");
    if (!form) return;
    paintSignupProgress();

    const draft = getSignupDraft();
    if (!draft.userType) { goToSignupStep("signup-scholarship"); return; }
    (draft.interests || []).forEach(function (v) {
      const c = $('input[name="interest"][value="' + v + '"]');
      if (c) { c.checked = true; const lab = c.closest("label"); if (lab) lab.classList.add("is-checked"); }
    });

    const otherInterest = $('input[name="interest"][value="기타"]');
    const customInterestInput = $("#custom-interest");
    if (customInterestInput && draft.customInterest) customInterestInput.value = draft.customInterest;

    function syncCustomInterestRequired() {
      if (!customInterestInput) return;
      const isRequired = !!(otherInterest && otherInterest.checked);
      customInterestInput.required = isRequired;
      customInterestInput.setAttribute("aria-required", String(isRequired));
      customInterestInput.placeholder = isRequired ? "직접 입력 (필수)" : "직접 입력 (선택)";
      if (!isRequired) {
        const group = customInterestInput.closest(".form-group");
        if (group) group.classList.remove("is-invalid");
      }
    }

    if (otherInterest) otherInterest.addEventListener("change", syncCustomInterestRequired);
    if (customInterestInput) {
      customInterestInput.addEventListener("input", function () {
        if (customInterestInput.value.trim()) {
          const group = customInterestInput.closest(".form-group");
          if (group) group.classList.remove("is-invalid");
        }
      });
    }
    syncCustomInterestRequired();

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearInvalidGroups();
      const interests = $$('input[name="interest"]:checked').map((el) => el.value);
      const customInterest = (customInterestInput && customInterestInput.value.trim()) || "";
      if (interests.indexOf("기타") >= 0 && !customInterest) {
        invalidGroup(customInterestInput);
        customInterestInput.focus();
        showToast("기타 관심 분야를 직접 입력해 주세요");
        return;
      }
      if (customInterest) interests.push(customInterest);
      if (!interests.length) {
        showToast("관심 분야를 하나 이상 선택해 주세요");
        return;
      }
      setSignupDraft({ interests: interests, customInterest: customInterest });
      goToSignupStep("signup-password");
    });
  }

  function initSignupStep4() {
    if (document.body.dataset.page !== "signup-password") return;
    const form = $("#signup-form");
    if (!form) return;
    paintSignupProgress();

    const draft = getSignupDraft();
    if (!draft.interests) { goToSignupStep("signup-career"); return; }
    (draft.preferredRegions || []).forEach(function (v) {
      const c = $('input[name="region"][value="' + v + '"]');
      if (c) { c.checked = true; const lab = c.closest("label"); if (lab) lab.classList.add("is-checked"); }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      setSignupDraft({
        preferredRegions: $$('input[name="region"]:checked').map((el) => el.value),
      });
      goToSignupStep("signup-email");
    });
  }

  function initSignupStep5() {
    if (document.body.dataset.page !== "signup-email") return;
    const form = $("#signup-form");
    if (!form) return;
    paintSignupProgress();

    const draft = getSignupDraft();
    if (!draft.name || !draft.userType || !draft.interests) { goToSignupStep("signup"); return; }

    const summary = $("#signup-summary");
    if (summary) {
      summary.innerHTML =
        '<dl class="info-list">' +
        "<div><dt>이름</dt><dd>" + escapeHtml(draft.name) + "</dd></div>" +
        "<div><dt>이메일</dt><dd>" + escapeHtml(draft.email || "") + "</dd></div>" +
        "<div><dt>사용자 유형</dt><dd>" + escapeHtml(draft.userType) + "</dd></div>" +
        "<div><dt>관심 분야</dt><dd>" + escapeHtml((draft.interests || []).join(", ")) + "</dd></div>" +
        "<div><dt>선호 지역</dt><dd>" + escapeHtml((draft.preferredRegions || []).join(", ") || "전국") + "</dd></div>" +
        "</dl>";
    }

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const agree = $("#signup-agree");
      if (!agree || !agree.checked) {
        showToast("개인정보 수집 및 이용에 동의해 주세요");
        return;
      }

      const birthDate = draft.birthDate || "";
      const age = birthDate ? Math.max(0, today().getFullYear() - Number(birthDate.split("-")[0])) : null;

      const user = {
        name: draft.name,
        email: draft.email,
        profileImage: null,
        birthDate: birthDate,
        age: age,
        userType: draft.userType,
        interests: draft.interests || [],
        preferredRegions: draft.preferredRegions || [],
        savedProgramIds: getSavedIds(),
        recentlyViewedProgramIds: getRecentViews(),
        notificationSettings: defaultNotifSettings(),
        createdAt: new Date().toISOString().slice(0, 10),
      };
      const submitButton = form.querySelector('[type="submit"]');
      if (submitButton) submitButton.disabled = true;
      try {
        let firebaseUser = await window.DiDimAPI.currentUser();
        if (!firebaseUser) {
          showToast("회원가입을 완료하려면 Google 계정으로 로그인해 주세요");
          firebaseUser = await window.DiDimAPI.signInGoogle();
          if (firebaseUser.email) user.email = firebaseUser.email;
          if (!user.name && firebaseUser.displayName) user.name = firebaseUser.displayName;
        }
        const saved = toFrontendUser(await window.DiDimAPI.putUserProfile(toBackendProfile(user)));
        setUser(saved);
        localStorage.setItem(STORAGE.loggedIn, "1");
        clearSignupDraft();
        showToast("회원가입이 완료되었어요");
        setTimeout(function () { location.href = "recommend.html"; }, 600);
      } catch (error) {
        showToast(error.message || "회원가입 정보를 저장하지 못했어요");
        if (submitButton) submitButton.disabled = false;
      }
    });
  }

  function initSignup() {
    initSignupStep1();
    initSignupStep2();
    initSignupStep3();
    initSignupStep4();
    initSignupStep5();
  }

  function initMyPage() {
    if (document.body.dataset.page !== "mypage") return;
    const guest = $("#mypage-guest");
    const member = $("#mypage-member");

    if (!isLoggedIn() || !getUser()) {
      if (guest) guest.hidden = false;
      if (member) member.hidden = true;
      return;
    }

    if (guest) guest.hidden = true;
    if (member) member.hidden = false;

    const user = getUser();
    const nameEl = $("#mp-name");
    const subEl = $("#mp-sub");
    const avatar = $("#mp-avatar");
    if (nameEl) nameEl.textContent = user.name;
    if (subEl) {
      subEl.textContent =
        (user.userType || "") +
        " · " +
        (user.age ? user.age + "세" : "") +
        " · " +
        (user.email || "");
    }
    if (avatar) avatar.textContent = (user.name || "?").charAt(0);

    const savedCount = $("#mp-saved-count");
    if (savedCount) savedCount.textContent = String(getSavedIds().length);

    const recentEl = $("#mp-recent");
    if (recentEl) {
      const views = getRecentViews().map(getProgramById).slice(0, 4);
      if (!views.length) recentEl.innerHTML = '<p style="color:var(--muted);font-size:0.9rem">최근 본 프로그램이 없어요.</p>';
      else recentEl.innerHTML = '<div class="stack">' + views.map(newsCardHtml).join("") + "</div>";
    }

    // notification toggles
    const settings = user.notificationSettings || defaultNotifSettings();
    $$("[data-notif-setting]").forEach(function (input) {
      const key = input.getAttribute("data-notif-setting");
      input.checked = !!settings[key];
      input.addEventListener("change", async function () {
        const u = getUser();
        u.notificationSettings = u.notificationSettings || defaultNotifSettings();
        u.notificationSettings[key] = input.checked;
        setUser(u);
        try {
          setUser(toFrontendUser(await window.DiDimAPI.putUserProfile(toBackendProfile(u))));
          showToast("알림 설정을 저장했어요");
        } catch (error) {
          showToast(error.message);
        }
      });
    });

    const logout = $("#logout-btn");
    if (logout) {
      logout.addEventListener("click", async function () {
        await window.DiDimAPI.signOut().catch(function () {});
        localStorage.setItem(STORAGE.loggedIn, "0");
        showToast("로그아웃했어요");
        setTimeout(function () { location.reload(); }, 400);
      });
    }

    const withdraw = $("#withdraw-btn");
    if (withdraw) {
      withdraw.addEventListener("click", async function () {
        if (!confirm("정말 탈퇴할까요? 저장된 프로필 정보가 삭제됩니다.")) return;
        try {
          await window.DiDimAPI.deleteUserProfile();
          await window.DiDimAPI.signOut().catch(function () {});
          localStorage.removeItem(STORAGE.user);
          localStorage.setItem(STORAGE.loggedIn, "0");
          showToast("회원 탈퇴가 완료되었어요");
          setTimeout(function () { location.href = "index.html"; }, 500);
        } catch (error) {
          showToast(error.message);
        }
      });
    }

    const editForm = $("#edit-profile-form");
    const editModal = $("#edit-modal");
    const openEdit = $("#open-edit-profile");
    const closeEdit = $("#close-edit-profile");

    function fillEdit() {
      const u = getUser();
      if ($("#edit-name")) $("#edit-name").value = u.name || "";
      if ($("#edit-birth")) $("#edit-birth").value = u.birthDate || "";
      $$('input[name="editUserType"]').forEach(function (el) {
        el.checked = el.value === u.userType;
      });
      $$('input[name="editInterest"]').forEach(function (el) {
        el.checked = (u.interests || []).indexOf(el.value) >= 0;
      });
      const customInterest = (u.interests || []).find((value) => INTERESTS.indexOf(value) < 0) || "";
      if ($("#edit-custom-interest")) $("#edit-custom-interest").value = customInterest;
      $$('input[name="editRegion"]').forEach(function (el) {
        el.checked = (u.preferredRegions || []).indexOf(el.value) >= 0;
      });
    }

    function openModal(open) {
      if (!editModal) return;
      editModal.classList.toggle("is-open", open);
      if (open) fillEdit();
    }

    if (openEdit) openEdit.addEventListener("click", function () { openModal(true); });
    if (location.hash === "#edit-profile") openModal(true);
    if (closeEdit) closeEdit.addEventListener("click", function () { openModal(false); });
    if (editModal) {
      editModal.addEventListener("click", function (e) {
        if (e.target === editModal) openModal(false);
      });
    }

    if (editForm) {
      editForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const u = getUser();
        u.name = $("#edit-name").value.trim() || u.name;
        u.birthDate = $("#edit-birth").value || u.birthDate;
        if (u.birthDate) u.age = Math.max(0, today().getFullYear() - Number(u.birthDate.split("-")[0]));
        const t = $('input[name="editUserType"]:checked');
        if (t) u.userType = t.value;
        u.interests = $$('input[name="editInterest"]:checked').map((el) => el.value);
        const custom = ($("#edit-custom-interest") && $("#edit-custom-interest").value.trim()) || "";
        if (u.interests.indexOf("기타") >= 0 && !custom) {
          showToast("기타 관심 분야를 직접 입력해 주세요");
          $("#edit-custom-interest").focus();
          return;
        }
        if (custom) u.interests.push(custom);
        u.preferredRegions = $$('input[name="editRegion"]:checked').map((el) => el.value);
        try {
          setUser(toFrontendUser(await window.DiDimAPI.putUserProfile(toBackendProfile(u))));
          showToast("프로필을 수정했어요");
          openModal(false);
          setTimeout(function () { location.reload(); }, 400);
        } catch (error) {
          showToast(error.message);
        }
      });
    }
  }

  /* ---------- Boot ---------- */
  function enhanceChipSelects() {
    $$(".chip-select label").forEach(function (label) {
      const input = label.querySelector("input");
      if (!input) return;
      function sync() {
        label.classList.toggle("is-checked", input.checked);
      }
      input.addEventListener("change", function () {
        if (input.type === "radio") {
          $$(`input[name="${input.name}"]`).forEach(function (r) {
            const lab = r.closest("label");
            if (lab) lab.classList.toggle("is-checked", r.checked);
          });
        } else sync();
      });
      sync();
    });
  }

  async function hydrateBackendState() {
    await window.DiDimAPI.ready;
    const firebaseUser = await window.DiDimAPI.currentUser().catch(function () { return null; });
    if (firebaseUser) localStorage.setItem(STORAGE.loggedIn, "1");
    if (isLoggedIn()) {
      try {
        setUser(toFrontendUser(await window.DiDimAPI.getUserProfile()));
      } catch (error) {
        if (error.status !== 404) console.warn("프로필을 동기화하지 못했습니다.");
      }
      try {
        const savedResult = await window.DiDimAPI.saved("all", "saved_at");
        setSavedIds(savedResult.items.map((item) => String(item.id)));
      } catch (error) {
        console.warn("저장 목록을 동기화하지 못했습니다.");
      }
    }
    const page = document.body.dataset.page;
    if (page === "home" || page === "mypage") {
      try {
        PROGRAMS = (await window.DiDimAPI.listOpportunities({ page_size: 100 })).items;
      } catch (error) {
        PROGRAMS = [];
      }
    }
  }

  document.addEventListener("DOMContentLoaded", async function () {
    await hydrateBackendState();
    setActiveNav();
    bindSaveButtons(document);
    enhanceChipSelects();
    initMobileNav();
    initNotifUI();
    initHome();
    initPrograms();
    initDetail();
    initRecommend();
    initSaved();
    initLogin();
    initSignup();
    initMyPage();
  });

  window.DiDim = {
    INTERESTS: INTERESTS,
    REGIONS: REGIONS,
    METHODS: METHODS,
  };
  Object.defineProperty(window.DiDim, "PROGRAMS", { get: function () { return PROGRAMS; } });
})();
