// Editor: debounced server-side live preview, image upload (button + paste),
// and a fullscreen toggle.
(function () {
  const body = document.getElementById("body");
  const preview = document.getElementById("preview");
  const imageInput = document.getElementById("image-input");
  const uploadStatus = document.getElementById("upload-status");
  const fsToggle = document.getElementById("fullscreen-toggle");
  const metaToggle = document.getElementById("meta-toggle");
  const metaFields = document.getElementById("meta-fields");
  const root = document.getElementById("editor-root");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  let timer = null;

  async function renderPreview() {
    const data = new FormData();
    data.append("body", body.value);
    try {
      const res = await fetch("/admin/preview", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: data,
      });
      preview.innerHTML = await res.text();
    } catch (e) {
      preview.textContent = "Preview unavailable.";
    }
  }

  function schedulePreview() {
    clearTimeout(timer);
    timer = setTimeout(renderPreview, 250);
  }

  function insertAtCursor(text) {
    const start = body.selectionStart;
    const end = body.selectionEnd;
    body.value = body.value.slice(0, start) + text + body.value.slice(end);
    body.selectionStart = body.selectionEnd = start + text.length;
    body.focus();
    schedulePreview();
  }

  // Shared upload used by the button and by paste. Inserts an image at the
  // cursor on success so the writer can place images anywhere in the post.
  async function uploadAndInsert(file) {
    uploadStatus.textContent = "…";
    const data = new FormData();
    data.append("file", file);
    try {
      const res = await fetch("/admin/upload", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: data,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        uploadStatus.textContent = "Upload failed: " + (err.detail || res.status);
        return;
      }
      const { url } = await res.json();
      const alt = (file.name || "image").replace(/\]/g, "");
      insertAtCursor(`\n![${alt}](${url})\n`);
      uploadStatus.textContent = "✓";
    } catch (e) {
      uploadStatus.textContent = "Upload failed.";
    }
  }

  // Keep the textarea and the preview scrolled to the same relative position so
  // the two panes track each other. Proportional (not line-exact) but matches
  // closely for typical posts.
  //
  // Only the pane the user is actively driving (pointer over it, or focused)
  // pushes scroll to the other. Without this gate Safari self-scrolls: it
  // coalesces scroll events and dispatches the programmatic one a frame late —
  // after a rAF-released lock — so the two panes feed each other in a loop the
  // user can't stop. activePane breaks the loop regardless of lock timing.
  let activePane = null;
  let scrollLock = false;
  function linkScroll(src, dst) {
    src.addEventListener("scroll", function () {
      if (scrollLock || activePane !== src) return;
      const srcMax = src.scrollHeight - src.clientHeight;
      if (srcMax <= 0) return;
      const dstMax = dst.scrollHeight - dst.clientHeight;
      scrollLock = true;
      dst.scrollTop = (src.scrollTop / srcMax) * dstMax;
      requestAnimationFrame(function () {
        scrollLock = false;
      });
    });
    function claim() { activePane = src; }
    src.addEventListener("pointerenter", claim);
    src.addEventListener("focus", claim, true);
    src.addEventListener("touchstart", claim, { passive: true });
  }

  if (body && preview) {
    body.addEventListener("input", schedulePreview);
    renderPreview();
    linkScroll(body, preview);
    linkScroll(preview, body);

    // Ctrl/Cmd+V of an image anywhere in the body uploads + inserts it inline.
    body.addEventListener("paste", function (ev) {
      const items = (ev.clipboardData || window.clipboardData).items || [];
      for (const item of items) {
        if (item.kind === "file" && item.type.startsWith("image/")) {
          const file = item.getAsFile();
          if (file) {
            ev.preventDefault();
            uploadAndInsert(file);
            return;
          }
        }
      }
    });
  }

  if (imageInput) {
    imageInput.addEventListener("change", function () {
      const file = imageInput.files[0];
      if (file) uploadAndInsert(file);
      imageInput.value = "";
    });
  }

  function setMetaCollapsed(collapsed) {
    if (!metaFields || !metaToggle) return;
    metaFields.classList.toggle("collapsed", collapsed);
    metaToggle.textContent = collapsed ? metaToggle.dataset.show : metaToggle.dataset.hide;
  }

  if (metaToggle && metaFields) {
    metaToggle.addEventListener("click", function () {
      setMetaCollapsed(!metaFields.classList.contains("collapsed"));
    });
  }

  if (fsToggle && root) {
    fsToggle.addEventListener("click", function () {
      const on = root.classList.toggle("fullscreen");
      document.body.classList.toggle("editor-fullscreen", on);
      fsToggle.textContent = on ? fsToggle.dataset.off : fsToggle.dataset.on;
      // Maximize writing space: collapse the meta fields on entering fullscreen,
      // restore them on exit.
      setMetaCollapsed(on);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && root.classList.contains("fullscreen")) {
        fsToggle.click();
      }
    });
  }

  // --- Autosave (per-device, localStorage) ---------------------------------
  // Drafts persist on THIS browser so an accidental tab close / crash doesn't
  // lose work. Not a sync — it won't follow you to another machine, and Save
  // is still what writes the post. Cleared on submit.
  const form = document.getElementById("post-form");
  const titleEl = document.getElementById("title");
  const tagsEl = document.getElementById("tags");
  const publishEl = document.getElementById("publish_at");
  const draftEl = document.getElementById("draft");
  const saveStatus = document.getElementById("autosave-status");
  const restoreBar = document.getElementById("restore-bar");
  const restoreBtn = document.getElementById("restore-draft");
  const discardBtn = document.getElementById("discard-draft");
  const autosaveKey = form ? "goggy-autosave:" + (form.dataset.slug || "new") : null;

  function collectDraft() {
    return {
      title: titleEl ? titleEl.value : "",
      tags: tagsEl ? tagsEl.value : "",
      body: body ? body.value : "",
      publish_at: publishEl ? publishEl.value : "",
      draft: draftEl ? draftEl.checked : false,
      at: Date.now(),
    };
  }

  function applyDraft(d) {
    if (titleEl && typeof d.title === "string") titleEl.value = d.title;
    if (tagsEl && typeof d.tags === "string") tagsEl.value = d.tags;
    if (body && typeof d.body === "string") body.value = d.body;
    if (publishEl && typeof d.publish_at === "string") publishEl.value = d.publish_at;
    if (draftEl && typeof d.draft === "boolean") draftEl.checked = d.draft;
    schedulePreview();
  }

  function saveDraft() {
    if (!autosaveKey) return;
    try {
      localStorage.setItem(autosaveKey, JSON.stringify(collectDraft()));
      if (saveStatus) saveStatus.textContent = saveStatus.dataset.saved || "";
    } catch (e) {}
  }

  function clearDraft() {
    if (!autosaveKey) return;
    try { localStorage.removeItem(autosaveKey); } catch (e) {}
  }

  let saveTimer = null;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 800);
  }

  if (autosaveKey) {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(autosaveKey)); } catch (e) {}

    // Offer restore only when the stored draft actually differs from what the
    // server rendered into the form — no banner on every clean load.
    if (
      saved &&
      restoreBar &&
      (saved.title !== (titleEl ? titleEl.value : "") ||
        saved.tags !== (tagsEl ? tagsEl.value : "") ||
        saved.body !== (body ? body.value : "") ||
        saved.publish_at !== (publishEl ? publishEl.value : "") ||
        saved.draft !== (draftEl ? draftEl.checked : false))
    ) {
      restoreBar.hidden = false;
      if (restoreBtn) restoreBtn.addEventListener("click", function () {
        applyDraft(saved);
        restoreBar.hidden = true;
      });
      if (discardBtn) discardBtn.addEventListener("click", function () {
        clearDraft();
        restoreBar.hidden = true;
      });
    }

    [titleEl, tagsEl, body, publishEl].forEach(function (el) {
      if (el) el.addEventListener("input", scheduleSave);
    });
    if (draftEl) draftEl.addEventListener("change", scheduleSave);
    if (form) form.addEventListener("submit", clearDraft);
  }
})();
