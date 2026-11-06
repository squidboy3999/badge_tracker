let appState = {
  user_id: "",
  selected_category: "all",
  available_users: [],
  available_categories: [],
  trees: [],
  notes: {}
};

let selectedGoalId = null;
let nodeIndex = {};
let categoryLabelMap = {};
let collapsedIds = new Set(JSON.parse(localStorage.getItem("badge_collapsed_ids") || "[]"));

function persistCollapsed() {
  localStorage.setItem("badge_collapsed_ids", JSON.stringify([...collapsedIds]));
}

function toggleCollapse(id, event) {
  if (event) event.stopPropagation();
  if (collapsedIds.has(id)) {
    collapsedIds.delete(id);
  } else {
    collapsedIds.add(id);
  }
  persistCollapsed();
  renderTrees();
  renderInspector();
}

function expandAll() {
  collapsedIds.clear();
  persistCollapsed();
  renderTrees();
  renderInspector();
}

function collapseBranchesOnly() {
  collapsedIds.clear();
  appState.trees.forEach(root => {
    (root.children || []).forEach(branch => {
      if (!branch.is_leaf) collapsedIds.add(branch.id);
    });
  });
  persistCollapsed();
  renderTrees();
  renderInspector();
}

function collapseAllRoots() {
  appState.trees.forEach(root => {
    if (!root.is_leaf) collapsedIds.add(root.id);
  });
  persistCollapsed();
  renderTrees();
  renderInspector();
}

function badgeUrl(node) {
  const dir = encodeURIComponent(node.badge_dir || "default");
  const file = encodeURIComponent(node.badge || "default.png");
  return `/badges/${dir}/${file}`;
}

async function fetchTrees() {
  const params = new URLSearchParams();
  if (appState.user_id) params.set("user_id", appState.user_id);
  params.set("category", appState.selected_category || "all");

  const res = await fetch(`/api/trees?${params.toString()}`);
  appState = await res.json();

  categoryLabelMap = {};
  (appState.available_categories || []).forEach(c => {
    categoryLabelMap[c.id] = c.label;
  });

  nodeIndex = {};
  appState.trees.forEach(t => indexNodes(t));
  if (!selectedGoalId || !nodeIndex[selectedGoalId]) {
    selectedGoalId = appState.trees.length > 0 ? appState.trees[0].id : null;
  }

  renderDropdowns();
  renderTrees();
  renderInspector();
}

function indexNodes(node) {
  nodeIndex[node.id] = node;
  (node.children || []).forEach(c => indexNodes(c));
}

function onUserChange(newUserId) {
  appState.user_id = newUserId;
  appState.selected_category = "all";
  selectedGoalId = null;
  fetchTrees();
}

function onCategoryChange(newCategory) {
  appState.selected_category = newCategory;
  selectedGoalId = null;
  fetchTrees();
}

function renderDropdowns() {
  const userSelect = document.getElementById("userSelect");
  const users = appState.available_users || [];
  userSelect.innerHTML = users.map(u => `
    <option value="${u.id}" ${u.id === appState.user_id ? "selected" : ""}>
      ${u.name}
    </option>
  `).join("");

  const activeUserObj = users.find(u => u.id === appState.user_id);
  const subtitle = document.getElementById("userSubtitle");
  if (activeUserObj && activeUserObj.description) {
    subtitle.textContent = `${activeUserObj.name} — ${activeUserObj.description}`;
  } else {
    subtitle.textContent = "Declarative YAML Skill Trees • Multi-Category Filtering";
  }

  const catSelect = document.getElementById("categorySelect");
  const cats = appState.available_categories || [];
  const allOption = `<option value="all" ${appState.selected_category === "all" ? "selected" : ""}>all (All Categories)</option>`;
  const catOptions = cats.map(c => `
    <option value="${c.id}" ${c.id === appState.selected_category ? "selected" : ""}>
      ${c.label} (${c.id})
    </option>
  `).join("");
  catSelect.innerHTML = allOption + catOptions;
}

function selectNode(id, event) {
  if (event) event.stopPropagation();
  selectedGoalId = id;
  renderTrees();
  renderInspector();
}

async function toggleLeaf(id, event) {
  if (event) event.stopPropagation();
  const res = await fetch(`/api/goals/${encodeURIComponent(id)}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: appState.user_id,
      category: appState.selected_category
    })
  });
  if (res.ok) {
    appState = await res.json();
    nodeIndex = {};
    appState.trees.forEach(t => indexNodes(t));
    renderTrees();
    renderInspector();
  }
}

async function setCount(id, newCount, event) {
  if (event) event.stopPropagation();
  const res = await fetch(`/api/goals/${encodeURIComponent(id)}/progress`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: appState.user_id,
      category: appState.selected_category,
      count: Number(newCount)
    })
  });
  if (res.ok) {
    appState = await res.json();
    nodeIndex = {};
    appState.trees.forEach(t => indexNodes(t));
    renderTrees();
    renderInspector();
  }
}

async function saveNote(id) {
  const noteText = document.getElementById("noteTextarea").value;
  const res = await fetch(`/api/goals/${encodeURIComponent(id)}/note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: appState.user_id,
      category: appState.selected_category,
      note: noteText
    })
  });
  if (res.ok) {
    appState = await res.json();
    renderInspector();
  }
}

function renderNode(node, isRoot = false) {
  const lockClass = node.completed ? "unlocked" : "locked";
  const selClass = node.id === selectedGoalId ? "selected" : "";
  const isCollapsed = collapsedIds.has(node.id);
  const childCount = (node.children || []).length;

  const collapseToggle = !node.is_leaf
    ? `<button class="collapse-btn" onclick="toggleCollapse('${node.id}', event)"
               title="${isCollapsed ? 'Expand sub-goals' : 'Collapse sub-goals'}">
         ${isCollapsed ? "▶" : "▼"}
       </button>`
    : `<span class="collapse-spacer">•</span>`;

  const ruleBadge = !node.is_leaf
    ? `<span class="pill rule-${node.rule}">${node.rule === "all" ? "Requires All" : "Requires Any"}</span>`
    : "";
  const doneBadge = node.completed ? `<span class="pill done">Unlocked</span>` : "";
  const foldedBadge = (!node.is_leaf && isCollapsed)
    ? `<span class="pill folded-info" onclick="toggleCollapse('${node.id}', event)">+${childCount} sub-goals folded</span>`
    : "";

  let actionControl = "";
  if (node.is_leaf && node.target === 1) {
    actionControl = `
      <input type="checkbox" ${node.completed ? "checked" : ""}
        onclick="toggleLeaf('${node.id}', event)"
        title="Toggle completion"
        style="width:18px;height:18px;cursor:pointer;accent-color:var(--success);" />`;
  } else if (node.is_leaf && node.target > 1) {
    actionControl = `
      <div style="display:flex;align-items:center;gap:0.4rem;" onclick="event.stopPropagation()">
        <button style="padding:0.15rem 0.5rem;background:#334155;color:var(--text);"
                onclick="setCount('${node.id}', ${node.current_count - 1}, event)">−</button>
        <div class="progress-wrap" style="width:78px;text-align:center;">
          <span style="font-size:0.75rem;font-weight:600;color:var(--text);">${node.current_count} / ${node.target}</span>
          <div class="progress-bar"><div class="progress-fill" style="width:${node.progress_pct}%"></div></div>
        </div>
        <button style="padding:0.15rem 0.5rem;"
                onclick="setCount('${node.id}', ${node.current_count + 1}, event)">+</button>
      </div>`;
  } else {
    actionControl = `
      <div class="progress-wrap">
        <span style="font-size:0.75rem;color:var(--muted);">${node.progress_completed}/${node.progress_total} (${node.progress_pct}%)</span>
        <div class="progress-bar"><div class="progress-fill" style="width:${node.progress_pct}%"></div></div>
      </div>`;
  }

  const childrenHtml = (node.children || []).map(c => renderNode(c, false)).join("");

  return `
    <div class="node ${isRoot ? 'root-node' : ''} ${lockClass}">
      <div class="node-row ${selClass}" onclick="selectNode('${node.id}', event)">
        ${collapseToggle}
        <img class="badge-icon" src="${badgeUrl(node)}" alt="${node.title}" />
        <div class="node-main">
          <div class="node-title-row">
            <span class="node-title">${node.title}</span>
            ${ruleBadge}
            ${doneBadge}
            ${foldedBadge}
          </div>
          <div class="node-desc">${node.description}</div>
        </div>
        ${actionControl}
      </div>
      ${!node.is_leaf ? `<div class="node-children ${isCollapsed ? 'collapsed' : ''}">${childrenHtml}</div>` : ""}
    </div>
  `;
}

function renderTrees() {
  const container = document.getElementById("treesContainer");
  if (!appState.trees || appState.trees.length === 0) {
    const resetBtn = appState.selected_category !== "all"
      ? `<button style="margin-top:0.85rem;" onclick="onCategoryChange('all')">Show All Categories</button>`
      : "";
    container.innerHTML = `
      <div class="empty-state">
        <h3 style="color:var(--text);margin-bottom:0.4rem;">
          No Goal Trees Match (${appState.user_id} • category: ${appState.selected_category})
        </h3>
        <p style="font-size:0.88rem;">
          Assign <code>users: [${appState.user_id}]</code> or tag <code>categories: [...]</code> inside <code>data/goals/*.yaml</code>.
        </p>
        ${resetBtn}
      </div>`;
    return;
  }

  container.innerHTML = appState.trees.map(tree => {
    const tagsHtml = (tree.categories || []).map(cid => `
      <span class="cat-tag" onclick="onCategoryChange('${cid}')" title="Filter by ${cid}">
        #${categoryLabelMap[cid] || cid}
      </span>
    `).join(" ");

    return `
      <div class="tree-card">
        <div class="tree-meta">
          <div>
            <span>Source: <code>data/goals/${tree.badge_dir}.yaml</code></span>
            <span style="margin-left:0.75rem;">Users: <strong>${(tree.users || []).join(", ") || "All"}</strong></span>
          </div>
          <div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
            ${tagsHtml || '<span style="opacity:0.6;">Uncategorized</span>'}
          </div>
        </div>
        ${renderNode(tree, true)}
      </div>
    `;
  }).join("");
}

function renderInspector() {
  const panel = document.getElementById("inspectorPanel");
  const node = nodeIndex[selectedGoalId];
  if (!node) {
    panel.innerHTML = `<p class="inspector-placeholder">Select any badge node to inspect tactical advice and log progress.</p>`;
    return;
  }

  const noteVal = (appState.notes && appState.notes[node.id]) || "";
  const statusText = node.completed
    ? `Unlocked on ${node.completed_at || "Derived"}`
    : `Locked • ${node.progress_completed} of ${node.progress_total} completed (${node.progress_pct}%)`;

  let actionControlHtml = "";
  if (node.is_leaf && node.target === 1) {
    actionControlHtml = `
      <button class="toggle-btn ${node.completed ? 'completed' : ''}" onclick="toggleLeaf('${node.id}')">
        ${node.completed ? "Mark as Incomplete" : "Complete & Claim Badge"}
      </button>`;
  } else if (node.is_leaf && node.target > 1) {
    actionControlHtml = `
      <div class="counter-panel">
        <div class="counter-header">
          <span style="font-size:0.82rem;color:var(--muted);font-weight:600;">Repetition Counter (${appState.user_id})</span>
          <span id="sliderLabel" style="font-size:0.95rem;font-weight:700;color:var(--accent);">${node.current_count} / ${node.target}</span>
        </div>
        <input type="range" min="0" max="${node.target}" value="${node.current_count}"
               style="width:100%;padding:0;cursor:pointer;accent-color:var(--accent);"
               oninput="document.getElementById('sliderLabel').innerText = this.value + ' / ${node.target}'"
               onchange="setCount('${node.id}', this.value)" />
        <div class="counter-actions">
          <button style="flex:1;background:#334155;color:var(--text);" onclick="setCount('${node.id}', ${node.current_count - 1})">−1 Rep</button>
          <button style="flex:1;" onclick="setCount('${node.id}', ${node.current_count + 1})">+1 Rep</button>
          <button style="flex:1;background:var(--success);color:#0f172a;" onclick="setCount('${node.id}', ${node.target})">Max (${node.target})</button>
        </div>
      </div>`;
  } else {
    const isFolded = collapsedIds.has(node.id);
    actionControlHtml = `
      <div style="font-size:0.8rem;color:var(--muted);text-align:center;margin-top:0.5rem;">
        Composite milestone (${node.rule.toUpperCase()} rule). Complete child goals to unlock automatically.
      </div>
      <button style="width:100%;margin-top:0.6rem;background:#334155;color:var(--text);"
              onclick="toggleCollapse('${node.id}')">
        ${isFolded ? "Expand Sub-Goals in Tree" : "Collapse Sub-Goals in Tree"}
      </button>`;
  }

  panel.innerHTML = `
    <div class="inspector-header">
      <img class="inspector-badge ${node.completed ? '' : 'locked'}"
           src="${badgeUrl(node)}"
           alt="${node.title}"
           title="Click to view large badge"
           onclick="openBadgeZoom()" />
      <button type="button" class="zoom-btn" onclick="openBadgeZoom()">Enlarge Badge</button>
      <h2 style="font-size:1.2rem;">${node.title}</h2>
      <span style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem;">${statusText}</span>
      <code style="font-size:0.72rem;color:var(--muted);margin-top:0.25rem;">data/badges/${node.badge_dir}/${node.badge}</code>
    </div>
    <p style="font-size:0.92rem;">${node.description}</p>
    ${node.advice ? `
      <div class="advice-box">
        <strong>Field Advice & Mechanics</strong>
        ${node.advice}
      </div>
    ` : ""}
    ${actionControlHtml}
    <div class="notes-area">
      <label style="font-size:0.8rem;color:var(--muted);font-weight:600;">${appState.user_id}'s Field Log / Reflection</label>
      <textarea id="noteTextarea" placeholder="Jot down notes, metrics, or lessons learned...">${noteVal}</textarea>
      <button style="width:100%;background:#334155;color:var(--text);" onclick="saveNote('${node.id}')">Save Reflection</button>
    </div>
  `;
}

function openBadgeZoom() {
  const node = nodeIndex[selectedGoalId];
  if (!node) return;

  const dialog = document.getElementById("badgeDialog");
  const img = document.getElementById("dialogBadgeImg");
  const title = document.getElementById("dialogBadgeTitle");
  const path = document.getElementById("dialogBadgePath");

  img.src = badgeUrl(node);
  img.alt = node.title;
  title.textContent = node.title;
  path.textContent = `data/badges/${node.badge_dir}/${node.badge}`;

  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    window.open(badgeUrl(node), "_blank");
  }
}

function closeBadgeZoom() {
  const dialog = document.getElementById("badgeDialog");
  if (dialog && dialog.open) {
    dialog.close();
  }
}

function handleDialogBackdropClick(event) {
  const dialog = document.getElementById("badgeDialog");
  if (event.target === dialog) {
    dialog.close();
  }
}

fetchTrees();
