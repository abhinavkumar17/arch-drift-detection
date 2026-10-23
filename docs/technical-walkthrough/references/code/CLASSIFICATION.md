# PR classification experiment

This is an advisory stage, not automatic routing. Existing reviews and publishing are unchanged.

The classifier tries conservative rules across every changed file. Unresolved changes can optionally go to one tool-free Pi/OpenRouter call. Invalid, uncertain, oversized, or failed classifications fall back to full review. Complete supplied diffs are included without truncation; callers must supply a complete diff.

Outputs include the PR category, reason, changed files, source (rules/model/fallback), input hash, and proposed focus areas. Focus mappings are experimental. They do not start focused reviews or assign models yet. Nothing skips review or posts to GitHub.

## Rules

- Dependency updates: configured TOML version catalogs, existing version assignments only, with an explicit `[versions]` section in hunk context. Missing section context goes to the unresolved path.
- Translations: existing simple strings in localized Android resource files. Placeholders, XML structure changes, additions/deletions, and default-language resources require further classification.
- Release metadata: exact configured files and version keys. No release files are trusted by default; configure them per repository.
- Other or mixed changes: unresolved; use the optional model or full-review fallback.

Model classifications are suggestions, not proof that changes are low risk. These categories are our policy, inspired by Cisco Foundation AI's MIT-licensed diff-review concept; no upstream code was copied. Unlike that viewer's dynamic file groups, this experiment outputs a whole-PR category.

## Run without paid calls

`python classify_pr.py --diff input.diff --output out/classification-example`

The output directory must be new. A policy JSON can override `dependency_files`, `release_files`, and `release_keys` with `--policy`.

## Optional model fallback

Add `--model <OpenRouter model ID> --sdk <installed Pi SDK index.js>`. This enables a paid classification request only when rules cannot resolve the input. Existing Pi credentials are used; no credentials are written into reports. The adapter has no tools, no automatic retry, a one-request guard, and a 2,048-token output limit. Python enforces the timeout and an approximate characters/3 input check (not a dollar cap or exact tokenizer guarantee). The complete assembled SDK context can include additional overhead beyond that prompt estimate.

The adapter also estimates the assembled SDK context before sending it and stops if that exceeds the same limit.

Saved evidence: input diff, policy, classification report, and—when used—prompt, model configuration, raw response, usage events and errors. Review these before promoting any category into live routing. No live model quality or cost claim follows from offline tests.
