# Profile Breakdown Input

The renderer accepts one UTF-8 JSON object. Times may use any unit, but all
profiles and components in one file must use the unit declared in `metric`.

```json
{
  "schema_version": 1,
  "title": "LingBot-WM VAE steady decode",
  "subtitle": "768x384, latent T=4, NVIDIA Thor",
  "metric": {
    "name": "GPU operation time",
    "unit": "ms",
    "aggregation": "one steady profiled chunk",
    "lower_is_better": true
  },
  "context": {
    "hardware": "NVIDIA Thor",
    "shape": "latent [16,4,48,96] -> RGB [3,16,384,768]",
    "software": "PyTorch + cuDNN",
    "protocol": "warm cache, synchronized NVTX range"
  },
  "profiles": [
    {
      "name": "Before: FP32 per-frame",
      "total": 1140.092,
      "components": [
        {"name": "Convolution/cuDNN", "value": 673.940},
        {"name": "VAE RMS/cache producer", "value": 288.691}
      ]
    },
    {
      "name": "Current: BF16 vectorized",
      "total": 593.754,
      "components": [
        {"name": "Convolution/cuDNN", "value": 396.420},
        {"name": "VAE RMS/cache producer", "value": 96.119}
      ]
    }
  ],
  "optimizations": [
    {
      "name": "Decoder-only BF16",
      "description": "Keep the encoder and master statistics in FP32; run only the streaming decoder in BF16.",
      "impact": "1.72x steady decoder GPU-span speedup",
      "components": ["Convolution/cuDNN", "VAE RMS/cache producer"]
    }
  ],
  "notes": [
    "The first causal chunk remains per-frame to preserve Rep-cache semantics."
  ],
  "sources": [
    "profile/nsys/fp32.nsys-rep",
    "profile/nsys/bf16-vectorized.nsys-rep"
  ]
}
```

## Required Fields

- `schema_version`: integer `1`.
- `title`: non-empty string.
- `metric.name`, `metric.unit`, `metric.aggregation`: non-empty strings.
- `profiles`: one to four profile objects.
- `profiles[].name`: unique, non-empty string.
- `profiles[].components`: non-empty list of unique `{name, value}` objects.
- Component values and optional `total` must be finite and non-negative.

When `total` is omitted, the renderer uses the component sum. If the sum is
smaller than `total`, it adds an explicit `Unattributed` component. The allowed
floating-point tolerance is `max(1e-6, total * 0.005)`. A sum above that limit is
rejected because it makes shares and speedups misleading.

## Optional Fields

- `subtitle`: concise workload description.
- `metric.lower_is_better`: defaults to `true` and controls the baseline/current
  ratio label.
- `context`: string-to-string metadata shown near the title.
- `optimizations`: implemented changes. `components` names must match profile
  component names; `impact` should be a measured claim.
- `notes`: interpretation constraints or protocol caveats.
- `sources`: raw trace, analysis, benchmark, and configuration paths. Relative
  paths are resolved by the reader of the report, not rewritten by the renderer.

The first profile is the comparison baseline and the last is the current state.
Middle profiles may represent intermediate precision modes or optimization
iterations.
