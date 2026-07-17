"""Runtime diff harness (Stage 4: VALIDATE, dynamic half). NOT YET IMPLEMENTED.

Will run the original and converted pipelines against sample data (converted
side via pan/kitchen or the PDI engine API), diff the outputs row-by-row, and
score output parity per step. No auto-deploy: results feed the migration
report for human review.
"""


class DiffHarness:
    def run(self, original_output_path: str, converted_output_path: str) -> None:
        raise NotImplementedError(
            "Runtime output diffing is planned once the generator emits runnable KTRs."
        )
