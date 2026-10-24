# Translation accuracy evaluation

The current structural checks and model audit can detect known failures. They do not establish that a translation is correct. This protocol adds a separate, source-grounded review of real documents.

## Frozen comparison

`scripts/accuracy_blind.py prepare` selects prose units from six different public PDFs in `test_vault/accuracy-diverse-20261021`. Selection is deterministic by source length and source hash; it does not use the QA decision, the draft/final difference, or an evaluator's score. The PDF SHA-256 and exact extracted source are retained in `private-pack.json`. The corpus and all translations remain in ignored `test_vault` and are not part of the public repository.

For each exact source unit, the pack contains the existing Hy-MT2 draft and hybrid final. `scripts/accuracy_blind.py qwen` runs the same source through the installed Qwen model alone and saves each result immediately. A failed Qwen item remains visibly incomplete; it is not silently dropped into a two-way accuracy comparison. This is a comparison of the deployed workflows, not an isolated model architecture test: the hybrid has an additional review stage and may have more context.

The reproducible pilot commands are:

```powershell
.venv\Scripts\python.exe scripts/accuracy_blind.py prepare --output test_vault/accuracy-blind-ko
.venv\Scripts\python.exe scripts/accuracy_blind.py qwen --output test_vault/accuracy-blind-ko
.venv\Scripts\python.exe scripts/accuracy_blind.py checks --output test_vault/accuracy-blind-ko
.venv\Scripts\python.exe scripts/accuracy_blind.py export --output test_vault/accuracy-blind-ko
```

The `checks` output separates missing Qwen results from automated source/target contract flags; it is not a semantic quality score. The pilot attempted 12 units from six documents. One scan-derived unit failed Qwen's formula/style placeholder validation, so the first blind export has 11 complete triplets. This failure remains in the private pack and structural report.

After all three outputs exist, `scripts/accuracy_blind.py export` writes `review-blind.json` with method names replaced by deterministic A/B/C labels, and a separate `answer-key.json`. The reviewer must compare each candidate to the English source and record major/minor errors. Each issue needs an exact source quote, explanation, and one of these types: omission, addition, reversed meaning, wrong relation, terminology, other. For scientific claims, negation, conditions, direction, actor, quantitative relation, and unsupported claims are major errors. Stylistic awkwardness without a meaning change is minor. The reviewer should use the original PDF as needed to detect source extraction mistakes before judging translation.

An annotation file has this shape:

```json
{
  "reviewer_id": "independent-reviewer-id",
  "independent_of_model_generation": true,
  "items": [
    {
      "item_id": "copy-id-from-review-blind",
      "options": {
        "A": [{"type": "omission", "severity": "major", "source_quote": "exact English substring", "reason": "what was lost"}],
        "B": [],
        "C": []
      }
    }
  ]
}
```

`scripts/accuracy_blind.py score --annotations <file>` refuses incomplete, modified, or unattested reviews. It counts human-labelled errors per method after matching the withheld key. A reviewer must not see the answer key until annotations are locked. The attestation is a declared provenance field, not proof of independence.

The 12-unit pilot is a way to test the procedure and surface failure types. It is too small and selectively sampled to claim application-wide accuracy, and the current author/model cannot create independent expert gold by grading its own output. Before making accuracy claims, obtain expert review on a much larger paper-disjoint corpus across fields and layouts, report uncertainty intervals, and measure **major mistranslation miss rate** against the application's QA decisions alongside omission and false-alarm rates. Compare time and GPU use on the same document set separately from linguistic quality.
