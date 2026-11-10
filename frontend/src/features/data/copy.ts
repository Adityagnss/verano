/** User-facing text for the Your Data step. */
export const DATA_COPY = {
  title: "Add examples",
  intro: {
    what: "Optional files with real inputs and the answers you expect. Without them, Verano writes test cases for you.",
    whenToUse: "you have real messages, files or documents the prompt should handle",
    youGet: "test cases built from your own examples",
  },
  wizard: {
    chooseTitle: "Choose what you have",
    chooseDescription: "Tick everything you can upload. You can skip this whole page.",
    chooseNone: "Tick at least one kind of file, or skip this page.",
    uploadTitle: "Upload",
    uploadDescription: "Add the files. Each is read right away.",
    uploadNone: "Upload at least one file, or go back and skip.",
    matchTitle: "Match the columns",
    matchDescription:
      "Check which column holds the correct answer, then import. Input files need nothing here.",
    confirmTitle: "Confirm",
    confirmDescription: "This is what the test cases will be built from.",
    confirmNone: "No files are ready yet.",
    waiting: "Some files are still being read or need their columns matched.",
  },
  skip: "Skip: write test cases for me",
  subtitle:
    "Send your real files to the models and compare their answers with your golden answers. Everything here is optional: without data, Verano writes the test cases for you.",
  howItWorks: [
    "Input files: each file is sent to every model together with your prompt, as it is. One file is one test case.",
    "Golden set: the correct answer for each input file. Upload it after the input files.",
    "Reference documents: test cases are written from them and checked against them.",
    "Every model's answer is saved for each file and compared with the golden answer.",
  ],
  uploadHeading: "Upload files",
  uploadHint: "Add your input files first, then the golden set. All are optional.",
  filesHint:
    "Input files are ready as soon as they are read. Import the golden set once its columns look right.",
  cards: {
    inputs: {
      title: "Input files",
      description:
        "What your prompt works on: a list of messages, or files. Text files are sent as they are.",
    },
    golden: {
      title: "Golden set",
      description: "The correct answer for each input file, in the same order (or named per file).",
    },
    documents: {
      title: "Reference documents",
      description: "Policies, manuals, FAQs. Test cases are written from them and checked against them.",
    },
  },
  inputFormats: "CSV, XLSX, JSON, JSONL, TXT or MD",
  tableChoice: {
    legend: "A table file (CSV, XLSX, JSON, JSONL) is…",
    rows: {
      label: "A list of inputs: each row is a test case",
      hint: "Use this for a list of messages. A column named message, text or question is sent; otherwise every filled column is.",
    },
    whole: {
      label: "One input: the whole file is a single test case",
      hint: "Use this when the prompt should read the file as a whole, for example a spreadsheet to extract from.",
    },
  },
  goldenFormats: "JSON, JSONL, CSV or XLSX",
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
  imported: (count: number) => `${count.toLocaleString()} answers matched`,
  sheet: "Sheet",
  mappingHeading: "Match your columns",
  mappingHint:
    "Optional. With no correct-answer column, each row is itself the correct answer (for example a JSON rule).",
  targets: {
    expected_output: "Correct answer",
    rubric: "Grading criteria",
    category: "Category",
    tags: "Tags",
    input_file: "Input file name",
  } as Record<string, string>,
  none: "— none —",
  check: "Check entries",
  checking: "Checking…",
  report: (valid: number, skipped: number) =>
    `${valid.toLocaleString()} answers matched to input files, ${skipped.toLocaleString()} skipped`,
  rowsList: (rows: number[], count: number) =>
    `rows ${rows.join(", ")}${count > rows.length ? ` and ${count - rows.length} more` : ""}`,
  importRows: (count: number) => `Import ${count.toLocaleString()} answers`,
  remove: "Remove",
  generateForMe: "I don't have data, generate it for me",
  next: "Next: test cases",
}
