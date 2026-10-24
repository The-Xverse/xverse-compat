# Review log: Phase 8 WP-09 increment #2, the shared NumPy preprocessing function (xverse-compat)

Candidate `candidate/phase8-wp09-preprocess-20261024`, base main `95e9e7a`. Specification:
- thesis `specs/002-assured-aeb/design/wp09-training-pipeline.md` §4 ("Shared preprocessing") and §7 (freezing),
  decided in the `decisions.md` row "WP-09 training pipeline" (15:15, under the author's delegation, flagged for
  review);
- `design/wp08-inference-stack.md` §9 (one shared preprocessing function; the logits-only graph);
- compat WP-06 (`FrameResult`, the declared frame format) and WP-08 (`inference/loader.py`, the U4 lock with
  numpy 2.5.4).
The module sits beside the loader, because both U4 and the offline training import it. Findings are recorded before
repairs. This is an engineering increment verified offline; no parameter value is set (AD-02).

## Findings

1. **Design record: `xverse_compat.inference.preprocess` (2026-10-24 15:22:18, before any code).**
   - **Parameter record `xverse-compat.preprocess/1`** (no defaults; the values are AD-02 protocol values and stay
     TODO). It has exactly these members:
     - `schema`;
     - `input`: `{width, height, encoding}`, which must equal the WP-06 frame-format record, with `encoding`
       `bgra8` only;
     - `crop`: `{x, y, width, height}` in input pixels, fully inside the input;
     - `resize`: `{method, width, height}`, with `method` one of:
       - `area-integer`: each output pixel is the exact mean of a `kx × ky` block; it requires the crop size
         to be an integer multiple of the output size;
       - `nearest`: the source index is `floor((2·i + 1) · in / (2 · out))`, in integer arithmetic;
     - `channels`: the output order, `rgb` or `bgr`; alpha is dropped;
     - `normalize`: `{mean: [3], std: [3]}`, in the 0..1 scale, finite, with `std > 0`; per output channel.
     Every member is type-checked, and anything unknown, missing, non-finite or bool is refused (`ValueError`).
   - **Computation (deterministic by construction).**
     1. View the bytes as `uint8` `[H, W, 4]` and crop.
     2. Resize: `area-integer` sums each block in `int64` (exact), and `nearest` gathers by integer index tables.
     3. Select and order the channels.
     4. Normalise elementwise in **float64**, as `y = (s / (k · 255) − mean_c) / std_c`, where `s` is the block sum
        (`k = 1` for `nearest`), then cast once to **float32**.
     5. Lay out as NCHW `[1, 3, out_h, out_w]`, C-contiguous.
     There is no reduction in floating point, and every float operation is a single IEEE-754 elementwise operation, so
     the result is bit-exact for the same input, parameters and numpy build. Equality with an independent pure-Python
     computation of the same formula is tested.
   - **Input from WP-06.** `preprocess_frame(result, frame_format, params)` requires `result.status ==
     "verified"` and uses `result.pixels()`. Any other status is refused, and so is a byte length other than
     `4·W·H` or a frame format that differs from `params.input`.
   - **numpy.** It is imported inside the functions, so the module imports the standard library only and the compat
     test venv can import it. The numpy version in use is part of the binding (below). The pin is the U4 lock's
     `numpy==2.5.4`, and the WP-09 #3 training venv must pin the same version (a requirement handed to #3).
   - **Binding into the model digest.** `binding(params)` returns the `metadata_props` entries that WP-09 #4 writes
     into the ONNX file:
     - `xverse.preprocess.schema`;
     - `xverse.preprocess.paramsSha256` (canonical JSON of the record);
     - `xverse.preprocess.codeSha256` (the SHA-256 of `preprocess.py`'s source bytes);
     - `xverse.preprocess.numpy`.
     Because the metadata is inside the file, the model's SHA-256 (WP-08 `load_model`) binds them.
     `verify_binding(metadata, params)` refuses a model whose entries differ from the parameters, code and numpy in
     use. U4 calls it after `load_model`, and WP-13 wires it. The interface is defined now; #4 uses it.
   - **Tests (offline).**
     - Standard library, in the compat suite: parameter refusals; the binding's digests and their sensitivity to every
       parameter; `verify_binding` mismatches; the U4 lock pins numpy.
     - In the U4 inference venv (the real 3.13.13 interpreter with `PYTHONPATH`, as the WP-08 tests), skipping
       cleanly when it is absent:
       - both resize methods against the pure-Python reference, bit for bit;
       - shape, dtype and layout;
       - the crop and channel order;
       - determinism within one process and across fresh processes;
       - the `preprocess_frame` refusals;
       - an ONNX test model carrying the binding: its digest changes with any parameter change, ONNX Runtime exposes the
         entries (`custom_metadata_map`), and `verify_binding` accepts the matching parameters and refuses others.
2. **Implementation of finding 1 (2026-10-24 15:26:12).**
   - **Change.**
     - `src/xverse_compat/inference/preprocess.py` (new): `load_params` returning `PreprocessParams`,
       `preprocess`, `preprocess_frame`, `binding`, `verify_binding` and `code_sha256`. It imports only the
       standard library at module level.
     - `tests/inference/minimal_onnx.py`: `model_bytes(metadata_in=None)` adds sorted `metadata_props` entries.
       With no argument the bytes are unchanged; the WP-08 fixture digest `29f7e86b…` still holds and its test passes.
     - `tests/inference/preprocess_probe.py` (new, venv side) and `tests/inference/test_preprocess.py` (new).
   - **Tests.** 24 tests.
     - 19 run everywhere:
       - 16 refused records: missing or extra members, wrong schema, encoding, sizes, bools, a crop outside the input,
         a non-integer `area-integer` factor, an unknown method or channel order, bad `mean`/`std`, `None`;
       - the binding covers every parameter (six variants give seven distinct digests), the code hash and the numpy
         version; `verify_binding` refuses each mismatch and an empty map;
       - the U4 lock pins `numpy==2.5.4`;
       - the module's standard-library imports.
     - 5 run in the U4 venv and skip cleanly without it (`XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`: 19 passed,
       5 skipped):
       - **both methods** (`area-integer` 8×6 to 4×3; `nearest` with a 7×5 crop at (1, 1) to 3×2, `bgr`) are
         **bit-equal to an independent pure-Python implementation** cast with `struct`, and equal on repetition, with
         shape `[1, 3, h, w]`, float32 and C-contiguous;
       - bit-exact across three fresh processes;
       - `preprocess_frame` gives the same tensor through a `verified` WP-06 `FrameResult`, and refuses
         `mismatch`, `missing`, a differing frame format and a short buffer;
       - **the binding in a model:** the test ONNX model carries the four entries; ONNX Runtime exposes them through
         `custom_metadata_map`; `verify_binding` passes; numpy is 2.5.4; and the two parameter sets give two model
         digests.
   - **Mutation checks (not committed; restored).** Each fails tests:
     - float32 arithmetic instead of the float64 step: 2;
     - `nearest` with `floor(i·in/out)`: 1;
     - a binding with a constant code hash: 1.
   - **Venv integrity.** No `__pycache__` or `.pyc` in the U4 venv after the runs (the probe runs with `-B`). The
     WP-08 identity test, which recomputes the venv tree digests, still passes.
   - **Suite.** With the venv: 443 passed, 39 subtests (base `95e9e7a`: 419). Without it: 433 passed, 10 skipped.
   - **Residuals.**
     - R-1. Every parameter value is `TODO: author decision` (AD-02): crop, method, output size, channel order,
       `mean` and `std`. The `input` member must equal the WP-06 frame format, which AD-02 also fixes.
     - R-2. Bit-exactness is shown **on this host** for numpy 2.5.4. The method uses only exact integer arithmetic and
       single elementwise IEEE-754 operations, but no claim is made for other hosts or numpy builds. The WP-09 #3
       training venv must pin `numpy==2.5.4`, and `verify_binding` refuses a model bound under another numpy version.
     - R-3. Two resize methods only, and no colour transform beyond channel selection. `area-integer` needs integer
       factors, and `nearest` aliases. The choice is an AD-02 item.
     - R-4. The code hash covers this module's source bytes, so any edit, even a comment, invalidates every bound model.
       That is intended; freezing makes the module immutable for the campaign.
     - R-5. Writing the binding into the real model is WP-09 #4; calling `verify_binding` in U4 after `load_model` is
       WP-13.
     - R-6. The per-frame cost at 800 × 600 is not measured (V-5, D-4c).
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 15:29:31).** Reviewer: an independent Claude agent that did
   not write the increment. Scope: `d3d5805` and `426aa05` on `95e9e7a`. **Verdict: PASS WITH NOTES.** All notes are
   LOW, and **nothing blocks the merge**. The merge still needs the author's or the coordinator's acceptance, which
   this finding does not give.
   - **Independent checks.**
     - **With the U4 venv** (`…/xverse-aeb-inference-20261024`): **443 passed, 39 subtests**.
     - **Without it** (`XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`): **433 passed, 10 skipped, 39 subtests**.
       The 10 skips are the 5 new venv cases plus the existing WP-08 venv cases.
     - **The U4 venv stays bytecode-free.** It held 0 `__pycache__` and `.pyc` entries before the runs and still
       held 0 after both suite runs and my own probe (all with `-s -B`). The WP-08 identity tests, which recompute
       the venv tree digests, pass.
     - **WP-08 fixture digest.** `model_bytes()` and `model_bytes({})` both still hash to `FIXTURE_DIGEST`
       (`sha256:29f7e86b…`). The candidate's `model_bytes()` is also byte-identical to base `95e9e7a`'s.
     - **numpy pin.** The lock has `numpy==2.5.4` with a hash (`tools/inference/u4-inference.lock:5`). The venv
       holds `numpy-2.5.4.dist-info`, and the binding probe reports 2.5.4.
     - **Bit-exactness at realistic size (my own probe in the U4 venv, `-s -B`).** On a random 800 × 600 BGRA frame
       with test values for mean and std, three cases are **bit-equal** to the record's pure-Python reference:
       - `area-integer` 800 × 600 to 200 × 150 (k = 16);
       - `area-integer` on a 640 × 480 crop at (80, 60) to 320 × 240;
       - `nearest` on a 600 × 600 crop at (100, 0) to 224 × 224, `bgr`.

       The record's cases are 8 × 6 and do not exercise numpy's vectorised loops with long runs and tails. These
       cases do. The timings were 2–16 ms after the first call; they are not a measurement (R-6).
     - **The `preprocess/1` record.** It has exact members at every level and no defaults. Booleans are excluded
       (`_int` uses `type(...) is int`, and `mean`/`std` require `int` or `float`). The crop must lie inside the
       input, `area-integer` needs integer factors, the method and channels are enumerated, and `mean` and `std` are
       3 finite numbers with `std > 0` (`preprocess.py:61-93`). The 16 refusal cases cover these.
     - **The computation.**
       - The crop and resize use exact integer arithmetic: `area-integer` sums in `int64` blocks, and `nearest`
         uses integer index tables with centre sampling (`:113-124`).
       - Float64 is used in one elementwise expression, `(s/(k·255) − mean)/std`, with no reduction. The sums are
         exact in float64 (< 2^53). The result is cast once to float32, in C-contiguous NCHW (`:128-129`).
       - "Single float64 step" means one expression of three correctly rounded IEEE operations. That is what makes
         it reproducible, and the reference applies them in the same order.
     - **Binding.** `binding` gives the four `xverse.preprocess.*` entries: schema, `paramsSha256` (canonical JSON),
       `codeSha256` (source bytes) and the numpy version. Inside the ONNX file they are covered by the WP-08 model
       digest, which the probe shows: the two parameter sets give two model digests, and ONNX Runtime exposes them
       through `custom_metadata_map`. `verify_binding` compares exactly those four keys and refuses any difference or
       a missing entry (`:146-164`).
   - **Notes (LOW; none blocks the merge).**
     - **L1. "Only verified frames" trusts the status label.** `preprocess_frame` checks `status == "verified"` and
       that `pixels()` is non-`None` (`preprocess.py:135-137`). It does not re-check the pixels against the result's
       own `rawSha256`, `actualSha256` and `rawLength`.
       - The probe itself builds a `FrameResult.with_pixels(raw, "verified", 1, "0"*64, ...)` whose `rawSha256` is
         not the hash of `raw`, and it is accepted (`preprocess_probe.py:58`).
       - The WP-06 receiver is the only real producer, so this is defence in depth. **Fix.** Refuse unless
         `sha256(pixels) == rawSha256 == actualSha256` and `len(pixels) == rawLength`, at one hash per frame, and
         give the probe a true hash.
     - **L2. The frame format is checked loosely.** `_check_format` compares `schema`, `width`, `height` and
       `encoding`, but tolerates extra members (`preprocess.py:96-99`). Reusing the WP-06 `frames.load_format`
       (exact members, the `MAX_DIMENSION` tool bound) would keep one definition of the record.
     - **L3. The reference is not independent of the record.** The pure-Python reference shares the parameter
       parsing (`PreprocessParams`) and the same formula, including the index rule. It shows numpy and Python
       agree; it does not show the formula is the intended one. A small hand-computed expected tensor would pin the
       semantics, for example one `area-integer` block mean and one `nearest` index at a crop offset.
     - **L4 (scope). `nearest` uses centre sampling.** It samples at `floor((2i+1)·in/(2·out))`, which is not the
       `floor(i·in/out)` rule of, for example, OpenCV `INTER_NEAREST`. Both U4 and training import this one
       function, so that is consistent. Any external tool or dataset preprocessing must not be used instead; R-3
       could state this.
   - **Residuals R-1 to R-6.** They are honest and correctly scoped. R-2 is now strengthened: bit-equality also holds
     at 800 × 600 on this host and build. The proposed additions are L1 and L2 under R-5 (for WP-13), and L3 and L4
     under R-3.

## 4. Acceptance (written at 15:30:39 2026-10-24)

- **Accepted** under the author's delegation of 2026-10-24 (thesis `specs/002-assured-aeb/decisions.md` §G and
  the "WP-09 training pipeline" row). It is flagged for the author's review.
- **Basis:** finding 3, PASS WITH NOTES, all LOW. The suite gives 443 passed with the U4 venv and 433 passed with 10
  skipped without it. The reviewer independently confirmed bit-exactness at 800×600.
- **Declared and carried:**
  - L1 goes to WP-13: U4 re-verifies the frame bytes against `rawSha256` on receipt, before `preprocess_frame`,
    because U4 reads frames across a process boundary. The probe's fake hash is a test artefact.
  - L2: reusing WP-06's `load_format` is optional hardening.
  - L3: a hand-computed expected tensor is added with WP-09 #4.
  - L4: `nearest` uses centre sampling (R-3), which is valid while U4 and training share this one function.
- **Merged** into compat main and pushed (see the merge commit).
