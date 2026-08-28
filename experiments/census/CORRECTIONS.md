# Corrections to reported quantities

This file records every number that changed after the records were sealed, why
it changed, and how to check the correction from this directory alone. The
records themselves are unchanged: each correction is a reading error in the
manuscript, not a change to the evidence.

Run `python3 verify_reported_quantities.py --check` to assert the corrected
values. Each correction below is now covered by a named check, so asserting the
superseded value makes the script exit non-zero.

## 1. Items answered correctly in neither branch: 21 -> 19

The Discussion reported that, under the generator as answerer, "21 of 68
admitted items are answered correctly in neither branch". The correct count is
**19**.

21 is `n - text_image` (68 - 47), which is the number not answered *with* the
figure. That set is the 19 answered in neither branch plus the 2 answered only
*without* the figure. The discordance decomposes as both = 31, image-only = 16,
text-only = 2, neither = 19.

Check: `qwen neither branch`. The script now prints both quantities side by
side, since confusing them is what produced the error.

## 2. Structural audit -> mechanical cue scan: 44/25 -> 39/33

The Results section reported "a structural audit finds 44 of the 68 admitted
items referring to the figure (17 of 22, 12 of 17, 7 of 15 and 8 of 14) and 25
whose answer is a long verbatim span of `T_c`". No record backing those counts
exists for this run.

Two rules were calibrated against the only comparable audit in the project, a
single-rater reading of an earlier 50-item run, and reproduce its per-item
labels exactly, 50 of 50 on both measures. Applied to the 68 admitted items of
this run they give **39** questions naming the figure (**15/22, 11/17, 7/15,
6/14**) and **33** answers repeating at least 20 characters of `T_c`.

A sweep of all 255 non-empty subsets of the observed figure-cue vocabulary
reproduces the published per-arm split 17/12/7/8 zero times, so the discrepancy
is not a difference in cue choice. Both deviations ran in the paper's favour:
more items reported as citing the figure, fewer answers reported as repeating
the prose.

The manuscript now reports the reproduced counts and labels the measure a
mechanical cue scan rather than an audit or a review.

Checks: `cue scan cites figure total`, `cue scan verbatim total`, and the four
per-arm counts.

## 3. Conclusion hedge on the image-quoting endpoint

The Conclusion stated that no quotation of image-rendered text "occurred" under
the contract, at 0 of 24 attempts. The count is correct as instrumented, but it
rests on a contiguous-substring test, and the contract arm's single unresolved
attempt has an OCR overlap of 0.94 against its own figure crops. Were that
attempt counted as confirmed image quoting, the arm would read 1 of 24.

The wording is now "no quotation ... was confirmed", with the unresolved attempt
stated in the same sentence. The taxonomy counts are unchanged and remain
checkable: `image-quoting ECM` and `unresolved total`.

## 4. Frame extensibility: superseded discovery pass replaced by the screened one

The Limitations paragraph attributed the frame's shortfall to the acquisition
pass and supported that with "a narrow re-scan returned 56 further candidate
sources, 23 in the textbook class the sweep excluded, unscreened and of unknown
yield".

Both halves were stale. The 56-record pass read only the first page of the
catalogue's pager and was superseded by a paginated pass that enumerated the
same query to its end and returned **319** records. And the candidates are no
longer unscreened: eight of those sources were staged and screened over 3902
pages, keeping **32** candidate pages under the frame's own text-sufficiency
rule, of which **10** bear raster figures. None has been crop-extracted, so
none is yet a frame chunk.

The manuscript now reports 319, the eight screened sources, 32 candidate pages,
and the 10 raster-bearing ones, and states that none is crop-resolved.

Not covered by a check: the discovery and screening records are acquisition
artefacts and are not part of `records/`, which holds the executed census. They
are not redistributed, because they carry catalogue identifiers and staged
copyrighted PDFs. The numbers above are recomputable from those artefacts by the
owner and are stated here so the claim can be challenged.

## 5. Poppler version removed from the setup description

The setup section named the extractor as "`pdftotext -layout`, Poppler 25.12.0".
The tool is correct and is recorded in the run, but the version is not: no
record captures which Poppler built `T_c` in August, and 25.12.0 is simply what
the machine that drafted the sentence reports today. The version is now omitted
rather than asserted. Nothing else in the paper depends on it.
