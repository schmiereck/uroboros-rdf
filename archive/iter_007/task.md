# Task – iter_007

**Hypothesis:** fix: The formal filter successfully enumerates all non-trivial, reversible, bit-conserving 1D 3-bit rules.

## Task

Create a Python script `archive/iter_007/code/generate_rules.py`. This script is a retry of the failed task in iter_006.

The script must:
1.  Define the state space for a 1D, 3-bit neighborhood (8 states: '000' through '111').
2.  Group these 8 states by their Hamming weight (number of '1's).
3.  Generate all possible permutations for the states within each Hamming weight group. A full rule is a combination of one permutation from each group.
4.  Iterate through all possible valid rules. For each rule, check if it is "trivial". A trivial rule is either:
    a) The identity rule (e.g., '001' -> '001', '010' -> '010', ... for all states).
    b) A global shift left (e.g., '110' -> '100').
    c) A global shift right (e.g., '011' -> '001').
5.  Count the total number of valid bit-conserving rules, the number of trivial rules found, and the number of non-trivial rules.
6.  Write all valid, non-trivial rules to `archive/iter_007/results/valid_rules.json`. The format should be a list of dictionaries, where each dictionary represents a rule (e.g., `[{'000':'000', '001':'100', ...}, ...]`).
7.  **Crucially**, write a summary YAML file to `archive/iter_007/result.yaml` with the final counts. The file must contain these exact keys:
    - `total_bit_conserving_permutations`
    - `trivial_rules_found`
    - `nontrivial_rules_found`
8.  Add print statements to stdout to show progress (e.g., "Found X permutations for weight 1"). This will help debug in case of another failure.


## Success Criteria

- Script exits with status 0.
- The file `archive/iter_007/result.yaml` is created and is valid YAML.
- The key `nontrivial_rules_found` exists in `result.yaml` and its value is an integer.
- The file `archive/iter_007/results/valid_rules.json` is created and contains a valid JSON list.