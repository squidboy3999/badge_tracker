from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Any, Sequence


@dataclass(frozen=True)
class GoalSpec:
    """Immutable specification of a goal node loaded from config."""
    id: str
    title: str
    description: str = ""
    advice: str = ""
    badge: str = "default.png"
    badge_dir: str = "default"
    categories: tuple[str, ...] = field(default_factory=tuple)
    users: tuple[str, ...] = field(default_factory=tuple)
    rule: Literal["all", "any"] = "all"
    target: int = 1
    children: tuple[GoalSpec, ...] = field(default_factory=tuple)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


@dataclass(frozen=True)
class EvaluatedGoal:
    """Immutable evaluated state of a goal node for a specific user."""
    id: str
    title: str
    description: str
    advice: str
    badge: str
    badge_dir: str
    categories: tuple[str, ...]
    users: tuple[str, ...]
    rule: Literal["all", "any"]
    is_leaf: bool
    target: int
    current_count: int
    completed: bool
    completed_at: str | None
    progress_completed: int
    progress_total: int
    progress_pct: float
    children: tuple[EvaluatedGoal, ...] = field(default_factory=tuple)


def parse_goal_spec(
    raw: dict,
    badge_dir: str = "default",
    default_users: tuple[str, ...] = (),
    default_categories: tuple[str, ...] = (),
) -> GoalSpec:
    """Pure parser converting raw dictionary from YAML/JSON into a GoalSpec tree."""
    raw_users = raw.get("users")
    users = tuple(str(u) for u in raw_users) if raw_users is not None else default_users

    raw_cats = raw.get("categories")
    if raw_cats is None and "category" in raw:
        raw_cats = [raw["category"]] if isinstance(raw["category"], str) else raw["category"]
    categories = (
        tuple(str(c) for c in raw_cats)
        if raw_cats is not None
        else default_categories
    )

    children_raw = raw.get("children", [])
    children = tuple(
        parse_goal_spec(
            c,
            badge_dir=badge_dir,
            default_users=users,
            default_categories=categories,
        )
        for c in children_raw
    )
    rule = raw.get("rule", "all")
    if rule not in ("all", "any"):
        raise ValueError(f"Invalid rule '{rule}' on goal '{raw.get('id')}'. Must be 'all' or 'any'.")

    target = max(1, int(raw.get("target", 1)))

    return GoalSpec(
        id=str(raw["id"]),
        title=str(raw["title"]),
        description=str(raw.get("description", "")),
        advice=str(raw.get("advice", "")),
        badge=str(raw.get("badge", "default.png")),
        badge_dir=badge_dir,
        categories=categories,
        users=users,
        rule=rule,
        target=target,
        children=children,
    )


def filter_specs_for_user(specs: Sequence[GoalSpec], user_id: str) -> list[GoalSpec]:
    """
    Pure filter returning only GoalSpec trees assigned to `user_id` (case-insensitive).
    If a tree has an empty `users` tuple, it is treated as global across all users.
    """
    target_lower = user_id.strip().lower()
    return [
        spec
        for spec in specs
        if not spec.users or any(u.lower() == target_lower for u in spec.users)
    ]


def filter_and_sort_specs(
    specs: Sequence[GoalSpec],
    user_id: str,
    category_filter: str = "all",
    category_order: Sequence[str] = (),
) -> list[GoalSpec]:
    """
    Filters GoalSpec trees by user_id and category_filter ('all' or a specific tag),
    then sorts trees deterministically by their earliest matching tag in `category_order`.
    """
    user_specs = filter_specs_for_user(specs, user_id)

    cat_key = category_filter.strip().lower()
    if cat_key and cat_key != "all":
        filtered = [
            s for s in user_specs
            if any(c.lower() == cat_key for c in s.categories)
        ]
    else:
        filtered = list(user_specs)

    order_map = {c.lower(): idx for idx, c in enumerate(category_order)}
    fallback_rank = len(order_map) + 1000

    def sort_key(spec: GoalSpec) -> tuple[int, str]:
        if not spec.categories:
            return (fallback_rank, spec.title.lower())
        best_rank = min(
            order_map.get(c.lower(), fallback_rank) for c in spec.categories
        )
        return (best_rank, spec.title.lower())

    return sorted(filtered, key=sort_key)


def normalize_leaf_entry(raw_entry: Any, target: int) -> tuple[int, str | None]:
    """
    Normalizes stored user progress into (current_count, completed_at).
    Supports legacy string timestamps and counter dicts.
    """
    if raw_entry is None:
        return 0, None
    if isinstance(raw_entry, str):
        return target, raw_entry
    if isinstance(raw_entry, dict):
        count = max(0, min(target, int(raw_entry.get("count", 0))))
        ts = raw_entry.get("updated_at") if count >= target else None
        return count, ts
    return 0, None


def evaluate_tree(
    spec: GoalSpec,
    completed_map: dict[str, Any],
) -> EvaluatedGoal:
    """
    Recursively evaluates a GoalSpec against user state.
    Leaf nodes check `current_count >= spec.target`.
    Parent nodes roll up child completion according to `spec.rule`.
    """
    if spec.is_leaf:
        current_count, completed_at = normalize_leaf_entry(
            completed_map.get(spec.id), spec.target
        )
        is_done = current_count >= spec.target
        pct = round((current_count / spec.target) * 100.0, 1)
        return EvaluatedGoal(
            id=spec.id,
            title=spec.title,
            description=spec.description,
            advice=spec.advice,
            badge=spec.badge,
            badge_dir=spec.badge_dir,
            categories=spec.categories,
            users=spec.users,
            rule=spec.rule,
            is_leaf=True,
            target=spec.target,
            current_count=current_count,
            completed=is_done,
            completed_at=completed_at if is_done else None,
            progress_completed=current_count,
            progress_total=spec.target,
            progress_pct=pct,
            children=(),
        )

    evaluated_children = tuple(
        evaluate_tree(child, completed_map) for child in spec.children
    )

    if spec.rule == "all":
        is_done = all(c.completed for c in evaluated_children)
        prog_completed = sum(1 for c in evaluated_children if c.completed)
        prog_total = len(evaluated_children)
        pct = (
            round(sum(c.progress_pct for c in evaluated_children) / len(evaluated_children), 1)
            if evaluated_children
            else 0.0
        )
    else:  # "any"
        is_done = any(c.completed for c in evaluated_children)
        done_children = sum(1 for c in evaluated_children if c.completed)
        prog_completed = min(1, done_children) if is_done else 0
        prog_total = 1
        pct = 100.0 if is_done else max((c.progress_pct for c in evaluated_children), default=0.0)

    completed_at = None
    if is_done:
        child_times = [c.completed_at for c in evaluated_children if c.completed_at]
        if child_times:
            completed_at = max(child_times)

    return EvaluatedGoal(
        id=spec.id,
        title=spec.title,
        description=spec.description,
        advice=spec.advice,
        badge=spec.badge,
        badge_dir=spec.badge_dir,
        categories=spec.categories,
        users=spec.users,
        rule=spec.rule,
        is_leaf=False,
        target=1,
        current_count=1 if is_done else 0,
        completed=is_done,
        completed_at=completed_at,
        progress_completed=prog_completed,
        progress_total=prog_total,
        progress_pct=pct,
        children=evaluated_children,
    )


def collect_leaf_specs(spec: GoalSpec) -> dict[str, GoalSpec]:
    """Returns a map of {leaf_id: GoalSpec} for all leaf nodes in the tree."""
    if spec.is_leaf:
        return {spec.id: spec}
    leaves: dict[str, GoalSpec] = {}
    for child in spec.children:
        leaves.update(collect_leaf_specs(child))
    return leaves


def collect_leaf_ids(spec: GoalSpec) -> set[str]:
    """Returns all valid leaf goal IDs in a tree."""
    return set(collect_leaf_specs(spec).keys())


def toggle_leaf_state(
    current_map: dict[str, Any],
    goal_id: str,
    valid_leaves: dict[str, GoalSpec] | set[str],
    timestamp: str,
) -> dict[str, Any]:
    """Pure state transition toggling a leaf between 0 and its full target."""
    if goal_id not in valid_leaves:
        raise ValueError(f"Goal '{goal_id}' is either unknown or a parent container (auto-evaluated).")

    target = valid_leaves[goal_id].target if isinstance(valid_leaves, dict) else 1
    current_count, _ = normalize_leaf_entry(current_map.get(goal_id), target)

    next_map = dict(current_map)
    if current_count >= target:
        del next_map[goal_id]
    else:
        if target == 1:
            next_map[goal_id] = timestamp
        else:
            next_map[goal_id] = {"count": target, "updated_at": timestamp}
    return next_map


def update_leaf_count(
    current_map: dict[str, Any],
    goal_id: str,
    new_count: int,
    valid_leaves: dict[str, GoalSpec],
    timestamp: str,
) -> dict[str, Any]:
    """Pure state transition setting a specific count [0..target] on a leaf node."""
    if goal_id not in valid_leaves:
        raise ValueError(f"Goal '{goal_id}' is either unknown or a parent container (auto-evaluated).")

    spec = valid_leaves[goal_id]
    clamped = max(0, min(spec.target, int(new_count)))

    next_map = dict(current_map)
    if clamped == 0:
        next_map.pop(goal_id, None)
    elif spec.target == 1 and clamped == 1:
        next_map[goal_id] = timestamp
    else:
        next_map[goal_id] = {"count": clamped, "updated_at": timestamp}
    return next_map
