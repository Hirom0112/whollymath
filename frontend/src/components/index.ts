// React components (Storybook stories alongside).
export {
  LearningPathRail,
  type PathNode,
  type PathNodeStatus,
  type PathNodeTint,
} from './LearningPathRail';
export { Mascot } from './Mascot';
export { AvatarGuide, type AvatarGuideProps } from './avatar/AvatarGuide';
// PHASE-1 SPIKE (capability-gated, default OFF, lazy-loaded). The 3D avatar gate is exported so the
// owner can mount it for the ~30fps Chromebook acceptance test; it renders nothing unless the device
// is capable AND the `wm-avatar-3d` / `?avatar3d=1` opt-in is set. The three.js bundle stays in its
// own lazy chunk — importing the gate here does NOT pull 3D deps into the main bundle.
export { Avatar3DGate, type Avatar3DGateProps } from './avatar/Avatar3DGate';
export { emotionToGuide, type GuidePresentation } from './avatar/emotionToGuide';
export { HelpLanguageToggle } from './HelpLanguageToggle';
export { PiMenu, type PiMenuItem } from './PiMenu';
export { LessonTracker, type LessonPhase } from './LessonTracker';
export { SparkCount } from './SparkCount';
export { Sparkline, type SparklineProps, type SparklineTone } from './Sparkline';
export { AreaChart, type AreaChartProps, type AreaChartTone } from './AreaChart';
export { WoodBanner } from './WoodBanner';
