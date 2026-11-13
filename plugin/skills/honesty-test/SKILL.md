---
name: honesty-test
description: Measure how often the edu4self tutor passes an answer that should not pass, by grading answers with known labels through the real Grade path. Use when the learner asks to test, check or benchmark the grader ("is the grading reliable?", "run the honesty test"), or after a change to grading rules, the grade command or the model.
---

The honesty test grades answers whose correct verdict is fixed in advance and counts the mistakes. The
mistake that matters most is a **false pass**: an answer that must not pass (half-right, wrong, copied,
or trying to talk the grader into a pass) marked as passed, which turns into fake proof.

1. **Find the engine.** In the vault, `CLAUDE.md` has the check command `python3 <engine>/edu4self check
   --vault …`; the engine is the folder holding that `edu4self` file. If there is no vault or no such line,
   ask where edu4self is installed. The test lives in `<engine>/evals/grading/` (read its `README.md` for
   details). If that folder is missing, the engine predates the test: tell the learner to update.

2. **Pick the set and say the price before anything runs.** Each answer is graded by a real Claude Code
   run on the learner's own account. Measured on 2026-11-13: about $0.09 per answer at API prices; on a
   Pro or Max plan it uses the plan's limits instead of a bill.
   - `made-up`: 80 answers on 8 questions, including injection, copied hints and checker tricks (about $7, 15 min);
   - `saf`: 100 real student answers with expert labels (CC BY 4.0) (about $9, 15 min);
   - `all`: both (about $16, 30 min); `--limit N` grades only the first N of the fixed order.
   Offer the free plumbing check first: `python3 <engine>/evals/grading/run.py --fake` (no Claude, its
   verdicts mean nothing). Start a real run only after the learner says yes to the named set and price.

3. **Run it** from the engine folder, in the background if your tools allow (it prints one line per batch):

       python3 evals/grading/run.py --set <set> --yes

   It writes `evals/grading/out/<time>/`. Results are written when the run ends, so don't stop it midway.

4. **Score it:** `python3 evals/grading/score.py evals/grading/out/<time>`.

5. **Report in plain words**, nothing softened:
   - the false-pass rate per set with its 95% range, read from the upper end ("1 of 60, could be up to 9%");
   - the false-fail rate (a grader that fails everything looks safe otherwise);
   - per category, which kinds of answers got through;
   - each threshold printed as `[met]` or `[NOT met]`;
   - what the run measured: the engine commit (`git -C <engine> rev-parse --short HEAD`), the date, the
     model, and the total cost;
   - anything that makes the numbers mean less: every answer is graded once; runs that ended in an API or
     network error (e.g. `403`) graded nothing, so name them and offer to re-run just those answers instead
     of counting them as failures.

Never change a label, a case or the grading rules to improve a result. The test measures the grader as it
ships; fixing the grader is a separate change, and the test is re-run after it.
