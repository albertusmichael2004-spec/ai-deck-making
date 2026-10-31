// Webview UI: slides with clickable object boxes, drag-to-mark regions and an
// annotation sidebar. All persistence happens in the extension via the Studio CLI.
(function () {
  const vscode = acquireVsCodeApi();
  const app = document.getElementById("app");
  const DRAG_THRESHOLD = 6;
  const state = { preview: null, annotations: [], selection: null, showBoxes: false, status: "", error: false, busy: false };

  function element(tag, attributes, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attributes || {})) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children || []) if (child) node.appendChild(child);
    return node;
  }

  function place(node, box) {
    node.style.left = box.x * 100 + "%";
    node.style.top = box.y * 100 + "%";
    node.style.width = box.width * 100 + "%";
    node.style.height = box.height * 100 + "%";
  }

  function point(event, frame) {
    const rect = frame.getBoundingClientRect();
    return { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height };
  }

  // Background shapes cover whole slides, so a click picks the smallest box under the cursor.
  function objectAt(slide, at) {
    const hits = slide.objects.filter((o) => at.x >= o.box.x && at.x <= o.box.x + o.box.width && at.y >= o.box.y && at.y <= o.box.y + o.box.height);
    hits.sort((a, b) => a.box.width * a.box.height - b.box.width * b.box.height);
    return hits[0] || null;
  }

  // A marked area selects objects mostly inside it, or a (non-background) object
  // that mostly contains it; boxes merely grazed by the drag are ignored.
  function intersecting(slide, region) {
    const regionArea = region.width * region.height;
    return slide.objects.filter((o) => {
      const width = Math.min(o.box.x + o.box.width, region.x + region.width) - Math.max(o.box.x, region.x);
      const height = Math.min(o.box.y + o.box.height, region.y + region.height) - Math.max(o.box.y, region.y);
      if (width <= 0 || height <= 0) return false;
      const overlap = width * height;
      const area = o.box.width * o.box.height;
      return overlap / area >= 0.3 || (overlap / regionArea >= 0.6 && area < 0.5);
    });
  }

  function select(slide, objectIds, region, additive) {
    const same = state.selection && state.selection.slideId === slide.slide_id;
    let ids = objectIds;
    if (additive && same) {
      const current = new Set(state.selection.objectIds);
      for (const id of objectIds) current.has(id) ? current.delete(id) : current.add(id);
      ids = [...current];
    }
    state.selection = ids.length || region ? { slideId: slide.slide_id, slideIndex: slide.index, objectIds: ids, region: region || (same && additive ? state.selection.region : null) } : null;
    render();
    const input = document.getElementById("note");
    if (input) input.focus();
  }

  function slideView(slide) {
    const frame = element("div", { class: "frame" }, [element("img", { src: slide.src, alt: "Slide " + slide.index, draggable: "false" })]);
    const selected = state.selection && state.selection.slideId === slide.slide_id ? new Set(state.selection.objectIds) : new Set();
    const hover = element("div", { class: "box hover hidden" });
    const tip = element("div", { class: "tip hidden" });
    for (const obj of slide.objects) {
      if (!state.showBoxes && !selected.has(obj.object_id)) continue;
      const box = element("div", { class: "box" + (selected.has(obj.object_id) ? " selected" : "") });
      place(box, obj.box);
      frame.appendChild(box);
    }
    if (state.selection && state.selection.slideId === slide.slide_id && state.selection.region) {
      const [x, y, width, height] = state.selection.region;
      const region = element("div", { class: "region" });
      place(region, { x, y, width, height });
      frame.appendChild(region);
    }
    state.annotations.forEach((note, number) => {
      if (note.slide_id !== slide.slide_id) return;
      const obj = slide.objects.find((o) => note.object_ids.includes(o.object_id));
      const anchor = obj ? obj.box : note.region ? { x: note.region[0], y: note.region[1] } : { x: 0, y: 0 };
      const pin = element("div", { class: "pin", text: String(number + 1), title: note.text });
      pin.style.left = anchor.x * 100 + "%";
      pin.style.top = anchor.y * 100 + "%";
      frame.appendChild(pin);
    });
    frame.appendChild(hover);
    frame.appendChild(tip);

    let start = null;
    let drag = null;
    const finish = (event) => {
      if (!start) return;
      const at = point(event, frame);
      const additive = event.shiftKey || event.ctrlKey || event.metaKey;
      if (drag) {
        const region = { x: Math.max(0, Math.min(start.x, at.x)), y: Math.max(0, Math.min(start.y, at.y)), width: Math.abs(at.x - start.x), height: Math.abs(at.y - start.y) };
        start = drag = null;
        select(slide, intersecting(slide, region).map((o) => o.object_id), [region.x, region.y, region.width, region.height], additive);
      } else {
        start = null;
        const obj = objectAt(slide, at);
        if (obj) select(slide, [obj.object_id], null, additive);
      }
    };
    frame.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      start = point(event, frame);
      start.clientX = event.clientX;
      start.clientY = event.clientY;
      window.addEventListener("mouseup", finish, { once: true });
    });
    frame.addEventListener("mousemove", (event) => {
      const at = point(event, frame);
      if (start && Math.hypot(event.clientX - start.clientX, event.clientY - start.clientY) > DRAG_THRESHOLD) {
        if (!drag) { drag = element("div", { class: "region drawing" }); frame.appendChild(drag); }
        place(drag, { x: Math.min(start.x, at.x), y: Math.min(start.y, at.y), width: Math.abs(at.x - start.x), height: Math.abs(at.y - start.y) });
        hover.classList.add("hidden");
        tip.classList.add("hidden");
        return;
      }
      const obj = objectAt(slide, at);
      hover.classList.toggle("hidden", !obj);
      tip.classList.toggle("hidden", !obj);
      if (obj) {
        place(hover, obj.box);
        tip.textContent = obj.kind + (obj.label ? ": " + obj.label : "");
        tip.style.left = Math.min(at.x, 0.7) * 100 + "%";
        tip.style.top = (at.y + 0.04) * 100 + "%";
      }
    });
    frame.addEventListener("mouseleave", () => { hover.classList.add("hidden"); tip.classList.add("hidden"); });
    return element("section", { class: "slide" }, [element("div", { class: "slide-label", text: "Slide " + slide.index }), frame]);
  }

  function selectionPanel() {
    if (!state.selection) return element("p", { class: "hint", text: "Click an object on a slide, or drag a box around an area. Shift/Ctrl+click adds objects." });
    const slide = state.preview.slides.find((s) => s.slide_id === state.selection.slideId);
    const labels = state.selection.objectIds.map((id) => {
      const obj = slide.objects.find((o) => o.object_id === id);
      return element("li", { text: obj.kind + (obj.label ? " — " + obj.label : "") });
    });
    const note = element("textarea", { id: "note", rows: "5", placeholder: "What should change here? (Ctrl+Enter to save)" });
    const save = () => {
      const text = note.value.trim();
      if (!text) return note.focus();
      vscode.postMessage({ type: "save", slideId: state.selection.slideId, objectIds: state.selection.objectIds, region: state.selection.region, text });
    };
    note.addEventListener("keydown", (event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) save(); });
    return element("div", {}, [
      element("h3", { text: "Slide " + state.selection.slideIndex + " · " + (labels.length || "no") + " object(s)" }),
      labels.length ? element("ul", { class: "targets" }, labels) : element("p", { class: "warn", text: "This area has no objects. Add objects so the revision has a target." }),
      note,
      element("div", { class: "row" }, [
        element("button", { text: "Save annotation", onclick: save }),
        element("button", { class: "secondary", text: "Clear", onclick: () => { state.selection = null; render(); } }),
      ]),
    ]);
  }

  function annotationList() {
    if (!state.annotations.length) return element("p", { class: "hint", text: "No pending annotations." });
    const items = state.annotations.map((note, number) => element("li", { class: "note" }, [
      element("div", { class: "note-head", text: "#" + (number + 1) + " · slide " + note.slide_index }),
      element("div", { class: "note-text", text: note.text }),
      element("div", { class: "row" }, [
        element("button", { class: "secondary small", text: "Done", onclick: () => vscode.postMessage({ type: "mark", status: "done", ids: [note.annotation_id] }) }),
        element("button", { class: "secondary small", text: "Dismiss", onclick: () => vscode.postMessage({ type: "mark", status: "dismissed", ids: [note.annotation_id] }) }),
      ]),
    ]));
    return element("div", {}, [
      element("ol", { class: "notes" }, items),
      element("button", { text: "Copy revision request for AI", onclick: () => vscode.postMessage({ type: "copyRequest" }) }),
    ]);
  }

  function render() {
    app.replaceChildren();
    const header = element("header", {}, [
      element("div", { class: "title", text: state.preview ? state.preview.project_id : "Deck Preview" }),
      element("label", { class: "toggle" }, [
        Object.assign(element("input", { type: "checkbox", onchange: (event) => { state.showBoxes = event.target.checked; render(); } }), { checked: state.showBoxes }),
        document.createTextNode(" Show object boxes"),
      ]),
      element("button", { class: "secondary", text: "Re-render", onclick: () => vscode.postMessage({ type: "refresh" }) }),
    ]);
    const status = state.status ? element("div", { class: "status" + (state.error ? " error" : "") + (state.busy ? " busy" : ""), text: state.status }) : null;
    const slides = element("main", {}, state.preview ? state.preview.slides.map(slideView) : []);
    const meta = state.preview ? element("p", { class: "hint", text: "Deck " + state.preview.sha256.slice(0, 10) + " · rendered " + new Date(state.preview.generated_at).toLocaleString() + ". Updates automatically when the working deck changes." }) : null;
    const side = element("aside", {}, [element("h2", { text: "Annotate" }), selectionPanel(), element("h2", { text: "Pending" }), annotationList(), meta]);
    app.appendChild(header);
    if (status) app.appendChild(status);
    app.appendChild(element("div", { class: "layout" }, [slides, side]));
  }

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "status") Object.assign(state, { status: message.text, error: !!message.error, busy: !!message.busy });
    if (message.type === "preview") {
      Object.assign(state, { preview: message.preview, status: "", error: false, busy: false });
      if (state.selection && !message.preview.slides.some((s) => s.slide_id === state.selection.slideId)) state.selection = null;
    }
    if (message.type === "annotations") state.annotations = message.annotations;
    if (message.type === "saved") state.selection = null;
    render();
  });
  render();
})();
