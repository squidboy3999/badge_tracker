import pytest
from badge_tracker.core import (
    collect_leaf_ids,
    collect_leaf_specs,
    evaluate_tree,
    filter_and_sort_specs,
    filter_specs_for_user,
    parse_goal_spec,
    toggle_leaf_state,
    update_leaf_count,
)

SAMPLE_RAW_TREE = {
    "id": "root_engineering",
    "title": "Systems Engineering Mastery",
    "rule": "all",
    "children": [
        {
            "id": "branch_fundamentals",
            "title": "Core Fundamentals",
            "rule": "all",
            "children": [
                {"id": "leaf_setup", "title": "Environment Setup"},
                {"id": "leaf_first_commit", "title": "First Commit"},
            ],
        },
        {
            "id": "branch_deployment",
            "title": "Deployment Options",
            "rule": "any",
            "children": [
                {"id": "leaf_container", "title": "Container Build"},
                {"id": "leaf_package", "title": "Native Package"},
            ],
        },
    ],
}


def test_hierarchical_rollup_all_and_any():
    spec = parse_goal_spec(SAMPLE_RAW_TREE)

    # 1. Partial leaf completion
    state_1 = {"leaf_setup": "2026-01-01T10:00Z"}
    eval_1 = evaluate_tree(spec, state_1)
    assert not eval_1.completed
    assert eval_1.children[0].progress_completed == 1
    assert eval_1.children[0].progress_total == 2
    assert not eval_1.children[0].completed

    # 2. Satisfy 'all' branch + one leaf of 'any' branch -> unlocks root
    state_2 = {
        "leaf_setup": "2026-01-01T10:00Z",
        "leaf_first_commit": "2026-01-01T11:00Z",
        "leaf_package": "2026-01-01T12:00Z",
    }
    eval_2 = evaluate_tree(spec, state_2)
    assert eval_2.children[0].completed is True
    assert eval_2.children[1].completed is True
    assert eval_2.completed is True
    assert eval_2.progress_pct == 100.0


def test_cannot_toggle_non_leaf_parent():
    spec = parse_goal_spec(SAMPLE_RAW_TREE)
    leaves = collect_leaf_ids(spec)
    assert leaves == {"leaf_setup", "leaf_first_commit", "leaf_container", "leaf_package"}

    with pytest.raises(ValueError, match="parent container"):
        toggle_leaf_state({}, "branch_fundamentals", leaves, "2026-01-01T12:00Z")


def test_counted_leaf_goal_progression():
    raw = {
        "id": "quality_assurance",
        "title": "Quality Assurance",
        "rule": "all",
        "children": [
            {"id": "unit_tests", "title": "Write 20 Unit Tests", "target": 20},
            {"id": "ci_pipeline", "title": "Configure CI Pipeline", "target": 1},
        ],
    }
    spec = parse_goal_spec(raw)
    leaves = collect_leaf_specs(spec)

    state = {}
    state = update_leaf_count(state, "unit_tests", 7, leaves, "2026-01-01T15:00Z")
    eval_partial = evaluate_tree(spec, state)

    counter_node = eval_partial.children[0]
    assert counter_node.current_count == 7
    assert counter_node.target == 20
    assert counter_node.progress_pct == 35.0
    assert not counter_node.completed
    assert not eval_partial.completed

    # Reach 20 unit tests and 1 CI pipeline -> unlocks parent
    state = update_leaf_count(state, "unit_tests", 20, leaves, "2026-01-01T16:00Z")
    state = update_leaf_count(state, "ci_pipeline", 1, leaves, "2026-01-01T17:00Z")
    eval_done = evaluate_tree(spec, state)
    assert eval_done.children[0].completed is True
    assert eval_done.completed is True
    assert eval_done.progress_pct == 100.0


def test_user_and_multi_category_filtering_and_sorting():
    backend_tree = parse_goal_spec(
        {"id": "backend", "title": "Backend API", "children": [{"id": "b1", "title": "Endpoint"}]},
        badge_dir="backend_api",
        default_users=("alice",),
        default_categories=("code", "architecture"),
    )
    infra_tree = parse_goal_spec(
        {"id": "infra", "title": "Cloud Infra", "children": [{"id": "i1", "title": "Cluster"}]},
        badge_dir="cloud_infra",
        default_users=("alice", "bob", "team"),
        default_categories=("ops", "architecture"),
    )
    security_tree = parse_goal_spec(
        {"id": "sec", "title": "Security Audit", "children": [{"id": "s1", "title": "Scan"}]},
        badge_dir="security_audit",
        default_users=("alice",),
        default_categories=("security",),
    )
    all_specs = [backend_tree, infra_tree, security_tree]
    cat_order = ["security", "ops", "code", "architecture"]

    # 1. 'all' returns all 3 of alice's trees sorted according to cat_order
    alice_all = filter_and_sort_specs(
        all_specs, "alice", category_filter="all", category_order=cat_order
    )
    assert [s.id for s in alice_all] == ["sec", "infra", "backend"]
    assert alice_all[2].badge_dir == "backend_api"

    # 2. Multi-category tag 'architecture' matches both infra_tree and backend_tree
    alice_arch = filter_and_sort_specs(
        all_specs, "alice", category_filter="architecture", category_order=cat_order
    )
    assert [s.id for s in alice_arch] == ["infra", "backend"]

    # 3. Single category 'code' matches only backend_tree
    alice_code = filter_and_sort_specs(
        all_specs, "alice", category_filter="code", category_order=cat_order
    )
    assert [s.id for s in alice_code] == ["backend"]

    # 4. User isolation holds
    bob_all = filter_specs_for_user(all_specs, "bob")
    assert [s.id for s in bob_all] == ["infra"]
