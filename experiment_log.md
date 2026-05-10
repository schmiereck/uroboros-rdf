# Experiment Log
<!-- Append-only. Eintragstrenner: \n---\n zwischen YAML-Blöcken. -->

---
```yaml
cached_tokens: 0
cost_usd: 0.00875
hypothesis: '[mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0'
input_tokens: 1000
iter: 2
metrics:
  mock_value: 3.0
output_tokens: 500
status: ok
```

## iter_002: [mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0

**Analysis:** [Mock] Iteration 3. All systems nominal.

**Task:** Create archive/iter_003/code/run.py that prints 'hello from iter 3' and exits 0.

**Status:** ok

**Experimenter view:** [Mock] Iteration 2 completed. No real computation.

**Metrics:** `{'mock_value': 3.0}`


---
```yaml
cached_tokens: 0
cost_usd: 0.00875
hypothesis: '[mock] warmup-500: adding 500-step warmup reduces val_loss by ≥2%'
input_tokens: 1000
iter: 1
metrics:
  mock_value: 1.5
output_tokens: 500
status: ok
```

## iter_001: [mock] warmup-500: adding 500-step warmup reduces val_loss by ≥2%

**Analysis:** [Mock] Iteration 2. All systems nominal.

**Task:** Create archive/iter_002/code/run.py that prints 'hello from iter 2' and exits 0.

**Status:** ok

**Experimenter view:** [Mock] Iteration 1 completed. No real computation.

**Metrics:** `{'mock_value': 1.5}`


---
```yaml
cached_tokens: 0
cost_usd: 0.00875
hypothesis: '[mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0'
input_tokens: 1000
iter: 2
metrics:
  mock_value: 3.0
output_tokens: 500
status: ok
```

## iter_002: [mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0

**Analysis:** [Mock] Iteration 3. All systems nominal.

**Task:** Create archive/iter_003/code/run.py that prints 'hello from iter 3' and exits 0.

**Status:** ok

**Experimenter view:** [Mock] Iteration 2 completed. No real computation.

**Metrics:** `{'mock_value': 3.0}`


---
```yaml
cached_tokens: 0
cost_usd: 0.00875
hypothesis: '[mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0'
input_tokens: 1000
iter: 3
metrics:
  mock_value: 4.5
output_tokens: 500
status: ok
```

## iter_003: [mock] lr-2e4: doubling LR to 2e-4 with warmup achieves val_loss < 3.0

**Analysis:** [Mock] Iteration 4. All systems nominal.

**Task:** Create archive/iter_004/code/run.py that prints 'hello from iter 4' and exits 0.

**Status:** ok

**Experimenter view:** [Mock] Iteration 3 completed. No real computation.

**Metrics:** `{'mock_value': 4.5}`


---
```yaml
cached_tokens: 31883
cost_usd: 0.04384
hypothesis: 'baseline: The formal filter identifies at least one non-trivial, reversible,
  bit-conserving rule for a 1D, 3-bit neighborhood.'
input_tokens: 32587
iter: 6
metrics: {}
output_tokens: 1284
status: code_error
```

## iter_006: baseline: The formal filter identifies at least one non-trivial, reversible, bit-conserving rule for a 1D, 3-bit neighborhood.

**Analysis:** We are in the Orientation phase, starting from iteration 1. The provided logs and state are mocks from a different project and will be ignored.

The research goal is to discover emergent physics from simple, local, reversible rules on a discrete lattice. The strategic plan correctly identifies the first step: validating the core constraints in a 1D environment (Phase 1). Before we can test for gliders, oscillations, or any complex behaviour, we must first prove that our constraints (reversibility and bit-conservation) permit the existence of any non-trivial dynamics at all.

Therefore, the minimal validating step is to build and run the "Formaler Filter" for the simplest case: a 1D, 3-bit neighborhood (a cell and its left/right neighbors). This experiment will either produce the first candidate "Naturkonstanten" or refute our initial assumptions about the rule constraints.

**Task:** Create a Python script `archive/iter_001/code/generate_rules.py`.

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

**Status:** code_error

**Experimenter view:** No YAML block found in output.

**Metrics:** `{}`


---
```yaml
cached_tokens: 32099
cost_usd: 0.04859
hypothesis: 'baseline: The formal filter identifies at least one non-trivial, reversible,
  bit-conserving rule for a 1D, 3-bit neighborhood.'
input_tokens: 33489
iter: 8
metrics: {}
output_tokens: 1489
status: code_error
```

## iter_008: baseline: The formal filter identifies at least one non-trivial, reversible, bit-conserving rule for a 1D, 3-bit neighborhood.

**Analysis:** We are at the beginning of Phase 1 (Orientation). The previous experiment logs appear to be mock data from a different project and can be disregarded. The first real attempt (logged as iter_006) was to establish a baseline by finding all valid rules for the simplest 1D, 3-bit case. This attempt failed with a `code_error`, meaning we have not yet produced any data to confirm or refute our most fundamental hypothesis: that non-trivial, reversible, bit-conserving rules actually exist.

The immediate and only priority is to successfully execute this first experiment. We cannot build upon a foundation that has not been laid. The scientific question remains the same, but the task is now to debug and robustly implement the "Formaler Filter" to get our first piece of evidence. This is a classic "Observation Before Hypothesis" step; we need to see what the rule space looks like before theorizing about it. I will re-number this attempt as `iter_001` to establish a clean, canonical history for this research project.

**Task:** Create a Python script `archive/iter_001/code/generate_rules.py`. This script must be robust and handle the case where no rules are found without crashing.

1.  **Define State Space**: The state space for a 1D, 3-bit neighborhood consists of 8 states: '000', '001', '010', ..., '111'.
2.  **Group by Hamming Weight**: Group these states by their Hamming weight (number of '1's).
    - Weight 0: {'000'}
    - Weight 1: {'001', '010', '100'}
    - Weight 2: {'011', '101', '110'}
    - Weight 3: {'111'}
3.  **Generate Permutations**: A rule is a permutation of the 8 states. To ensure bit-conservation, we only need to find permutations *within* each Hamming weight group. Generate all permutations for each group (e.g., all 3! = 6 permutations for the weight-1 group).
4.  **Construct Full Rules**: Iterate through all combinations of these intra-group permutations to construct the full rule tables.
5.  **Filter Trivial Rules**: Identify and count rules that are:
    - **Identity**: Every state maps to itself.
    - **Global Shift Left**: The rule is equivalent to `output = roll(input, -1)`. For example, '101' -> '011'.
    - **Global Shift Right**: The rule is equivalent to `output = roll(input, 1)`. For example, '101' -> '110'.
6.  **Write Outputs**:
    - Create `archive/iter_001/results/`.
    - Save all valid, non-trivial rules to `archive/iter_001/results/valid_rules.json`. This should be a list of dictionaries, where each dictionary represents a rule (e.g., `[{'000':'000', '001':'010', ...}, ...]`).
    - **Crucially**, create `archive/iter_001/result.yaml` with a summary, even if no rules are found. The file must contain:

**Status:** code_error

**Experimenter view:** No YAML block found in output.

**Metrics:** `{}`

