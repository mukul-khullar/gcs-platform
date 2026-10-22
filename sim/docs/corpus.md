# SITL telemetry corpus

`corpus/matrix.yaml` defines 30 nominal flights and 72 fault flights across three scenarios,
with seeded wind and mission-shape variation. The runner pins SITL to speedup 4, refuses any
matrix that changes that value, and requires explicit confirmation before arming.

```powershell
python sim/corpus/generate.py --plan
python sim/corpus/generate.py --confirm-sitl
python sim/corpus/generate.py --validate-manifest sim/corpus/manifest.json
```

Generation builds the pinned Docker image, starts a dedicated SITL container, saves `.tlog`
files in `sim/corpus/flights/`, and writes `labels.json` and `manifest.json`. Each manifest
entry is a SHA256 digest; validation checks the complete file set, hashes, labels, and minimum
flight counts. A full matrix contains 102 sequential flights and can take substantial time.

Decode a flight to CSV and load it into pandas in fewer than five lines:

```python
import io, pandas as pd, subprocess
log = subprocess.run(["mavlogdump.py", "--format", "csv", "sim/corpus/flights/nominal_001.tlog"], capture_output=True, text=True, check=True)
df = pd.read_csv(io.StringIO(log.stdout))
```

The corpus is reproducible from the matrix seed and pinned firmware, but its flight paths
depend on simulator timing and are not an exact physical model.
