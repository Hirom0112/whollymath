// Custom SVG manipulatives: FractionBar, NumberLine, SymbolicEditor (TECH_STACK §2).
export { SymbolicEditor, fractionToAnswer, type FractionValue } from './SymbolicEditor';
export { NumberLine, clampTick, nearestTick, tickFraction } from './NumberLine';
export { FractionBar, barToAnswer, type BarValue } from './FractionBar';
export { YesNo, yesNoToAnswer } from './YesNo';
export { NumberEntry } from './NumberEntry';
export { ExpressionInput } from './ExpressionInput';
export { InequalityInput, inequalityToAnswer } from './InequalityInput';
export {
  CoordinatePlane,
  pointsToAnswer,
  answerToPoints,
  type GridPoint,
} from './CoordinatePlane';
export {
  selectWidget,
  type WidgetKind,
  type WorkspaceWidgetProps,
} from './WidgetContract';
