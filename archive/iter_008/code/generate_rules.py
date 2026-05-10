"""
Generate all bit-conserving, reversible (permutation) rules for a 1D 3-bit neighborhood,
filter trivial ones, and write results to iter_008/results/ and iter_008/result.yaml.
"""
import itertools
import json
import os
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ITER_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(ITER_DIR, "results")
RESULT_YAML = os.path.join(ITER_DIR, "result.yaml")
VALID_RULES_JSON = os.path.join(RESULTS_DIR, "valid_rules.json")

STATES = [format(i, '03b') for i in range(8)]

def hamming_weight(s):
    return s.count('1')

def shift_left(s):
    return s[1:] + s[0]

def shift_right(s):
    return s[-1] + s[:-1]

def build_trivial_rules():
    identity = {s: s for s in STATES}
    shift_l = {s: shift_left(s) for s in STATES}
    shift_r = {s: shift_right(s) for s in STATES}
    return [identity, shift_l, shift_r]

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    groups = {}
    for s in STATES:
        w = hamming_weight(s)
        groups.setdefault(w, []).append(s)

    group_perms = {}
    for w, members in sorted(groups.items()):
        group_perms[w] = list(itertools.permutations(members))

    trivial_rules = build_trivial_rules()
    trivial_set = [frozenset(r.items()) for r in trivial_rules]

    all_rules = []
    non_trivial_rules = []

    weights = sorted(group_perms.keys())
    for combo in itertools.product(*[group_perms[w] for w in weights]):
        rule = {}
        for w, perm in zip(weights, combo):
            orig = sorted(groups[w])
            for inp, out in zip(orig, perm):
                rule[inp] = out
        all_rules.append(rule)
        if frozenset(rule.items()) not in trivial_set:
            non_trivial_rules.append(rule)

    total = len(all_rules)
    trivial_found = total - len(non_trivial_rules)
    nontrivial_found = len(non_trivial_rules)

    with open(VALID_RULES_JSON, 'w', encoding='utf-8') as f:
        json.dump(non_trivial_rules, f, indent=2)

    summary = {
        "status": "ok" if nontrivial_found > 0 else "no_results",
        "total_bit_conserving_permutations": total,
        "trivial_rules_found": trivial_found,
        "nontrivial_rules_found": nontrivial_found,
        "experimenter_view": (
            f"Found {nontrivial_found} non-trivial bit-conserving rules "
            f"out of {total} total."
        ),
        "artifacts": [
            "archive/iter_008/results/valid_rules.json",
        ],
        "metrics": {
            "total_bit_conserving_permutations": total,
            "trivial_rules_found": trivial_found,
            "nontrivial_rules_found": nontrivial_found,
        },
        "notes": "",
        "log_excerpt": "",
    }

    with open(RESULT_YAML, 'w', encoding='utf-8') as f:
        yaml.dump(summary, f, default_flow_style=False, allow_unicode=True)

    print(f"Total bit-conserving permutations: {total}")
    print(f"Trivial rules: {trivial_found}")
    print(f"Non-trivial rules: {nontrivial_found}")
    print(f"Results written to {VALID_RULES_JSON}")
    print(f"Summary written to {RESULT_YAML}")

    print("\n--- YAML ---")
    yaml.dump(summary, sys.stdout, default_flow_style=False, allow_unicode=True)

if __name__ == "__main__":
    main()
