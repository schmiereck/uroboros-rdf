#!/usr/bin/env python3
"""1D cellular automaton simulator for bit-conserving reversible rules."""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
RULES_PATH = REPO_ROOT / "archive" / "iter_001" / "results" / "valid_rules.json"
RESULTS_DIR = SCRIPT_DIR.parent / "results"
RESULT_YAML = SCRIPT_DIR.parent / "result.yaml"

LATTICE_SIZE = 100
NUM_STEPS = 200


def simulate_rule(rule):
    state = [0] * LATTICE_SIZE
    state[LATTICE_SIZE // 2] = 1

    history = [tuple(state)]
    for _ in range(NUM_STEPS):
        new_state = [0] * LATTICE_SIZE
        for i in range(LATTICE_SIZE):
            left = state[(i - 1) % LATTICE_SIZE]
            center = state[i]
            right = state[(i + 1) % LATTICE_SIZE]
            output = rule[f"{left}{center}{right}"]
            new_state[i] = int(output[1])  # center bit of the 3-bit output
        state = new_state
        history.append(tuple(state))
    return history


def classify_behavior(history):
    final = history[-1]

    if all(c == 0 for c in final):
        return "DECAY"

    if history[-1] == history[-2]:
        return "STABLE"

    # Check for exact-state periodicity (no translation) up to period 20
    for period in range(2, 21):
        if len(history) > period + 20:
            consistent = all(
                history[-1 - k] == history[-1 - k - period] for k in range(20)
            )
            if consistent:
                return "PERIODIC"

    # Glider detection: centroid moves at near-constant velocity, width stable
    centroids = []
    for state in history:
        ones = [i for i, v in enumerate(state) if v == 1]
        centroids.append(sum(ones) / len(ones) if ones else None)

    valid = [(t, c) for t, c in enumerate(centroids) if c is not None]
    if len(valid) < 20:
        return "CHAOTIC"

    # Unwrap centroid trajectory for periodic boundaries
    ts = [valid[0][0]]
    xs = [valid[0][1]]
    for i in range(1, len(valid)):
        diff = valid[i][1] - valid[i - 1][1]
        if diff > LATTICE_SIZE / 2:
            diff -= LATTICE_SIZE
        elif diff < -LATTICE_SIZE / 2:
            diff += LATTICE_SIZE
        xs.append(xs[-1] + diff)
        ts.append(valid[i][0])

    # Fit line to second half of trajectory
    n = len(xs) // 2
    t_fit, x_fit = ts[n:], xs[n:]
    mean_t = sum(t_fit) / len(t_fit)
    mean_x = sum(x_fit) / len(x_fit)
    ss_tt = sum((t - mean_t) ** 2 for t in t_fit)
    if ss_tt == 0:
        return "STABLE"

    slope = sum((t - mean_t) * (x - mean_x) for t, x in zip(t_fit, x_fit)) / ss_tt
    intercept = mean_x - slope * mean_t
    residuals = [abs(x - (slope * t + intercept)) for t, x in zip(t_fit, x_fit)]
    max_residual = max(residuals)

    # Width stability over second half
    widths = []
    for state in history[n:]:
        ones = [i for i, v in enumerate(state) if v == 1]
        if ones:
            widths.append(max(ones) - min(ones))
    width_stable = (max(widths) - min(widths)) <= 3 if widths else False

    if max_residual < 1.0 and width_stable and abs(slope) > 0.05:
        return "GLIDER"

    return "CHAOTIC"


def write_yaml(path, data):
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    with open(RULES_PATH, encoding="utf-8") as f:
        rules = json.load(f)
    print(f"Loaded {len(rules)} rules")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    counts = {"DECAY": 0, "STABLE": 0, "PERIODIC": 0, "GLIDER": 0, "CHAOTIC": 0}
    glider_indices = []

    for idx, rule in enumerate(rules):
        history = simulate_rule(rule)
        behavior = classify_behavior(history)
        counts[behavior] += 1

        if behavior == "GLIDER":
            glider_indices.append(idx)
            final = "".join(str(c) for c in history[-1])
            (RESULTS_DIR / f"glider_rule_{idx}.txt").write_text(final + "\n", encoding="utf-8")

        print(f"Rule {idx:2d}: {behavior}")

    print(f"\nRules tested   : {len(rules)}")
    print(f"Gliders found  : {counts['GLIDER']}")
    print(f"Stable found   : {counts['STABLE']}")
    print(f"Periodic found : {counts['PERIODIC']}")
    print(f"Decay found    : {counts['DECAY']}")
    print(f"Chaotic found  : {counts['CHAOTIC']}")
    print(f"Glider indices : {glider_indices}")

    write_yaml(RESULT_YAML, {
        "rules_tested": len(rules),
        "gliders_found": counts["GLIDER"],
        "stable_found": counts["STABLE"],
        "periodic_found": counts["PERIODIC"],
        "decay_found": counts["DECAY"],
        "chaotic_found": counts["CHAOTIC"],
        "glider_rule_indices": glider_indices,
    })
    print(f"\nWritten: {RESULT_YAML}")
    return 0 if counts["GLIDER"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
