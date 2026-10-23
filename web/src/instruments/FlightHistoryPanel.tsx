import { useEffect, useState } from 'react'
import { telemetryFrames } from '../state/telemetryStore'
import { visiblePositionHistory } from '../state/telemetryHistory'
import type { PositionSample } from '../state/telemetryHistory'

const ranges = [15, 60, 300] as const
type Metric = 'alt_rel_m' | 'speed_mps'

function samplePath(samples: PositionSample[], metric: Metric, rangeSeconds: number, nowMs: number): string {
  if (samples.length < 2) return ''
  const values = samples.map((sample) => sample[metric])
  const minimum = Math.min(...values)
  const spread = Math.max(...values) - minimum || 1
  const startMs = nowMs - rangeSeconds * 1000
  return samples.map((sample, index) => {
    const x = 44 + ((sample.receivedAtMs - startMs) / (rangeSeconds * 1000)) * 740
    const y = 18 + (1 - (sample[metric] - minimum) / spread) * 126
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function HistoryChart({ title, unit, metric, samples, rangeSeconds, nowMs }: {
  title: string
  unit: string
  metric: Metric
  samples: PositionSample[]
  rangeSeconds: number
  nowMs: number
}) {
  const latest = samples.at(-1)
  return (
    <article className="history-chart">
      <div className="history-chart__heading">
        <span>{title}</span>
        <strong>{latest ? `${latest[metric].toFixed(1)} ${unit}` : 'NO DATA'}</strong>
      </div>
      <svg viewBox="0 0 800 176" role="img" aria-label={`${title} over the last ${rangeSeconds} seconds`}>
        {[18, 60, 102, 144].map((y) => <line key={y} x1="44" x2="784" y1={y} y2={y} />)}
        <text x="4" y="23">{unit}</text>
        <text x="4" y="159">-{rangeSeconds} s</text>
        <text x="744" y="159">0 s</text>
        {samples.length > 1 && <path d={samplePath(samples, metric, rangeSeconds, nowMs)} />}
      </svg>
      <p>{samples.length < 2 ? 'Waiting for additional position samples.' : `Measured from telemetry.position · ${samples.length} samples`}</p>
    </article>
  )
}

export function FlightHistoryPanel() {
  const [rangeSeconds, setRangeSeconds] = useState<(typeof ranges)[number]>(60)
  const [nowMs, setNowMs] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(performance.now()), 500)
    return () => window.clearInterval(timer)
  }, [])
  const samples = visiblePositionHistory(telemetryFrames.positionHistory, nowMs, rangeSeconds)

  return (
    <section className="panel flight-history" aria-labelledby="history-title">
      <div className="panel-heading">
        <div><p className="eyebrow">RECENT AIRCRAFT DATA</p><h2 id="history-title">Flight history</h2></div>
        <div className="history-ranges" role="group" aria-label="Chart time range">
          {ranges.map((range) => (
            <button type="button" key={range} aria-pressed={rangeSeconds === range} onClick={() => setRangeSeconds(range)}>
              {range < 60 ? `${range}S` : `${range / 60}M`}
            </button>
          ))}
        </div>
      </div>
      <div className="history-chart-grid">
        <HistoryChart title="RELATIVE ALTITUDE" unit="m" metric="alt_rel_m" samples={samples} rangeSeconds={rangeSeconds} nowMs={nowMs} />
        <HistoryChart title="GROUND SPEED" unit="m/s" metric="speed_mps" samples={samples} rangeSeconds={rangeSeconds} nowMs={nowMs} />
      </div>
    </section>
  )
}
