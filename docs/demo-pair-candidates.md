# LEVIR-CD Demo Pair Candidates

Top 10 pairs ranked by `score = IoU × (gt_pct/100) × max(NCC, 0)`.

- **IoU** — model prediction vs ground-truth mask (0–1, higher = model detects the right pixels)
- **GT%** — percentage of image pixels with real change (ground truth mask)
- **NCC** — normalised cross-correlation of T1/T2 luminance; proxy for visual scene similarity (higher = T1 and T2 look more like the same place)
- **Score** — composite; rewards pairs where all three are high simultaneously

Panel PNGs are in `ml/eval_outputs/curation/`. Each panel shows: T1 | T2 | GT mask | Predicted prob | Overlay (red = predicted change) | Luminance diff map.

| Rank | Pair ID  | Score  | IoU   | GT%   | NCC   | Notes |
|------|----------|--------|-------|-------|-------|-------|
| 1    | test_14  | 0.0331 | 0.721 | 10.8% | 0.424 | Current seed — high IoU but seasonal mismatch gives very different overall brightness |
| 2    | test_7   | 0.0284 | 0.647 | 10.9% | 0.405 | Good balance; moderate NCC suggests similar structure |
| 3    | test_38  | 0.0250 | 0.630 | 13.2% | 0.300 | High GT change, decent IoU; lower NCC (more visual drift) |
| 4    | test_10  | 0.0250 | 0.685 | 9.8%  | 0.374 | Strong model performance, moderate visual similarity |
| 5    | test_34  | 0.0248 | 0.444 | 13.4% | 0.416 | High GT%, good NCC; weaker IoU means model misses some change |
| 6    | test_80  | 0.0247 | 0.470 | 20.0% | 0.263 | Highest GT% in top 10 (dramatic change); lower NCC/IoU |
| 7    | test_8   | 0.0244 | 0.545 | 8.1%  | 0.551 | **Highest NCC in top 10** — T1/T2 most visually similar; good for demo clarity |
| 8    | test_55  | 0.0236 | 0.690 | 11.0% | 0.310 | High IoU; lower NCC |
| 9    | test_13  | 0.0220 | 0.426 | 9.8%  | 0.528 | High NCC (looks like same place); weaker IoU |
| 10   | test_87  | 0.0215 | 0.591 | 10.6% | 0.344 | Solid all-round; no standout weakness |

## How to pick

For the demo the priority order is:
1. **NCC ≥ 0.45** — T1 and T2 must look like the same location to a non-expert eye
2. **GT% ≥ 5%** — enough change that the red overlay is clearly visible
3. **IoU ≥ 0.50** — model is actually finding the right pixels

By that filter: **test_8** (NCC=0.55, GT=8.1%, IoU=0.54) and **test_13** (NCC=0.53, GT=9.8%) look best for human-readable demo clarity even though they don't top the composite score.

Pick 3–5 pair IDs from this table (look at the panel PNGs), then re-seed:

```bash
python manage.py seed_levir_demo_scenes \
  --pair-ids test_8,test_13,test_7 \
  --force
```
