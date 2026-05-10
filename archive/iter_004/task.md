# Task – iter_004

**Hypothesis:** baseline: a 1D CA with a staggered 3-bit cyclic shift rule propagates a single bit at a constant velocity of 1 cell per step

## Task

1.  **Create Rule Definition:**
    In `archive/iter_001/code/`, create a script `generate_rule.py`.
    - It should define the 'cyclic right shift' permutation rule for 3-bit blocks. This rule only affects blocks with Hamming weight 1 or 2.
    - Rule logic:
      - `001` (1) -> `010` (2)
      - `010` (2) -> `100` (4)
      - `100` (4) -> `001` (1)
      - `011` (3) -> `101` (5)
      - `101` (5) -> `110` (6)
      - `110` (6) -> `011` (3)
      - All other inputs map to themselves.
    - The script should serialize this rule as a JSON lookup table to `archive/iter_001/code/rule.json`.

2.  **Create Simulator:**
    In `archive/iter_001/code/`, create `simulate.py`.
    - Initialize a 1D numpy array of 100 cells, all zero except for a `1` at index 50.
    - Load the rule from `rule.json`.
    - Run the simulation for 20 steps with periodic boundary conditions.
    - **Update Scheme:** Use a staggered 3-cell block partitioning:
      - For even steps (0, 2, ...), apply the rule to non-overlapping blocks `[0,1,2], [3,4,5], ...`.
      - For odd steps (1, 3, ...), apply the rule to non-overlapping blocks `[1,2,3], [4,5,6], ...`.
    - **Verification:** After each step, assert that `numpy.sum(grid) == 1`. If not, raise an error.
    - **Logging:**
      - Save the grid state at t=0, t=10, and t=20 to `archive/iter_001/grid_t0.txt`, `.../grid_t10.txt`, and `.../grid_t20.txt`.
      - Write the final index of the '1' bit to `archive/iter_001/result.yaml` in the format `{final_position: 70}`.


## Success Criteria

- Simulation completes 20 steps without assertion errors.
- The total bit count of the grid is exactly 1 at every step.
- The final position of the '1' bit is 70.
- The `result.yaml` file is present and contains `final_position: 70`.