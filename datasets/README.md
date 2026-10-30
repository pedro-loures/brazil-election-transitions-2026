# Published data snapshot

The snapshot contains the computed domestic analysis and normalized inputs for
2026. These are aggregate election results and model estimates. Estimated flows
do not identify individual voters or establish causal campaign effects.

| Directory | Contents |
| --- | --- |
| `2026/results/` | All 5,571 municipality totals, fitted flows, section and polling-place diagnostics, reconciliation audit, run settings, summary, and overview figures |
| `2026/processed/` | Normalized section-round inputs, candidate registry, finalist metadata, and independent municipal references |
| `2026/provenance/` | Official TSE download manifest, map provenance, and TSE-to-IBGE municipality-code crosswalk |
| `twitter_comparison/` | Available Lebon Régis comparisons against the supplied thread figures |

`manifest.json` records the SHA-256 hash, byte length, and working restore path
of every published dataset file. The `docs/data/` directory also contains the
municipal and aggregate JSON used by the visualization, and its GeoJSON maps.

To restore working inputs and computed outputs after cloning:

```bash
python scripts/restore_snapshot.py
```

This verifies every dataset checksum before copying any files. You can then run
tests, rebuild the explorer, or rerun analysis without downloading the raw TSE
archives. Rebuilding map geometry still requires the official IBGE mesh.

Raw source archives are omitted from Git because of their size. The original
public URLs and source hashes are preserved in the provenance files. Use
`python -m elections download --year 2026 --output data/raw/2026` to retrieve the
TSE inputs. Attribution: Tribunal Superior Eleitoral (TSE) and Instituto
Brasileiro de Geografia e Estatística (IBGE); model estimates are produced by
this project. Third-party source data retain their original terms.
