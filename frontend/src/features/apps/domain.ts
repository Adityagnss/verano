/** Pure helpers for the apps screen. */

/** "name=value" lines into the inputs of one test case; a line without "=" is ignored. */
export function parseInputs(text: string): Record<string, string> {
  const inputs: Record<string, string> = {}
  for (const line of text.split("\n")) {
    const at = line.indexOf("=")
    if (at > 0) inputs[line.slice(0, at).trim()] = line.slice(at + 1)
  }
  return inputs
}
