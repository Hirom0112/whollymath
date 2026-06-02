import type { ProblemView } from '@whollymath/shared-types';

import { DecimalPlaceValue } from './DecimalPlaceValue';
import { ExponentProduct } from './ExponentProduct';
import { FractionArea } from './FractionArea';
import { GcfFactors } from './GcfFactors';
import { IntegerLine } from './IntegerLine';
import { PercentGrid } from './PercentGrid';
import { RatioTable } from './RatioTable';
import './SceneStimulus.css';

/**
 * One front door for every DISPLAY-ONLY problem "scene". The backend attaches at most one `scene`
 * to a ProblemView (app/domain/scene.py); this switches on its `kind` and renders the matching
 * picture — percent hundred-grid, ratio table, integer number line, fraction area model, decimal
 * place-value chart, GCF/LCM factor list, or exponent repeated-product.
 *
 * Like the other stimuli, every scene shows the QUESTION INPUT only, never the answer (graded
 * server-side by SymPy, §8.2). It is NOT an answer input and never touches selectWidget. The Tutor
 * renders it as the visual anchor above the prompt; the prompt text is the accessible fallback. A
 * problem with no scene renders nothing.
 */
export function SceneStimulus({ problem }: { problem: ProblemView }): React.JSX.Element | null {
  const scene = problem.scene;
  if (scene == null) return null;
  let inner: React.JSX.Element;
  switch (scene.kind) {
    case 'percent_grid':
      inner = <PercentGrid percent={scene.percent} shaded={scene.shaded} />;
      break;
    case 'ratio_table':
      inner = (
        <RatioTable
          top_label={scene.top_label}
          bottom_label={scene.bottom_label}
          columns={scene.columns}
          scale_label={scene.scale_label}
        />
      );
      break;
    case 'integer_jump':
      inner = (
        <IntegerLine
          kind="integer_jump"
          axis_min={scene.axis_min}
          axis_max={scene.axis_max}
          start={scene.start}
          delta={scene.delta}
        />
      );
      break;
    case 'absolute_value':
      inner = (
        <IntegerLine
          kind="absolute_value"
          axis_min={scene.axis_min}
          axis_max={scene.axis_max}
          point={scene.point}
        />
      );
      break;
    case 'signed_point':
      inner = (
        <IntegerLine
          kind="signed_point"
          axis_min={scene.axis_min}
          axis_max={scene.axis_max}
          points={scene.points}
        />
      );
      break;
    case 'fraction_area':
      inner = <FractionArea op={scene.op} first={scene.first} second={scene.second} />;
      break;
    case 'decimal_place_value':
      inner = (
        <DecimalPlaceValue
          kind="decimal_place_value"
          columns={scene.columns}
          point_after={scene.point_after}
          rows={scene.rows}
        />
      );
      break;
    case 'gcf_factors':
      inner = (
        <GcfFactors
          mode={scene.mode}
          first={scene.first}
          second={scene.second}
          first_factors={scene.first_factors}
          second_factors={scene.second_factors}
        />
      );
      break;
    case 'exponent_product':
      inner = (
        <ExponentProduct base={scene.base} exponent={scene.exponent} factors={scene.factors} />
      );
      break;
    default:
      return null;
  }
  return <div className="wm-scene">{inner}</div>;
}
