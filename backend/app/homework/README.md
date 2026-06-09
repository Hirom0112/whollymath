# app/homework/

The homework-scan flow: assign → QR → photo OCR → read-back → grade → ★★.
Mathpix provides handwriting OCR when `MATHPIX_APP_KEY` is set; otherwise a
deterministic `MockScanner` stands in.

The OCR only **proposes** what was written — **SymPy decides correctness** (the OCR
never grades; invariant 2).
