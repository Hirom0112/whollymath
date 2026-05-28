// Behavioral telemetry: a buffered, fire-and-forget capture of the raw interaction stream
// (Slice PL.2.2). Records how a learner works a problem; never changes what the UI does
// (capture richly, act conservatively — ARCHITECTURE.md §14 invariant 9).
export { TelemetryBuffer, type TelemetryEventType } from './telemetry';
export { useTelemetry, type Telemetry } from './useTelemetry';
