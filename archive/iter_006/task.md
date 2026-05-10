# Task – iter_006

**Hypothesis:** baseline: The formal filter identifies at least one non-trivial, reversible, bit-conserving rule for a 1D, 3-bit neighborhood.

## Task

Create a Python script `archive/iter_001/code/generate_rules.py`.

This script must:
1. Define the state space for a 1D, 3-bit neighborhood (8 states from '000' to '111').
2. A "rule" is a permutation of these 8 states. The script must iterate through permutations that satisfy the bit-conservation constraint: the Hamming weight of an input state must equal the Hamming weight of its corresponding output state. (e.g., all states with weight 1 can only be permuted among themselves).
3. Filter out and count "trivial" rules:
    - The identity rule (every state maps to itself).
    - The global-shift rule (equivalent to shifting the entire lattice left or right, e.g., '101' -> '010').
4. Write all valid, non-trivial rules found to `archive/iter_001/results/valid_rules.json`. Each rule should be represented as a map from input state (string) to output state (string).
5. Write a summary of the findings to `archive/iter_001/result.yaml`, including these keys:
    - `total_bit_conserving_permutations`
    - `trivial_rules_found`
    - `nontrivial_rules_found`


## Success Criteria

- The script completes successfully.
- `archive/iter_001/result.yaml` is created and contains the required counts.
- The value for `nontrivial_rules_found` is greater than 0.