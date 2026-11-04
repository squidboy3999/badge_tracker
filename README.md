# Hierarchical Badge Foundry

A local-first, declarative skill-tree and personal achievement tracker built with a **Functional Core / Impure Shell** architecture (Python, FastAPI, Vanilla JS, and Podman).

Define hierarchical goals in simple YAML or JSON files, organize them by multi-category tags and user profiles, and track both boolean milestones and counted repetitions (`target: N`) with automatic parent-node rollups.

---

## Core Features

* **Declarative Goal Trees:** Drop `.yaml`, `.yml`, or `.json` files into `data/goals/` and they hot-reload into the dashboard.
* **Deterministic Rollup Engine (Functional Core):** Parent nodes are never toggled manually—their completion state, timestamps, and progress percentages are pure functions of their child nodes (`rule: "all"` or `rule: "any"`).
* **Checkboxes & Repetition Counters:** Leaf nodes default to a simple checkbox (`target: 1`) or automatically render inline `-`/`+` steppers and a range slider when `target > 1` (e.g., `target: 20`).
* **Multi-User & Multi-Category Filtering:** Configure profiles in `data/users.yaml` and taxonomy tags in `data/categories.yaml`. Filter trees by category or view `all`.
* **Collapsible Hierarchy:** Fold and expand sub-goals at any depth with persistent `localStorage` state.
* **Zero-Config SVG Fallback Crest Generator:** Reference any `.png` filename in your YAML (`badge: "my_icon.png"`). Until you drop a custom PNG into `data/badges/<yaml_stem>/`, the backend generates a deterministic, color-hashed hexagonal SVG crest with monogram initials.

---

## Quick Start (Podman / Docker)

### 1. Initialize Local Data from `sample_data/`
Your personal `data/` directory is git-ignored so private goals and state are never committed. Copy `sample_data/` to `data/` to start:

```bash
cp -r sample_data data
```

### 2. Build and Run with `podman-compose`
The container mounts `./src`, `./tests`, and `./data` with SELinux `:Z` volume flags and runs `uvicorn --reload` for live development:

```bash
podman-compose up --build -d
```

Open **`http://localhost:8080`** in your browser.

### 3. Run the Test Suite
Execute `pytest` directly inside the running container:

```bash
podman exec -it badge-tracker pytest -v
```

---

## Architecture

```text
src/badge_tracker/
├── core.py          # Pure Functional Core: immutable specs, tree evaluation, counter math
├── main.py          # Impure Shell: FastAPI routes, YAML/JSON disk I/O, SVG fallback generator
└── static/
    ├── index.html   # Semantic layout shell
    ├── styles.css   # Dark-slate responsive styling
    └── app.js       # Reactive state management & DOM rendering
```

* **`core.py` (Zero I/O):** Contains `GoalSpec` and `EvaluatedGoal` frozen dataclasses alongside pure functions (`parse_goal_spec`, `evaluate_tree`, `filter_and_sort_specs`, `toggle_leaf_state`, `update_leaf_count`).
* **`main.py` (Filesystem & HTTP Boundary):** Reads `data/users.yaml`, `data/categories.yaml`, and `data/goals/*.yaml` on demand and persists per-user progress in `data/state/<user_id>.json`.

---

## Configuration Schema

### 1. `data/users.yaml`
Defines the user dropdown options and default active profile:

```yaml
default_user: developer

users:
  - id: developer
    name: "Developer"
    description: "Software Engineering & Systems Mastery"
  - id: athlete
    name: "Athlete"
    description: "Conditioning & Mobility Milestones"
```

### 2. `data/categories.yaml`
Defines the ordered category taxonomy. Goal trees are sorted according to their earliest matching category in this file:

```yaml
categories:
  - id: engineering
    label: "Software Engineering"
  - id: devops
    label: "Containers & DevOps"
  - id: fitness
    label: "Physical Conditioning"
```

### 3. Goal Tree Files (`data/goals/<name>.yaml`)
The filename stem (e.g., `engineering_onboarding`) determines the badge icon subfolder (`data/badges/engineering_onboarding/`).

```yaml
users:
  - developer
categories:
  - engineering
  - devops

trees:
  - id: container_mastery
    title: "Container Architect"
    description: "Master rootless containers and local orchestration."
    advice: "Prefer rootless containers and minimal base images."
    badge: "container_architect.png"
    rule: "all"          # "all" (every child required) or "any" (at least 1 child required)
    children:
      - id: first_containerfile
        title: "Write a Multi-Stage Containerfile"
        description: "Build a slim production image."
        advice: "Order layers from least-frequently changed to most-frequently changed."
        badge: "containerfile.png"
        target: 1        # Renders a checkbox (default: 1)

      - id:green_test_runs
        title: "10 Clean Test Runs"
        description: "Execute 10 passing pytest runs inside the container."
        advice: "Keep unit tests fast and free of network/filesystem side effects."
        badge: "pytest_runs.png"
        target: 10       # Renders -/+ stepper buttons and a slider
```

---

## Adding Custom Badge Icons

1. Drop `.png` (or `.jpg`) files into `data/badges/<yaml_stem>/<badge_filename>.png`.
2. If you generate square `.jpg` or `.png` icons using an image model, run the included ImageMagick helper script to batch-convert, center-crop to `256x256`, and apply a transparent hexagonal crest mask:

```bash
./process_badges.sh ./data/badges/engineering_onboarding
```

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/trees?user_id=<id>&category=<tag\|all>` | Returns evaluated goal trees, user list, category list, and notes |
| `POST` | `/api/goals/{goal_id}/toggle` | Toggles a leaf node between `0` and its full `target` |
| `POST` | `/api/goals/{goal_id}/progress` | Sets a specific repetition count `[0..target]` on a leaf node |
| `POST` | `/api/goals/{goal_id}/note` | Saves a user reflection note for a specific goal ID |
| `GET` | `/badges/{badge_dir}/{filename}` | Serves the PNG from disk or generates a fallback SVG crest |
