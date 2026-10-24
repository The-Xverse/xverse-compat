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
