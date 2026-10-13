/** Pure rules for the Data step. No React here. */
import type { UploadPurpose } from "@/lib/api/types"

const TABLE_FILE = /\.(csv|tsv|xlsx|json|jsonl|ndjson)$/i

/** How a file dropped on the inputs card is read: a table is one test case per row unless the whole file is one input. */
export function inputPurpose(filename: string, wholeFile: boolean): UploadPurpose {
  return !wholeFile && TABLE_FILE.test(filename) ? "input_rows" : "input"
}
