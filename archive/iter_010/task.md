# Task – iter_010

**Hypothesis:** dynamics: At least one of the 33 candidate rules produces a stable, propagating pattern (glider) from a single-bit initial condition.

## Task

Create a Python script `archive/iter_002/code/simulate_rules.py`. This script will function as a 1D cellular automaton simulator.

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


## Success Criteria

- The script successfully runs and classifies all 33 rules without error.
- The `result.yaml` file is created with all specified keys.
- The value of `gliders_found` is greater than 0.

## Required Output

You MUST end your final response with a ```yaml``` code block in this exact schema (the orchestrator reads it to determine success):

```yaml
status: ok  # or experiment_failed or code_error
artifacts:
  - path/to/created/file  # relative to the repo root
metrics:
  key: value  # any numeric results
log_excerpt: |  # last ~20 lines of relevant output
  ...
experimenter_view: |  # your qualitative observations
  ...
notes: brief technical remark
```
