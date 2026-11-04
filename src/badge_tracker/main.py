from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

from badge_tracker.core import (
    GoalSpec,
    collect_leaf_specs,
    evaluate_tree,
    filter_and_sort_specs,
    filter_specs_for_user,
    parse_goal_spec,
    toggle_leaf_state,
    update_leaf_count,
)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
GOALS_DIR = DATA_DIR / "goals"
BADGES_DIR = DATA_DIR / "badges"
STATE_DIR = DATA_DIR / "state"
USERS_FILE = DATA_DIR / "users.yaml"
CATEGORIES_FILE = DATA_DIR / "categories.yaml"

DEFAULT_FALLBACK_USER = os.getenv("DEFAULT_USER", "default")
FALLBACK_USERS = [
    {"id": DEFAULT_FALLBACK_USER, "name": "Default User", "description": "Local Profile"},
]
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Personal Badge Tracker")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ToggleRequest(BaseModel):
    user_id: str = DEFAULT_FALLBACK_USER
    category: str = "all"
    note: str | None = None


class ProgressRequest(BaseModel):
    user_id: str = DEFAULT_FALLBACK_USER
    category: str = "all"
    count: int


class NoteRequest(BaseModel):
    user_id: str = DEFAULT_FALLBACK_USER
    category: str = "all"
    note: str


def ensure_directories() -> None:
    for d in (GOALS_DIR, BADGES_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_users_config() -> tuple[str, list[dict[str, str]]]:
    """Reads data/users.yaml and returns (default_user_id, list of user dicts)."""
    ensure_directories()
    if not USERS_FILE.exists():
        return DEFAULT_FALLBACK_USER, list(FALLBACK_USERS)

    raw = yaml.safe_load(USERS_FILE.read_text(encoding="utf-8")) or {}
    default_user = str(raw.get("default_user", DEFAULT_FALLBACK_USER))
    raw_users = raw.get("users", []) if isinstance(raw, dict) else raw

    users: list[dict[str, str]] = []
    for item in raw_users:
        if isinstance(item, str):
            users.append({"id": item, "name": item, "description": ""})
        elif isinstance(item, dict) and "id" in item:
            uid = str(item["id"])
            users.append({
                "id": uid,
                "name": str(item.get("name", uid)),
                "description": str(item.get("description", "")),
            })
    return default_user, (users or list(FALLBACK_USERS))


def load_categories_config() -> list[dict[str, str]]:
    """Reads data/categories.yaml and returns an ordered list of {id, label} dicts."""
    ensure_directories()
    if not CATEGORIES_FILE.exists():
        return []

    raw = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8")) or {}
    raw_cats = raw.get("categories", []) if isinstance(raw, dict) else raw

    categories: list[dict[str, str]] = []
    for item in raw_cats:
        if isinstance(item, str):
            categories.append({
                "id": item,
                "label": item.replace("_", " ").title(),
            })
        elif isinstance(item, dict) and "id" in item:
            cid = str(item["id"])
            categories.append({
                "id": cid,
                "label": str(item.get("label", cid.replace("_", " ").title())),
            })
    return categories


def load_all_goal_specs() -> list[GoalSpec]:
    """
    Scans data/goals/ for all .yaml, .yml, and .json files.
    Uses file_path.stem as `badge_dir` and reads top-level `users:` and `categories:`.
    """
    ensure_directories()
    specs: list[GoalSpec] = []
    files = sorted(
        p for p in GOALS_DIR.iterdir()
        if p.suffix.lower() in (".yaml", ".yml", ".json")
    )
    for file_path in files:
        badge_dir = file_path.stem
        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() == ".json":
            data = json.loads(content)
        else:
            data = yaml.safe_load(content) or {}

        file_users: tuple[str, ...] = ()
        file_categories: tuple[str, ...] = ()
        if isinstance(data, dict):
            raw_users = data.get("users", [])
            file_users = tuple(str(u) for u in raw_users)

            raw_cats = data.get("categories", [])
            if isinstance(raw_cats, str):
                raw_cats = [raw_cats]
            file_categories = tuple(str(c) for c in raw_cats)
            raw_trees = data.get("trees", [])
        else:
            raw_trees = data

        for raw_tree in raw_trees:
            specs.append(
                parse_goal_spec(
                    raw_tree,
                    badge_dir=badge_dir,
                    default_users=file_users,
                    default_categories=file_categories,
                )
            )
    return specs


def get_user_state_path(user_id: str) -> Path:
    safe_user = "".join(c for c in user_id if c.isalnum() or c in ("_", "-")) or DEFAULT_FALLBACK_USER
    return STATE_DIR / f"{safe_user}.json"


def load_user_state(user_id: str) -> dict[str, Any]:
    ensure_directories()
    path = get_user_state_path(user_id)
    if not path.exists():
        return {"user_id": user_id, "completed": {}, "notes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_user_state(user_id: str, state: dict[str, Any]) -> None:
    ensure_directories()
    path = get_user_state_path(user_id)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/trees")
def get_trees(
    user_id: str | None = Query(default=None),
    category: str = Query(default="all"),
) -> dict[str, Any]:
    default_user, configured_users = load_users_config()
    active_user = user_id or default_user

    configured_cats = load_categories_config()
    cat_order = [c["id"] for c in configured_cats]

    all_specs = load_all_goal_specs()

    user_all_specs = filter_specs_for_user(all_specs, active_user)
    known_cat_ids = {c["id"].lower() for c in configured_cats}
    for spec in user_all_specs:
        for cat_tag in spec.categories:
            if cat_tag.lower() not in known_cat_ids:
                configured_cats.append({
                    "id": cat_tag,
                    "label": cat_tag.replace("_", " ").title(),
                })
                known_cat_ids.add(cat_tag.lower())

    filtered_specs = filter_and_sort_specs(
        all_specs,
        user_id=active_user,
        category_filter=category,
        category_order=cat_order,
    )

    user_state = load_user_state(active_user)
    completed_map: dict[str, Any] = user_state.get("completed", {})
    notes_map: dict[str, str] = user_state.get("notes", {})

    evaluated = [asdict(evaluate_tree(spec, completed_map)) for spec in filtered_specs]

    known_user_ids = {u["id"] for u in configured_users}
    for spec in all_specs:
        for u in spec.users:
            if u not in known_user_ids:
                configured_users.append({"id": u, "name": u, "description": ""})
                known_user_ids.add(u)

    return {
        "user_id": active_user,
        "selected_category": category,
        "available_users": configured_users,
        "available_categories": configured_cats,
        "notes": notes_map,
        "trees": evaluated,
    }


@app.post("/api/goals/{goal_id}/toggle")
def toggle_goal(goal_id: str, req: ToggleRequest) -> dict[str, Any]:
    specs = load_all_goal_specs()
    valid_leaves: dict[str, GoalSpec] = {}
    for s in specs:
        valid_leaves.update(collect_leaf_specs(s))

    user_state = load_user_state(req.user_id)
    completed_map: dict[str, Any] = user_state.get("completed", {})

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        updated_map = toggle_leaf_state(completed_map, goal_id, valid_leaves, now_iso)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    user_state["completed"] = updated_map
    if req.note is not None:
        user_state.setdefault("notes", {})[goal_id] = req.note

    save_user_state(req.user_id, user_state)
    return get_trees(user_id=req.user_id, category=req.category)


@app.post("/api/goals/{goal_id}/progress")
def set_goal_progress(goal_id: str, req: ProgressRequest) -> dict[str, Any]:
    specs = load_all_goal_specs()
    valid_leaves: dict[str, GoalSpec] = {}
    for s in specs:
        valid_leaves.update(collect_leaf_specs(s))

    user_state = load_user_state(req.user_id)
    completed_map: dict[str, Any] = user_state.get("completed", {})

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        updated_map = update_leaf_count(completed_map, goal_id, req.count, valid_leaves, now_iso)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    user_state["completed"] = updated_map
    save_user_state(req.user_id, user_state)
    return get_trees(user_id=req.user_id, category=req.category)


@app.post("/api/goals/{goal_id}/note")
def save_note(goal_id: str, req: NoteRequest) -> dict[str, Any]:
    user_state = load_user_state(req.user_id)
    user_state.setdefault("notes", {})[goal_id] = req.note
    save_user_state(req.user_id, user_state)
    return get_trees(user_id=req.user_id, category=req.category)


def _render_fallback_svg(seed_key: str, filename: str) -> Response:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) % 360
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    initials = "".join(w[0].upper() for w in stem.split()[:2]) or "BG"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="hsl({hue}, 70%, 55%)" />
          <stop offset="100%" stop-color="hsl({(hue + 40) % 360}, 80%, 30%)" />
        </linearGradient>
      </defs>
      <polygon points="60,6 108,32 108,88 60,114 12,88 12,32"
               fill="url(#g)" stroke="hsl({hue}, 85%, 75%)" stroke-width="4" />
      <polygon points="60,15 99,37 99,83 60,105 21,83 21,37"
               fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" stroke-dasharray="4,2" />
      <text x="60" y="68" font-family="system-ui, sans-serif" font-size="28"
            font-weight="800" fill="#ffffff" text-anchor="middle" letter-spacing="1">{initials}</text>
    </svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/badges/{badge_dir}/{filename}")
def get_categorized_badge_image(badge_dir: str, filename: str) -> Response:
    safe_dir = Path(badge_dir).name
    safe_name = Path(filename).name

    scoped_path = BADGES_DIR / safe_dir / safe_name
    if scoped_path.exists() and scoped_path.is_file():
        return FileResponse(scoped_path)

    flat_fallback = BADGES_DIR / safe_name
    if flat_fallback.exists() and flat_fallback.is_file():
        return FileResponse(flat_fallback)

    return _render_fallback_svg(f"{safe_dir}/{safe_name}", safe_name)


@app.get("/badges/{filename}")
def get_legacy_badge_image(filename: str) -> Response:
    safe_name = Path(filename).name
    file_path = BADGES_DIR / safe_name
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return _render_fallback_svg(safe_name, safe_name)
