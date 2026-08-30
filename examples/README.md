# Example: a real journal paper

[`vessel-movement-prediction.md`](vessel-movement-prediction.md) is the output of
running PdfToMd over a 14-page open-access paper. It is here so you can see what
the converter actually produces on real input — a two-column LaTeX article with
figures, running headers, and an unruled table — rather than only on the
synthetic fixtures.

**Source:** S. Mehri, A. A. Alesheikh and A. Basiri, "A Contextual Hybrid Model
for Vessel Movement Prediction," *IEEE Access*, vol. 9, pp. 45600–45613, 2021.
[doi:10.1109/ACCESS.2021.3066463](https://doi.org/10.1109/ACCESS.2021.3066463) ·
[IEEE Xplore](https://ieeexplore.ieee.org/document/9380635) ·
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

The source PDF is not committed — fetch it from the link above if you want to
reproduce the conversion:

```bash
python -m pdftomd.cli paper.pdf -o examples
```

## What it produced

| | |
|---|---|
| Pages | 14 |
| Markdown | 67,009 characters (~16,750 tokens) |
| Figures kept | 15 (425 KB, in a sibling folder) |
| Images filtered | 16 — logos, rules, publisher marks |
| Running headers removed | 13 |
| Time | ~23 seconds |

## What this example honestly shows

**The token saving depends entirely on the document.** This paper is dense
text with few figures, so the Markdown (~16,750 tokens) is *not* dramatically
cheaper than sending 14 page images (~10,500–22,400 tokens, depending on the
model's per-image rate). Roughly a wash on volume alone.

Where it does win, clearly:

- **The 15 figures cost ~120 tokens as links instead of ~16,500 inlined** —
  that is the single biggest effect, and it is the reason `extract` is the
  default. The pictures are still on disk when a question needs one.
- **`--images embed` would produce 10× the file** (~165,000 tokens). The
  measurement is in this repo rather than in a claim.
- **The text is searchable and quotable.** A model can cite a sentence from
  section IV; it cannot quote a picture of one.
- **Running headers are gone.** "S. Mehri et al.: Contextual Hybrid Model…"
  appeared on all 13 body pages and is now removed once, not repeated.

The honest summary: **for figure-heavy documents the saving is large; for
dense prose it is modest, and the real gain is that the text becomes
searchable.** A raw text dump of the same PDF is about the same size — what
PdfToMd adds over that is heading structure, image handling, table conversion,
and furniture removal.

## Known weaknesses this example exposes

Worth seeing, since they are the honest limits of the tool:

- **The unruled table on page 11 was not converted.** PyMuPDF's table detection
  needs ruled lines; this paper's table uses whitespace alignment. The `text`
  detection strategy finds it but also shreds ordinary two-column prose into
  false tables, so it is deliberately not used. Its content survives as text.
- **Figure captions run into body text** rather than attaching to their figure.
- **Author affiliations and the abstract are one long paragraph**, because they
  are a single text block in the PDF.
- **Ligatures are preserved** (`ﬁ`, `ﬂ`) rather than expanded, which is correct
  for display but can affect naive text search.
