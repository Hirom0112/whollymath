// Custom SVG manipulatives: FractionBar, NumberLine, SymbolicEditor (TECH_STACK §2).
export { SymbolicEditor, fractionToAnswer, type FractionValue } from './SymbolicEditor';
export { NumberLine, clampTick, nearestTick, tickFraction } from './NumberLine';
export { FractionBar, barToAnswer, type BarValue } from './FractionBar';
export { YesNo, yesNoToAnswer } from './YesNo';
export { NumberEntry } from './NumberEntry';
export { ExpressionInput } from './ExpressionInput';
export { InequalityInput, inequalityToAnswer } from './InequalityInput';
export { ClassifySets, selectionToAnswer, answerToSelection } from './ClassifySets';
// Display-only stimulus (not a WorkspaceWidget answer input): a labeled geometry figure for the
// Unit-6 area/volume problem statements; geometry answers stay numeric via NumberEntry.
export { FigureStimulus, describeFigure, type FigureSpec } from './FigureStimulus';
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
