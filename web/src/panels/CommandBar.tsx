import { useEffect, useRef, useState } from 'react'
import {
  executeCommand,
  prepareCommand,
  type CommandAction,
  type CommandParams,
  type PrepareResponse,
} from '../state/operationsApi'
import { useTelemetryStore } from '../state/telemetryStore'

type PendingCommand = {
  action: CommandAction
  params: CommandParams
  preparation: PrepareResponse
  expiresAt: number
}

const actionLabels: Record<CommandAction, string> = {
  arm: 'ARM',
  mode: 'SET MODE · AUTO',
  rtl: 'RETURN TO LAUNCH',
}

export function CommandBar() {
  const armed = useTelemetryStore((state) => state.armed)
  const logAudit = useTelemetryStore((state) => state.logAudit)
  const [pending, setPending] = useState<PendingCommand | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [slide, setSlide] = useState(0)
  const [now, setNow] = useState(() => performance.now())
  const [error, setError] = useState('')
  const [executing, setExecuting] = useState(false)
  const pointerActive = useRef(false)
  const dragStarted = useRef(false)
  const submitStarted = useRef(false)

  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setNow(performance.now()), 200)
    return () => window.clearInterval(timer)
  }, [pending])

  const remainingSeconds = pending ? Math.max(0, Math.ceil((pending.expiresAt - now) / 1000)) : 0

  const openConfirmation = async (action: CommandAction) => {
    const params: CommandParams = action === 'mode' ? { mode: 'AUTO' } : {}
    setPreparing(true)
    setError('')
    logAudit(`${actionLabels[action]} · PREPARE`, 'INFO', 'Requesting bridge confirmation')
    try {
      const preparation = await prepareCommand(action, params)
      logAudit(`${actionLabels[action]} · PREPARED`, 'SUCCESS', preparation.summary)
      setPending({
        action,
        params,
        preparation,
        expiresAt: performance.now() + preparation.expires_s * 1000,
      })
      setSlide(0)
      setNow(performance.now())
      submitStarted.current = false
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      logAudit(`${actionLabels[action]} · PREPARE FAILED`, 'ERROR', message)
    } finally {
      setPreparing(false)
    }
  }

  const confirm = async () => {
    if (!pending || remainingSeconds <= 0 || submitStarted.current) return
    submitStarted.current = true
    setExecuting(true)
    logAudit(`${actionLabels[pending.action]} · EXECUTE`, 'INFO', 'Sending confirmed command to bridge')
    try {
      await executeCommand(pending.action, pending.preparation.confirm_token, pending.params)
      logAudit(`${actionLabels[pending.action]} · ACCEPTED`, 'SUCCESS', 'Bridge accepted the command')
      setPending(null)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      setSlide(0)
      submitStarted.current = false
      logAudit(`${actionLabels[pending.action]} · REJECTED`, 'ERROR', message)
    } finally {
      setExecuting(false)
    }
  }

  const close = () => {
    if (pending) logAudit(`${actionLabels[pending.action]} · CANCELLED`, 'INFO', 'Operator closed confirmation')
    setPending(null)
    setSlide(0)
    setError('')
  }

  const handleSlide = (value: number) => {
    if (pointerActive.current && !dragStarted.current) {
      setSlide(0)
      return
    }
    setSlide(value)
    if (value === 100) void confirm()
  }

  return (
    <>
      <section className="panel command-panel" aria-label="Flight commands">
        <div className="panel__heading">
          <div><p className="eyebrow">COMMAND GATEWAY</p><h2>Flight commands</h2></div>
          <span className="panel__index">05</span>
        </div>
        <p className="command-safety-note">
          Commands require bridge preparation and deliberate confirmation. The bridge remains authoritative.
        </p>
        <div className="command-buttons">
          <button type="button" onClick={() => void openConfirmation('arm')} disabled={preparing || armed === true}>
            ARM VEHICLE
          </button>
          <button type="button" onClick={() => void openConfirmation('mode')} disabled={preparing}>
            MODE <span>AUTO</span>
          </button>
          <button className="command-button--caution" type="button" onClick={() => void openConfirmation('rtl')} disabled={preparing}>
            RETURN TO LAUNCH
          </button>
        </div>
        {error && <p className="operation-error" role="alert">{error}</p>}
      </section>

      {pending && (
        <div className="modal-backdrop">
          <section className="command-modal" role="dialog" aria-modal="true" aria-labelledby="command-modal-title">
            <div className="panel__heading">
              <div><p className="eyebrow">CONFIRM COMMAND · {remainingSeconds}s</p><h2 id="command-modal-title">{actionLabels[pending.action]}</h2></div>
              <button className="modal-close" type="button" onClick={close} aria-label="Cancel command">×</button>
            </div>
            <p className="command-modal__summary">{pending.preparation.summary}</p>
            <p className="command-modal__notice">
              This command will be sent to the vehicle after confirmation. The single-use confirmation expires in {remainingSeconds} seconds.
            </p>
            <label className="slide-label" htmlFor="confirm-command">Slide fully right to send</label>
            <input
              id="confirm-command"
              className="confirm-slider"
              type="range"
              min="0"
              max="100"
              value={slide}
              disabled={remainingSeconds === 0 || executing}
              onPointerDown={(event) => {
                pointerActive.current = true
                dragStarted.current = event.clientX <= event.currentTarget.getBoundingClientRect().left + 22
                if (!dragStarted.current) setSlide(0)
              }}
              onPointerUp={() => {
                pointerActive.current = false
                dragStarted.current = false
              }}
              onPointerCancel={() => {
                pointerActive.current = false
                dragStarted.current = false
              }}
              onChange={(event) => handleSlide(Number(event.currentTarget.value))}
              onKeyUp={(event) => {
                if (event.currentTarget.value === '100') void confirm()
              }}
            />
            <div className="slider-endpoints"><span>HOLD</span><span>{executing ? 'SENDING…' : remainingSeconds === 0 ? 'EXPIRED' : 'CONFIRM'}</span></div>
            {error && <p className="operation-error" role="alert">{error}</p>}
          </section>
        </div>
      )}
    </>
  )
}
