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


---
```yaml
cached_tokens: 32322
cost_usd: 0.05016
hypothesis: 'baseline: The formal filter identifies at least one non-trivial, reversible,
  bit-conserving rule for a 1D, 3-bit neighborhood.'
input_tokens: 34399
iter: 9
metrics:
  nontrivial_rules_found: 33
  total_bit_conserving_permutations: 36
  trivial_rules_found: 3
output_tokens: 1391
status: ok
```

## iter_009: baseline: The formal filter identifies at least one non-trivial, reversible, bit-conserving rule for a 1D, 3-bit neighborhood.

**Analysis:** We are at the very beginning of the project (Phase 1, Orientation). The provided logs contain mock data and two failed attempts (`iter_006`, `iter_008`) to execute the first critical experiment. Both attempts resulted in `code_error`, meaning we have not yet gathered any data.

The project's entire foundation rests on the assumption that non-trivial rules satisfying our constraints (reversibility, bit-conservation, locality) actually exist. The immediate and only priority is to validate this assumption. We must successfully execute the "Formaler Filter" for the simplest possible case: a 1D, 3-bit neighborhood. This is the minimal validating step.

I am re-initiating this first experiment as `iter_001` to establish a clean, canonical history for this research. The hypothesis remains unchanged from the failed attempts, as it has not yet been tested.

**Task:** Create a Python script `archive/iter_001/code/generate_rules.py`. The script must be robust and not fail if no rules are found.

1.  **Define State Space**: The 8 states of a 3-bit neighborhood ('000' to '111').
2.  **Group by Hamming Weight**: Group states by the number of '1's.
    - W0: {'000'}
    - W1: {'001', '010', '100'}
    - W2: {'011', '101', '110'}
    - W3: {'111'}
3.  **Generate Rule Permutations**: A rule is a combination of permutations *within* each weight group. Iterate through all combinations of these intra-group permutations.
    - Example: `(Permutation of W0) x (Permutation of W1) x (Permutation of W2) x (Permutation of W3)`
4.  **Filter Trivial Rules**: A rule is trivial if it is one of the following:
    - **Identity**: `rule[state] == state` for all 8 states.
    - **Shift Left**: The rule's effect is identical to a circular left bit shift for all 8 states. E.g., for state 'abc', the output is 'bca'. ('101' -> '011').
    - **Shift Right**: The rule's effect is identical to a circular right bit shift for all 8 states. E.g., for state 'abc', the output is 'cab'. ('101' -> '110').
5.  **Write Outputs**:
    - Create the directory `archive/iter_001/results/`.
    - Save all valid, non-trivial rules found as a JSON list to `archive/iter_001/results/valid_rules.json`. Each item in the list is a dictionary mapping input states to output states.
    - Write a summary to `archive/iter_001/result.yaml` with these exact keys, even if the counts are zero:

**Status:** ok

**Experimenter view:** The hypothesis is confirmed. 36 total bit-conserving permutations exist across the
four Hamming-weight groups (W0: 1!, W1: 3!=6, W2: 3!=6, W3: 1!; product = 36).
After removing the 3 trivial rules (identity, shift-left, shift-right), 33
non-trivial reversible bit-conserving rules remain. Results saved to valid_rules.json.


**Metrics:** `{'total_bit_conserving_permutations': 36, 'trivial_rules_found': 3, 'nontrivial_rules_found': 33}`


---
```yaml
cached_tokens: 32545
cost_usd: 0.05442
hypothesis: 'dynamics: At least one of the 33 candidate rules produces a stable, propagating
  pattern (glider) from a single-bit initial condition.'
input_tokens: 35470
iter: 10
metrics:
  chaotic_found: 0
  decay_found: 0
  gliders_found: 22
  periodic_found: 0
  rules_tested: 33
  stable_found: 11
output_tokens: 1496
status: ok
```

## iter_010: dynamics: At least one of the 33 candidate rules produces a stable, propagating pattern (glider) from a single-bit initial condition.

**Analysis:** The foundational hypothesis was confirmed in the previous iteration (logged as iter_009): 33 non-trivial, reversible, bit-conserving rules exist for the simplest 1D, 3-bit case. This is a major milestone and the successful completion of the first step of Phase 1.

The research has now moved from a purely formal, mathematical question ("Do such rules exist?") to an empirical one ("What do these rules do?"). According to the master plan, the goal of Phase 1 is to find rules that "allow simple movement". Therefore, the immediate next step is to simulate these 33 rules and observe their behavior. We need to build a basic 1D cellular automaton simulator to test if any of these rules can support stable, propagating patterns (gliders or solitons). This is the minimal validating step to determine if our rule set has the potential for complex dynamics.

**Task:** Create a Python script `archive/iter_002/code/simulate_rules.py`. This script will function as a 1D cellular automaton simulator.

1.  **Input:** The script should load the `valid_rules.json` file from `archive/iter_001/results/`.
2.  **Simulation Setup:** For each of the 33 rules in the file:
    a. Initialize a 1D lattice of size 100 with all cells set to '0', except for a single '1' at the center (index 50). This is the initial condition.
    b. Run the simulation for 200 steps with periodic boundary conditions.
    c. In each step, for every cell, determine its new state by looking up the 3-bit neighborhood (left, self, right) in the current rule's mapping.
3.  **Analysis & Classification:** After each simulation run, classify the rule's behavior based on the final state and history. A simple classification logic:
    - `DECAY`: The lattice becomes all '0's.
    - `STABLE`: The lattice stops changing before the final step.
    - `PERIODIC`: The lattice enters a short, repeating cycle of states.
    - `GLIDER`: A contiguous pattern of bits moves consistently in one direction. You can detect this by tracking the "center of mass" of the '1' bits. If the center of mass moves at a near-constant velocity and the pattern's width is stable, classify it as a glider.
    - `CHAOTIC`: Anything else (e.g., expanding, complex, non-repeating patterns).
4.  **Output:**
    a. Create a directory `archive/iter_002/results/`.
    b. For each rule identified as `GLIDER`, save the final lattice state to `archive/iter_002/results/glider_rule_[RULE_INDEX].txt`.
    c. Write a summary file `archive/iter_002/result.yaml` with the following keys:
       - `rules_tested`: 33
       - `gliders_found`: (count of rules classified as GLIDER)
       - `stable_found`: (count)
       - `periodic_found`: (count)
       - `decay_found`: (count)
       - `chaotic_found`: (count)
       - `glider_rule_indices`: (a list of indices for the rules that produced gliders)

**Status:** ok

**Experimenter view:** Hypothesis confirmed strongly: 22 of 33 rules (67%) produce gliders from a single-bit
initial condition. The gliders fall into two symmetric groups — rules 5–16 produce
right-moving gliders (velocity +1/step) and rules 17–26 produce left-moving gliders
(velocity -1/step). The remaining 11 rules (0–4 and 27–32) are STABLE, meaning the
single '1' stays fixed.

This outcome is analytically predicted by the bit-conserving structure: the three
single-bit neighborhoods {001, 010, 100} are always permuted among themselves by each
rule. Exactly ONE of them maps to "010" (whose center bit is 1). If rule["100"]="010",
the bit shifts right (glider); if rule["001"]="010", it shifts left; if rule["010"]="010",
it stays (stable). No DECAY, PERIODIC, or CHAOTIC behavior is possible with a
single-bit initial condition under these rules.


**Metrics:** `{'rules_tested': 33, 'gliders_found': 22, 'stable_found': 11, 'periodic_found': 0, 'decay_found': 0, 'chaotic_found': 0}`

