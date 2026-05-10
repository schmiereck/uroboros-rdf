# Task – iter_008

**Hypothesis:** baseline: The formal filter identifies at least one non-trivial, reversible, bit-conserving rule for a 1D, 3-bit neighborhood.

## Task

Create a Python script `archive/iter_001/code/generate_rules.py`. This script must be robust and handle the case where no rules are found without crashing.

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
      

## Success Criteria

