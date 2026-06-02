// Custom SVG manipulatives: FractionBar, NumberLine, SymbolicEditor (TECH_STACK §2).
export { SymbolicEditor, fractionToAnswer, type FractionValue } from './SymbolicEditor';
export { NumberLine, clampTick, nearestTick, tickFraction } from './NumberLine';
export { FractionBar, barToAnswer, type BarValue } from './FractionBar';
export { YesNo, yesNoToAnswer } from './YesNo';
export { NumberEntry } from './NumberEntry';
export { ExpressionInput } from './ExpressionInput';
export { InequalityInput, inequalityToAnswer, isCompleteInequality } from './InequalityInput';
export { ClassifySets, selectionToAnswer, answerToSelection } from './ClassifySets';
// Display-only stimulus (not a WorkspaceWidget answer input): a labeled geometry figure for the
// Unit-6 area/volume problem statements; geometry answers stay numeric via NumberEntry.
export { FigureStimulus, describeFigure, type FigureSpec } from './FigureStimulus';
// Display-only stats stimulus (dot plot / frequency table / histogram) for the Unit-7 stats problem
// statements; stats answers stay numeric/yes-no — this only visualizes the data set.
export { StatsStimulus } from './StatsStimulus';
// Display-only set-model stimulus (a jar of coloured counters) for the Unit-1 ratio-language
// statements; the answer stays a fraction via SymbolicEditor — this only visualizes the collection.
export { SetModelStimulus } from './SetModelStimulus';
export { CoordinatePlane, pointsToAnswer, answerToPoints, type GridPoint } from './CoordinatePlane';
export { selectWidget, type WidgetKind, type WorkspaceWidgetProps } from './WidgetContract';
