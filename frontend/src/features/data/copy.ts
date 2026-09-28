/** User-facing text for the Your Data step. */
export const DATA_COPY = {
  title: "Add your data (optional)",
  subtitle:
    "Real data makes the test cases realistic. Everything here is optional: without data, Verano writes the test cases for you.",
  cards: {
    golden: {
      title: "Golden set",
      description: "Inputs with correct answers. Used as they are and trusted.",
    },
    inputs: {
      title: "Input files",
      description: "Real inputs without answers. Verano drafts the answers for you to review.",
    },
    documents: {
      title: "Reference documents",
      description: "Policies, manuals, FAQs. Test cases are written from them and checked against them.",
    },
  },
  rowsFormats: "CSV, XLSX, JSON or JSONL",
  documentFormats: "PDF, DOCX, TXT or MD",
  choose: "Choose file",
  uploading: "Uploading…",
  uploaded: (name: string) => `${name} uploaded.`,
  filesHeading: "Your files",
  noFiles: "No files yet. Add one above, or let Verano generate test cases.",
  status: {
    uploaded: "Waiting",
    profiling: "Reading…",
    ready: "Map columns",
    validating: "Checking rows…",
    validated: "Ready to import",
    importing: "Importing…",
    imported: "Imported",
    extracting: "Reading text…",
    extracted: "Ready",
    failed: "Failed",
  } as Record<string, string>,
  kind: { golden_set: "Golden set", raw_inputs: "Input file", reference_document: "Document" } as Record<
    string,
    string
  >,
  rows: (count: number) => `${count.toLocaleString()} rows`,
  sections: (count: number) => `${count} sections`,
  imported: (count: number) => `${count.toLocaleString()} test cases added`,
  sheet: "Sheet",
  mappingHeading: "Match your columns",
  mappingHint: "Tell Verano which column holds what. The suggestion is based on the column names.",
  input: (name: string) => (name === "user_message" ? "User message" : `Prompt variable: ${name}`),
  targets: {
    expected_output: "Correct answer",
    rubric: "Grading criteria",
    category: "Category",
    tags: "Tags",
  } as Record<string, string>,
  none: "— none —",
  noPrompt: "Save a prompt first (step 2), so Verano knows which columns it needs.",
  check: "Check rows",
  checking: "Checking…",
  report: (valid: number, skipped: number, duplicates: number) =>
    `${valid.toLocaleString()} valid rows, ${skipped.toLocaleString()} skipped, ${duplicates.toLocaleString()} duplicates removed`,
  rowsList: (rows: number[], count: number) =>
    `rows ${rows.join(", ")}${count > rows.length ? ` and ${count - rows.length} more` : ""}`,
  importRows: (count: number) => `Import ${count.toLocaleString()} rows`,
  remove: "Remove",
  generateForMe: "I don't have data, generate it for me",
  next: "Next: test cases",
}
