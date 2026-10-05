/**
 * The evidence behind a significance label: the quality difference with its interval and the number of cases,
 * the pass-rate difference with the exact test, how many cases were left out, and the method in one sentence.
 * Also the plain-text version used as a hover title.
 */
import type { ComparisonOut } from "@/lib/api/types"

import { RESULTS_COPY } from "../copy"

export function comparisonText(c: ComparisonOut): string {
  return [
    RESULTS_COPY.comparisonLines(c.cases, c.difference, c.low, c.high, c.level),
    RESULTS_COPY.comparisonPass(
      c.pass_rate_difference,
      c.mcnemar_p,
      c.first_only_passed,
      c.second_only_passed,
    ),
    c.only_first + c.only_second > 0 ? RESULTS_COPY.comparisonLeftOut(c.only_first, c.only_second) : "",
    c.method,
  ]
    .filter(Boolean)
    .join(" ")
}

export function ComparisonDetail({ comparison: c }: { comparison: ComparisonOut }) {
  return (
    <ul className="text-text-secondary flex flex-col gap-0.5 text-xs">
      <li>{RESULTS_COPY.comparisonLines(c.cases, c.difference, c.low, c.high, c.level)}</li>
      <li>
        {RESULTS_COPY.comparisonPass(
          c.pass_rate_difference,
          c.mcnemar_p,
          c.first_only_passed,
          c.second_only_passed,
        )}
      </li>
      {c.only_first + c.only_second > 0 ? (
        <li>{RESULTS_COPY.comparisonLeftOut(c.only_first, c.only_second)}</li>
      ) : null}
      <li className="text-text-muted">{c.method}</li>
    </ul>
  )
}
