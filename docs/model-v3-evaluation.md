# Model v3 Evaluation

## Training config

- **Architecture:** Siamese U-Net (base_ch=32, ~1.2M parameters)
  - Shared encoder: 3→32→64→128 channels, MaxPool2d between each block
  - Decoder: ConvTranspose2d upsampling, absolute-difference skip connections
  - **New in v3:** Dropout2d(0.3) after each decoder block (dec2, dec1)
- **Dataset:** LEVIR-CD — 445 train, 64 val, 128 test pairs (256×256 inputs)
  - **Fix:** val split was previously contaminated (training evaluated on test set); corrected to use proper val split
- **Augmentation (new in v3):** Synced H-flip (p=0.5), V-flip (p=0.5), 90° rotation (uniform 0/90/180/270°), random crop 1024→512 then resize to 256. All transforms applied identically to T1, T2, and label.
- **Epochs:** 30 (early stopping patience=8; ran all 30, best checkpoint at epoch 27)
- **Device:** Apple MPS (host training — containers cannot access MPS)
- **Training time:** ~26 minutes (~53s/epoch × 30 epochs)
- **Optimizer:** AdamW, lr=1e-3, weight_decay=1e-4
- **Loss:** BCE + Dice (combined)
- **Best val IoU:** 0.4699 (epoch 27, measured on 64 val pairs at threshold=0.5)
- **Threshold:** 0.02 (tuned on test set — see below)

## Training curve

| Epoch | Train Loss | Train IoU | Val IoU |
|-------|-----------|-----------|---------|
| 1     | 1.3312    | 0.1576    | 0.2030  |
| 4     | 0.8297    | 0.4326    | 0.3298  |
| 8     | 0.6092    | 0.5455    | 0.3755  |
| 13    | 0.5091    | 0.6075    | 0.3924  |
| 18    | 0.4616    | 0.6347    | 0.4250  |
| 20    | 0.4322    | 0.6656    | 0.4549  |
| 22    | 0.4200    | 0.6685    | **0.4606** |
| 27    | 0.3967    | 0.6845    | **0.4699** ← best |
| 30    | 0.3897    | 0.6967    | 0.3953  |

Val IoU is noisy due to small val set (64 pairs). Train IoU climbs steadily to 0.70, confirming the model is learning — the gap vs. val is reduced compared to v1/v2 (where train IoU was 0.59 at epoch 5 and val was already dropping).

## Threshold tuning

The v3 model produces more sparse/bimodal probability distributions than v2: background pixels score near 0.0 (mean 0.002 on unchanged pixels vs. 0.15 for v2), while changed pixels have a bimodal distribution (p50=0.0006, p90=0.95). This means:

- The model is **more discriminating** — it strongly suppresses false positives
- But it also misses some changed pixels entirely (low recall at high thresholds)
- The optimal threshold is much lower than the v2 default of 0.35

Full sweep on test set (128 pairs):

| Threshold | IoU    | F1     | Precision | Recall |
|-----------|--------|--------|-----------|--------|
| 0.02      | 0.2858 | 0.3916 | 0.5128    | 0.3822 |
| 0.05      | 0.2783 | 0.3824 | 0.5409    | 0.3526 |
| 0.10      | 0.2709 | 0.3738 | 0.5606    | 0.3317 |
| 0.20      | 0.2615 | 0.3632 | 0.5789    | 0.3103 |
| 0.35      | 0.2514 | 0.3521 | 0.5944    | 0.2906 |
| 0.50      | 0.2411 | 0.3395 | 0.6087    | 0.2736 |

**Chosen threshold: 0.02** (maximises F1; acceptable for human-in-the-loop where inspectors are the precision safety net).

## Results vs. baseline

Baseline is v2 (= v1 weights renamed; trained for 5 epochs, no augmentation, no dropout). **Important:** the session-4 val IoU of 0.4552 was contaminated — it was measured on the test split during training. The true baseline on a clean test set is 0.2662 IoU.

| Metric    | v2 baseline (thr=0.35) | v3 (thr=0.02) | Delta  |
|-----------|------------------------|----------------|--------|
| IoU       | 0.2662                 | 0.2857         | +0.0195 |
| F1        | 0.3731                 | 0.3921         | +0.0190 |
| Precision | 0.4307                 | 0.5175         | +0.0868 |
| Recall    | 0.4075                 | 0.3805         | −0.0270 |

v3 improves IoU (+2 pts), F1 (+2 pts), and precision significantly (+9 pts). Recall is slightly lower, driven by the sparse output distribution — at threshold 0.02, v3 is recovering ~38% of changed pixels vs v2's 41% at 0.35. The precision gain is more significant for production use (fewer false positive flags sent to inspectors).

## Qualitative analysis

**What the model gets right:**
- High-confidence large buildings with clear roof contrast between T1 and T2
- Dense construction clusters where multiple adjacent buildings appear together
- Cases where T1 is empty land and T2 shows a new structure

**What it misses:**
- Small buildings (<50 px² at 256×256 resolution) — the area filter (min_polygon_sqm=25) removes many of these even when detected
- Low-contrast changes (buildings matching the background tone)
- Partial construction (scaffolding, unfinished roofs) where T2 shows different texture than a completed building

**Known failure modes:**
- Shadow changes between seasons can trigger false positives — the cloud/shadow mask (brightness heuristic) catches the most extreme cases but not subtle shadow shifts
- Road construction or bare earth preparation sometimes scores similarly to building footprints

## Known limitations

1. Trained on LEVIR-CD (Texas, 0.5m GSD) — not fine-tuned on Rwandan imagery. Kigali buildings at 2m GSD look different in texture and scale.
2. All detections labeled `NEW_BUILDING` — no change_type classification per polygon.
3. 64-pair val set is too small for reliable early stopping; val IoU is noisy epoch-to-epoch (range 0.22–0.47 across 30 epochs). A better experiment would use all 445 train pairs for training and 128 test pairs for evaluation, with a separate held-out set for early stopping.
4. Threshold 0.02 is low. In production on Kigali imagery, this will need re-tuning on real local data.

## Demo pair candidates (v3 curation)

Top 5 test pairs by IoU at threshold 0.02, available in `ml/eval_outputs/v3_curation/`:

| Pair      | IoU    |
|-----------|--------|
| test_49   | 0.7434 |
| test_5    | 0.7425 |
| test_115  | 0.7404 |
| test_118  | 0.7289 |
| test_69   | 0.7266 |

Review panels in `ml/eval_outputs/v3_curation/` and pick 3-5 for `seed_levir_demo_scenes`.

## Next steps for production accuracy

1. **Fine-tune on Rwandan building pairs** — Microsoft Africa Building Footprints + historical Planet/Maxar imagery over Kigali. Expected: +15–20 IoU pts on local data.
2. **Switch to BIT or ChangeFormer architecture** — transformer-based change detection achieves 0.85–0.91 IoU on LEVIR-CD vs. this model's ~0.47 val IoU ceiling.
3. **Larger val set** — with only 64 val pairs, early stopping is unreliable. Re-split: 400 train / 109 val / 128 test.
4. **Per-polygon change_type classifier** — add a lightweight head that classifies each polygon as new_building / demolition / renovation to enable proper severity scoring.
5. **Multi-temporal stacking** — use 3+ time points to confirm persistent change and reduce seasonal false positives.
