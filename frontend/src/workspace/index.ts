// Custom SVG workspace widgets (answer inputs + display-only stimuli). selectWidget() in
// WidgetContract.ts dispatches by KC/representation; SymbolicEditor, NumberLine, and FractionArea
// are the core manipulatives (TECH_STACK §2). FractionBar is an earlier bar model, still exported
// but not currently routed by selectWidget — superseded by FractionArea.
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
// Display-only "scene" pictures, one per KC family, behind a single dispatcher (SceneStimulus reads
// ProblemView.scene). Each shows the question input only, never the answer — not answer widgets.
export { SceneStimulus } from './SceneStimulus';
export { PercentGrid } from './PercentGrid';
export { RatioTable } from './RatioTable';
export { IntegerLine } from './IntegerLine';
export { FractionArea } from './FractionArea';
export { DecimalPlaceValue } from './DecimalPlaceValue';
export { GcfFactors } from './GcfFactors';
export { ExponentProduct } from './ExponentProduct';
export { CoordinatePlane, pointsToAnswer, answerToPoints, type GridPoint } from './CoordinatePlane';
export { selectWidget, type WidgetKind, type WorkspaceWidgetProps } from './WidgetContract';
