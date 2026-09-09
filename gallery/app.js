(() => {
  "use strict";

  const state = {
    collections: [],
    collection: null,
    images: [],
    memo: "",
    filtered: [],
    lightboxIndex: -1,
    toastTimer: null,
  };
  const SORT_STORAGE_KEY = "pin-archive-sort-order";
  const SORT_VALUES = new Set(["newest", "oldest", "name"]);
  const $ = (selector) => document.querySelector(selector);

  function getSavedSort(collectionId) {
    const collection = collectionById(collectionId);
    if (collection && SORT_VALUES.has(collection.sort)) return collection.sort;
    try {
      const preferences = JSON.parse(localStorage.getItem(SORT_STORAGE_KEY) || "{}");
      const value = preferences && preferences[collectionId];
      return SORT_VALUES.has(value) ? value : "newest";
    } catch {
      return "newest";
    }
  }

  function saveSort(collectionId, value) {
    if (!collectionId || !SORT_VALUES.has(value)) return;
    const collection = collectionById(collectionId);
    if (collection) collection.sort = value;
    try {
      const preferences = JSON.parse(localStorage.getItem(SORT_STORAGE_KEY) || "{}");
      const nextPreferences = preferences && typeof preferences === "object" && !Array.isArray(preferences)
        ? preferences
        : {};
      nextPreferences[collectionId] = value;
      localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify(nextPreferences));
    } catch {
      // localStorage が使えない環境でも、表示自体は継続する。
    }
    fetch("/api/preferences/sort", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection: collectionId, sort: value }),
      keepalive: true,
    }).catch(() => {
      // サーバー保存に失敗しても、ブラウザ側の保存値で表示を継続する。
    });
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function showToast(message, kind = "success") {
    const toast = $("#gallery-toast");
    if (!toast) return;
    window.clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.dataset.kind = kind;
    toast.hidden = false;
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 3200);
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character]);
  }

  function setActiveCollection(collectionId) {
    document.querySelectorAll("[data-collection-link]").forEach((link) => {
      if (link.dataset.collectionLink === collectionId) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function collectionById(collectionId) {
    return state.collections.find((collection) => collection.id === collectionId) || null;
  }

  async function fetchCollections() {
    const response = await fetch("/api/collections");
    if (!response.ok) throw new Error("コレクション一覧を取得できませんでした。");
    return (await response.json()).collections || [];
  }

  async function fetchImages(collectionId) {
    const response = await fetch(`/api/images?collection=${encodeURIComponent(collectionId)}`);
    if (!response.ok) throw new Error("画像一覧を取得できませんでした。");
    const payload = await response.json();
    return { images: payload.images || [], memo: payload.memo || "" };
  }

  function makePreview(image, collectionId, className = "") {
    const img = document.createElement("img");
    img.className = className;
    img.src = `/media/${encodeURIComponent(collectionId)}/${encodeURIComponent(image.name)}`;
    img.alt = image.name;
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", () => img.remove());
    return img;
  }

  function renderNavigation() {
    const nav = $("#collection-nav");
    nav.replaceChildren();
    state.collections.forEach((collection) => {
      const link = document.createElement("a");
      link.href = `/${encodeURIComponent(collection.id)}`;
      link.dataset.collectionLink = collection.id;
      link.textContent = collection.label;
      nav.append(link);
    });
  }

  async function syncCollectionsFromUi() {
    const button = $("#sync-collections");
    const status = $("#sync-status");
    button.disabled = true;
    button.classList.add("is-busy");
    status.textContent = "Arts/ を確認しています…";
    try {
      const response = await fetch("/api/sync-collections", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "フォルダを更新できませんでした。");

      state.collections = await fetchCollections();
      renderNavigation();
      renderHome();
      const addedCount = Number(payload.addedCount || 0);
      status.textContent = addedCount
        ? `${addedCount}件のフォルダを追加しました。`
        : "新しいフォルダはありません。";
    } catch (error) {
      status.textContent = error.message || "フォルダを更新できませんでした。";
    } finally {
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }

  function renderHome() {
    state.collection = null;
    state.images = [];
    state.filtered = [];
    $("#home-view").hidden = false;
    $("#gallery-view").hidden = true;
    setActiveCollection(null);
    const cardRoot = $("#folder-cards");
    cardRoot.replaceChildren();
    if (!state.collections.length) {
      cardRoot.innerHTML = '<div class="loading-card">表示できるコレクションがありません。</div>';
      return;
    }
    state.collections.forEach((collection) => {
      const card = document.createElement("a");
      card.className = "folder-card";
      card.dataset.collection = collection.id;
      card.dataset.accent = collection.accent || "coral";
      card.href = `/${encodeURIComponent(collection.id)}`;
      const top = document.createElement("div");
      top.className = "folder-card-top";
      top.innerHTML = `<h2>${escapeHtml(collection.label)}</h2><span class="count">${collection.count} images</span>`;
      const preview = document.createElement("div");
      preview.className = "preview-stack";
      (collection.previews || []).forEach((image) => preview.append(makePreview(image, collection.id)));
      if (!collection.count) preview.insertAdjacentHTML("beforeend", '<span class="preview-placeholder">＋</span>');
      const bottom = document.createElement("div");
      bottom.className = "folder-card-bottom";
      bottom.innerHTML = `<div class="folder-card-copy"><p>${escapeHtml(collection.description || "ローカル画像コレクション")}</p></div><span class="folder-arrow" aria-hidden="true">↗</span>`;
      card.append(top, preview, bottom);
      cardRoot.append(card);
    });
  }

  function sortImages(images, sort) {
    return [...images].sort((left, right) => {
      if (sort === "oldest") return left.modified - right.modified;
      if (sort === "name") return left.name.localeCompare(right.name, "ja");
      return right.modified - left.modified;
    });
  }

  function renderMemo(memo) {
    const container = $("#collection-memo");
    container.replaceChildren();
    const normalized = String(memo || "").replace(/\r\n?/g, "\n").trim();
    if (!normalized) {
      container.hidden = true;
      return;
    }

    const kicker = document.createElement("p");
    kicker.className = "memo-kicker";
    kicker.textContent = "MEMO";
    container.append(kicker);

    let paragraphLines = [];
    let list = null;
    const flushParagraph = () => {
      if (!paragraphLines.length) return;
      const paragraph = document.createElement("p");
      paragraph.className = "memo-paragraph";
      paragraph.textContent = paragraphLines.join("\n");
      container.append(paragraph);
      paragraphLines = [];
    };
    const closeList = () => {
      if (!list) return;
      container.append(list);
      list = null;
    };

    normalized.split("\n").forEach((line) => {
      const heading = line.match(/^#{1,3}\s+(.+)$/);
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      if (!line.trim()) {
        flushParagraph();
        closeList();
      } else if (heading) {
        flushParagraph();
        closeList();
        const title = document.createElement("h2");
        title.className = "memo-heading";
        title.textContent = heading[1].trim();
        container.append(title);
      } else if (bullet) {
        flushParagraph();
        if (!list) {
          list = document.createElement("ul");
          list.className = "memo-list";
        }
        const item = document.createElement("li");
        item.textContent = bullet[1].trim();
        list.append(item);
      } else {
        closeList();
        paragraphLines.push(line.trim());
      }
    });
    flushParagraph();
    closeList();
    container.hidden = container.childElementCount <= 1;
  }

  async function deleteImage(image, card) {
    if (!state.collection || !window.confirm(`「${image.name}」をゴミ箱へ移動しますか？`)) return;
    const button = card.querySelector(".pin-card-delete");
    if (button) button.disabled = true;
    card.classList.add("is-deleting");
    try {
      const response = await fetch("/api/images/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collection: state.collection.id, filename: image.name }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "画像をゴミ箱へ移動できませんでした。");
      state.images = state.images.filter((candidate) => candidate.name !== image.name);
      renderGallery();
      showToast("ゴミ箱へ移動しました");
    } catch (error) {
      card.classList.remove("is-deleting");
      if (button) button.disabled = false;
      showToast(error.message || "画像をゴミ箱へ移動できませんでした。", "error");
    }
  }

  function renderGallery() {
    const query = $("#search-input").value.trim().toLocaleLowerCase("ja");
    const sort = $("#sort-select").value;
    state.filtered = sortImages(
      state.images.filter((image) => image.name.toLocaleLowerCase("ja").includes(query)),
      sort,
    );
    const grid = $("#gallery-grid");
    grid.dataset.sort = sort;
    grid.replaceChildren();
    $("#image-count").textContent = state.filtered.length;
    $("#empty-state").hidden = state.filtered.length !== 0;

    state.filtered.forEach((image, index) => {
      const card = document.createElement("article");
      card.className = "pin-card";
      const openButton = document.createElement("button");
      openButton.className = "pin-card-open";
      openButton.type = "button";
      openButton.setAttribute("aria-label", `${image.name}を拡大表示`);
      openButton.addEventListener("click", () => openLightbox(index));
      const media = document.createElement("span");
      media.className = "pin-card-media";
      const img = makePreview(image, state.collection.id);
      const overlay = document.createElement("span");
      overlay.className = "pin-card-overlay";
      overlay.innerHTML = `<span class="pin-card-name">${escapeHtml(image.name)}</span>`;
      media.append(img, overlay);
      openButton.append(media);
      const deleteButton = document.createElement("button");
      deleteButton.className = "pin-card-delete";
      deleteButton.type = "button";
      deleteButton.setAttribute("aria-label", `${image.name}をゴミ箱へ移動`);
      deleteButton.title = "ゴミ箱へ移動";
      deleteButton.innerHTML = "<span aria-hidden=\"true\">⌫</span><span class=\"sr-only\">ゴミ箱へ移動</span>";
      deleteButton.addEventListener("click", () => deleteImage(image, card));
      card.append(openButton, deleteButton);
      grid.append(card);
    });
  }

  async function renderGalleryPage(collectionId) {
    const collection = collectionById(collectionId);
    if (!collection) {
      renderHome();
      return;
    }
    state.collection = collection;
    $("#home-view").hidden = true;
    $("#gallery-view").hidden = false;
    const galleryTitle = $("#gallery-title");
    galleryTitle.textContent = collection.label;
    galleryTitle.classList.toggle("is-long", collection.label.length > 18);
    $("#sort-select").value = getSavedSort(collection.id);
    $("#gallery-eyebrow").textContent = `LOCAL COLLECTION · ${collection.id.toUpperCase()}`;
    setActiveCollection(collection.id);
    state.memo = "";
    renderMemo("");
    $("#gallery-grid").innerHTML = '<div class="loading-card"><span class="loader"></span> 画像を並べています…</div>';
    try {
      const payload = await fetchImages(collection.id);
      state.images = payload.images;
      state.memo = payload.memo;
      renderMemo(state.memo);
      renderGallery();
    } catch (error) {
      state.images = [];
      state.memo = "";
      renderMemo("");
      $("#gallery-grid").innerHTML = `<div class="loading-card">${escapeHtml(error.message)}</div>`;
    }
  }

  function openLightbox(index) {
    if (index < 0 || index >= state.filtered.length || !state.collection) return;
    state.lightboxIndex = index;
    const image = state.filtered[index];
    const lightboxImage = $("#lightbox-image");
    lightboxImage.src = `/media/${encodeURIComponent(state.collection.id)}/${encodeURIComponent(image.name)}`;
    lightboxImage.alt = image.name;
    $("#lightbox-caption").textContent = `${image.name} · ${formatBytes(image.size)}`;
    $("#lightbox-prev").disabled = index === 0;
    $("#lightbox-next").disabled = index === state.filtered.length - 1;
    $("#lightbox").hidden = false;
    document.body.classList.add("modal-open");
    $("#lightbox-close").focus();
  }

  function closeLightbox() {
    $("#lightbox").hidden = true;
    document.body.classList.remove("modal-open");
    $("#lightbox-image").removeAttribute("src");
    state.lightboxIndex = -1;
  }

  function moveLightbox(delta) {
    const next = state.lightboxIndex + delta;
    if (next >= 0 && next < state.filtered.length) openLightbox(next);
  }

  async function init() {
    $("#sync-collections").addEventListener("click", syncCollectionsFromUi);
    $("#search-input").addEventListener("input", renderGallery);
    $("#sort-select").addEventListener("change", () => {
      if (state.collection) saveSort(state.collection.id, $("#sort-select").value);
      renderGallery();
    });
    $("#lightbox-close").addEventListener("click", closeLightbox);
    $("#lightbox-prev").addEventListener("click", () => moveLightbox(-1));
    $("#lightbox-next").addEventListener("click", () => moveLightbox(1));
    $("#lightbox").addEventListener("click", (event) => {
      if (event.target === $("#lightbox")) closeLightbox();
    });
    document.addEventListener("keydown", (event) => {
      if ($("#lightbox").hidden) return;
      if (event.key === "Escape") closeLightbox();
      if (event.key === "ArrowLeft") moveLightbox(-1);
      if (event.key === "ArrowRight") moveLightbox(1);
    });

    try {
      state.collections = await fetchCollections();
      renderNavigation();
      const collectionId = location.pathname.replace(/^\//, "").replace(/\/$/, "");
      if (collectionId) await renderGalleryPage(collectionId);
      else renderHome();
    } catch (error) {
      $("#folder-cards").innerHTML = `<div class="loading-card">${escapeHtml(error.message)}</div>`;
    }
  }

  init();
})();
