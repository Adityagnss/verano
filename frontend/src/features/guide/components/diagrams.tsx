/**
 * Small architecture pictures for the Prompt guide, drawn as inline SVG so they follow the
 * theme and stay sharp at any size. Each is keyed by the slug of the heading it illustrates
 * (see components/common/markdown.tsx), so the notes stay plain Markdown.
 */
import type { ReactNode } from "react"

type Tone = "blue" | "gold" | "green" | "red" | "grey" | "violet"
const FILL: Record<Tone, [string, string]> = {
  blue: ["#e6eefe", "#2563eb"],
  gold: ["#fdf3d6", "#b7791f"],
  green: ["#e6f4ec", "#22804a"],
  red: ["#fbeae6", "#c23b22"],
  grey: ["#f1f4f9", "#8b95a7"],
  violet: ["#f1eefb", "#5a45b0"],
}

const LABELS: Record<string, string> = {
  "what-a-prompt-is-made-of": "Four layers of a prompt feed the model, which writes the answer",
  "the-one-habit-measure-first":
    "The measuring loop: write a variant, run it repeatedly, grade, compare the gap with the spread",
  "chain-of-thought": "Chain of thought: the question, then written steps, then a marked final answer",
  "few-shot-examples": "Few-shot: solved examples come before the real question",
  "reasoning-first-in-json": "JSON written left to right: reasoning first lets the answer use the working",
  "majority-vote": "Majority vote: ask three times, keep the most common answer",
  "prompt-chaining": "Prompt chaining: small prompts in a row, each checked on its own",
  "context-first-question-last": "Context first, question last: the model reads left to right",
  "prompt-caching": "Prompt caching: an unchanged start is reused, only the end is new",
  "ai-judge": "AI judge: a second model grades the answer against a rubric, and the judge itself is audited",
  "untrusted-text-and-injection": "Injection: instructions hidden in untrusted text can reach the model",
  "automatic-prompt-search":
    "Automatic prompt search: candidates are scored on the same cases and the winner is checked on held-back cases",
  "how-verano-uses-this-guide":
    "The Verano loop: keys, prompt, test cases, run, results, improve, then repeat with the new version",
  "which-technique-should-i-try-first":
    "Which technique first: wrong form, multi-step mistakes, drifting format, varying answers, missing facts, each with its fix",
  "delimiters-and-labelled-sections":
    "Delimiters: rules, document and question each sit in their own named tags before reaching the model",
  "step-back-prompting": "Step-back: state the general principle first, then apply it to the case and answer",
  "tree-of-thoughts":
    "Tree of thoughts: several ideas are tried, weak ones dropped, and the best path is kept",
  "grounding-in-reference-text":
    "Grounding: find the relevant passages, put them before the question, and answer with a source or say not found",
  "tool-use-and-react":
    "ReAct: the model thinks, calls a tool, reads the result, and repeats until it can answer",
  "meta-prompting":
    "Meta-prompting: the task, good examples and failures go to a prompt-writing model that returns candidates to be scored",
  "critique-and-revise-with-new-information":
    "Critique and revise: a draft is checked against new information such as a test or rule, then revised",
  "use-one-or-not":
    "Start with a plain model; only if it is not good enough try a reasoning model at low, then medium, then high effort",
  "thinking-uses-your-token-limit":
    "The token limit covers thinking and answer: a small limit can be used up by thinking and leave no answer",
  "the-parts-of-the-context":
    "The context: role, instructions, examples, live facts, documents, tools, memory and the marked input all reach the model",
  "workflow-or-agent":
    "A workflow runs steps fixed in code; an agent lets the model choose the next step in a loop with tools",
  "tool-calling-step-by-step":
    "Tool calling: your code sends the request and tools, the model picks a tool, your code runs it, the result goes back",
  "testing-an-agent-with-verano-today":
    "An agent split into prompts that Verano can test one by one today; the whole agent with real tools comes after V1",
}

/** Plain-text description of a diagram, keyed by the slug of its heading (used when the page is copied). */
export const DIAGRAM_LABELS = LABELS

function Frame({ label, height = 150, children }: { label: string; height?: number; children: ReactNode }) {
  return (
    <figure className="bg-subtle ring-border my-1 rounded-xl p-3 ring-1">
      <svg
        viewBox={`0 0 640 ${height}`}
        role="img"
        aria-label={label}
        className="w-full"
        fontFamily="inherit"
      >
        <defs>
          <marker
            id="verano-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto"
          >
            <path d="M0 0 10 5 0 10z" fill="#55627a" />
          </marker>
        </defs>
        {children}
      </svg>
      <figcaption className="text-text-muted mt-1 text-center text-xs">{label}</figcaption>
    </figure>
  )
}

function Box({
  x,
  y,
  w,
  h,
  title,
  sub,
  tone = "blue",
}: {
  x: number
  y: number
  w: number
  h: number
  title: string
  sub?: string
  tone?: Tone
}) {
  const [fill, stroke] = FILL[tone]
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={fill} stroke={stroke} strokeWidth={1.5} />
      <text
        x={x + w / 2}
        y={y + (sub ? h / 2 - 3 : h / 2 + 4)}
        textAnchor="middle"
        fontSize={13}
        fontWeight={600}
        fill="#14203a"
      >
        {title}
      </text>
      {sub ? (
        <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fontSize={11} fill="#55627a">
          {sub}
        </text>
      ) : null}
    </g>
  )
}

function Line({
  x1,
  y1,
  x2,
  y2,
  dashed = false,
}: {
  x1: number
  y1: number
  x2: number
  y2: number
  dashed?: boolean
}) {
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke="#55627a"
      strokeWidth={1.6}
      strokeDasharray={dashed ? "5 4" : undefined}
      markerEnd="url(#verano-arrow)"
    />
  )
}

function Note({
  x,
  y,
  children,
  anchor = "middle",
  color = "#55627a",
}: {
  x: number
  y: number
  children: ReactNode
  anchor?: "start" | "middle" | "end"
  color?: string
}) {
  return (
    <text x={x} y={y} textAnchor={anchor} fontSize={11.5} fill={color}>
      {children}
    </text>
  )
}

function Diagram({ label, height, children }: { label: string; height?: number; children: ReactNode }) {
  return (
    <Frame label={label} height={height}>
      {children}
    </Frame>
  )
}

function Layers() {
  return (
    <Diagram label={LABELS["what-a-prompt-is-made-of"]} height={170}>
      {[
        ["Instruction", "blue"],
        ["Examples", "green"],
        ["Input", "gold"],
        ["Output format", "violet"],
      ].map(([title, tone], i) => (
        <Box
          key={title}
          x={20}
          y={12 + i * 38}
          w={250}
          h={32}
          title={`${i + 1}. ${title}`}
          tone={tone as Tone}
        />
      ))}
      {[0, 1, 2, 3].map((i) => (
        <Note key={i} x={282} y={33 + i * 38} anchor="start">
          {
            [
              "task, rules, output contract",
              "worked demonstrations",
              "documents, then the question",
              "schema and settings",
            ][i]
          }
        </Note>
      ))}
      <Line x1={470} y1={85} x2={505} y2={85} />
      <Box x={508} y={62} w={112} h={46} title="Model" tone="blue" />
    </Diagram>
  )
}

function Loop() {
  return (
    <Diagram label={LABELS["the-one-habit-measure-first"]} height={150}>
      <Box x={10} y={50} w={100} h={48} title="Write a" sub="prompt variant" />
      <Box x={140} y={50} w={110} h={48} title="Run every case" sub="several times" tone="green" />
      <Box x={280} y={50} w={100} h={48} title="Grade" sub="each answer" tone="gold" />
      <Box x={410} y={50} w={110} h={48} title="Gap bigger" sub="than the spread?" tone="violet" />
      <Line x1={110} y1={74} x2={138} y2={74} />
      <Line x1={250} y1={74} x2={278} y2={74} />
      <Line x1={380} y1={74} x2={408} y2={74} />
      <Box x={550} y={12} w={82} h={40} title="Keep it" tone="green" />
      <Box x={550} y={96} w={82} h={40} title="Discard" tone="red" />
      <Line x1={520} y1={66} x2={548} y2={38} />
      <Line x1={520} y1={82} x2={548} y2={112} />
      <Note x={528} y={30} anchor="end">
        yes
      </Note>
      <Note x={528} y={124} anchor="end">
        no: noise
      </Note>
    </Diagram>
  )
}

function Cot() {
  return (
    <Diagram label={LABELS["chain-of-thought"]} height={120}>
      <Box x={10} y={36} w={110} h={48} title="Question" tone="gold" />
      <Box x={160} y={12} w={120} h={30} title="Step 1" tone="blue" />
      <Box x={160} y={50} w={120} h={30} title="Step 2" tone="blue" />
      <Box x={160} y={88} w={120} h={30} title="Step 3" tone="blue" />
      <Box x={330} y={36} w={130} h={48} title="Answer:" sub="clearly marked" tone="green" />
      <Line x1={120} y1={60} x2={158} y2={30} />
      <Line x1={120} y1={60} x2={158} y2={64} />
      <Line x1={120} y1={60} x2={158} y2={100} />
      <Line x1={280} y1={30} x2={328} y2={56} />
      <Line x1={280} y1={64} x2={328} y2={60} />
      <Line x1={280} y1={100} x2={328} y2={66} />
      <Note x={480} y={64} anchor="start">
        costs extra output tokens
      </Note>
    </Diagram>
  )
}

function FewShot() {
  return (
    <Diagram label={LABELS["few-shot-examples"]} height={110}>
      <Box x={10} y={14} w={120} h={38} title="Example 1" sub="question → answer" tone="green" />
      <Box x={10} y={60} w={120} h={38} title="Example 2" sub="question → answer" tone="green" />
      <Box x={190} y={36} w={130} h={44} title="Real question" tone="gold" />
      <Box x={380} y={36} w={110} h={44} title="Model" tone="blue" />
      <Box x={540} y={36} w={92} h={44} title="Answer" sub="same shape" tone="green" />
      <Line x1={130} y1={33} x2={188} y2={54} />
      <Line x1={130} y1={79} x2={188} y2={64} />
      <Line x1={320} y1={58} x2={378} y2={58} />
      <Line x1={490} y1={58} x2={538} y2={58} />
    </Diagram>
  )
}

function JsonOrder() {
  return (
    <Diagram label={LABELS["reasoning-first-in-json"]} height={120}>
      <Note x={10} y={20} anchor="start" color="#c23b22">
        Answer first: the model must guess
      </Note>
      <Box x={10} y={28} w={120} h={30} title={'"answer": ?'} tone="red" />
      <Box x={150} y={28} w={150} h={30} title={'"reasoning": …'} tone="grey" />
      <Line x1={130} y1={43} x2={148} y2={43} />
      <Note x={10} y={84} anchor="start" color="#22804a">
        Reasoning first: the answer follows the working
      </Note>
      <Box x={10} y={92} w={150} h={26} title={'"reasoning": …'} tone="green" />
      <Box x={180} y={92} w={120} h={26} title={'"answer": 42'} tone="green" />
      <Line x1={160} y1={105} x2={178} y2={105} />
      <Note x={330} y={50} anchor="start">
        about 39 points lower in the tutorial test
      </Note>
      <Note x={330} y={108} anchor="start">
        same schema, different order
      </Note>
    </Diagram>
  )
}

function Vote() {
  return (
    <Diagram label={LABELS["majority-vote"]} height={120}>
      <Box x={10} y={38} w={110} h={44} title="Question" tone="gold" />
      <Box x={170} y={8} w={100} h={30} title="Try 1: A" tone="blue" />
      <Box x={170} y={46} w={100} h={30} title="Try 2: B" tone="blue" />
      <Box x={170} y={84} w={100} h={30} title="Try 3: A" tone="blue" />
      <Box x={330} y={38} w={110} h={44} title="Vote" sub="A wins 2 to 1" tone="violet" />
      <Box x={490} y={38} w={110} h={44} title="Answer: A" tone="green" />
      <Line x1={120} y1={60} x2={168} y2={24} />
      <Line x1={120} y1={60} x2={168} y2={61} />
      <Line x1={120} y1={60} x2={168} y2={99} />
      <Line x1={270} y1={24} x2={328} y2={54} />
      <Line x1={270} y1={61} x2={328} y2={60} />
      <Line x1={270} y1={99} x2={328} y2={66} />
      <Line x1={440} y1={60} x2={488} y2={60} />
    </Diagram>
  )
}

function Chain() {
  return (
    <Diagram label={LABELS["prompt-chaining"]} height={110}>
      <Box x={10} y={30} w={130} h={50} title="1. Extract" sub="pull out the facts" tone="blue" />
      <Box x={190} y={30} w={130} h={50} title="2. Decide" sub="apply the rule" tone="blue" />
      <Box x={370} y={30} w={130} h={50} title="3. Format" sub="write the answer" tone="blue" />
      <Line x1={140} y1={55} x2={188} y2={55} />
      <Line x1={320} y1={55} x2={368} y2={55} />
      <Line x1={500} y1={55} x2={540} y2={55} />
      <Box x={542} y={32} w={90} h={46} title="Answer" tone="green" />
      {[75, 255, 435].map((x) => (
        <g key={x}>
          <Line x1={x} y1={98} x2={x} y2={84} dashed />
          <Note x={x} y={108}>
            check
          </Note>
        </g>
      ))}
    </Diagram>
  )
}

function ContextFirst() {
  return (
    <Diagram label={LABELS["context-first-question-last"]} height={110}>
      <Box x={10} y={30} w={180} h={50} title="Reference text" sub="delimited, unchanged" tone="grey" />
      <Box x={210} y={30} w={140} h={50} title="Rules" sub="and output format" tone="blue" />
      <Box x={370} y={30} w={140} h={50} title="Question" sub="last" tone="gold" />
      <Line x1={20} y1={98} x2={500} y2={98} />
      <Note x={260} y={90}>
        the model reads in this order and can only use what it has already read
      </Note>
    </Diagram>
  )
}

function Cache() {
  return (
    <Diagram label={LABELS["prompt-caching"]} height={120}>
      <Box x={10} y={26} w={140} h={40} title="Instructions" tone="green" />
      <Box x={156} y={26} w={140} h={40} title="Examples" tone="green" />
      <Box x={302} y={26} w={150} h={40} title="Reference text" tone="green" />
      <Box x={458} y={26} w={172} h={40} title="This call's input" tone="gold" />
      <Note x={230} y={90}>
        same every call: read once, then reused
      </Note>
      <Note x={544} y={90}>
        changes every call
      </Note>
      <Note x={230} y={108} color="#22804a">
        about 100× faster, about a tenth of the price
      </Note>
    </Diagram>
  )
}

function Judge() {
  return (
    <Diagram label={LABELS["ai-judge"]} height={130}>
      <Box x={10} y={14} w={110} h={38} title="Answer" tone="blue" />
      <Box x={10} y={64} w={110} h={38} title="Rubric" tone="gold" />
      <Box x={180} y={34} w={120} h={48} title="Judge model" sub="reasoning first" tone="violet" />
      <Box x={360} y={34} w={120} h={48} title="Pass / Fail" sub="and the reason" tone="green" />
      <Line x1={120} y1={33} x2={178} y2={52} />
      <Line x1={120} y1={83} x2={178} y2={64} />
      <Line x1={300} y1={58} x2={358} y2={58} />
      <Box x={200} y={96} w={280} h={28} title="Audit against answers you labelled" tone="grey" />
      <Line x1={340} y1={96} x2={340} y2={84} dashed />
    </Diagram>
  )
}

function Injection() {
  return (
    <Diagram label={LABELS["untrusted-text-and-injection"]} height={130}>
      <Box x={10} y={12} w={150} h={38} title="Your instructions" tone="blue" />
      <Box x={10} y={62} w={150} h={54} title="Untrusted text" sub={'"ignore the rules…"'} tone="red" />
      <Box x={230} y={36} w={110} h={54} title="Model" tone="blue" />
      <Line x1={160} y1={31} x2={228} y2={54} />
      <Line x1={160} y1={89} x2={228} y2={72} />
      <Line x1={340} y1={63} x2={385} y2={63} />
      <Box x={388} y={36} w={110} h={54} title="Output" sub="may obey the text" tone="red" />
      <Note x={520} y={54} anchor="start">
        Defences:
      </Note>
      <Note x={520} y={72} anchor="start">
        mark it as data
      </Note>
      <Note x={520} y={88} anchor="start">
        test for it
      </Note>
      <Note x={520} y={104} anchor="start">
        limit what it can do
      </Note>
    </Diagram>
  )
}

function Search() {
  return (
    <Diagram label={LABELS["automatic-prompt-search"]} height={120}>
      <Box x={10} y={38} w={110} h={44} title="Your prompt" tone="blue" />
      <Box x={170} y={8} w={110} h={30} title="Candidate A" tone="violet" />
      <Box x={170} y={46} w={110} h={30} title="Candidate B" tone="violet" />
      <Box x={170} y={84} w={110} h={30} title="Candidate C" tone="violet" />
      <Box x={330} y={38} w={120} h={44} title="Score all" sub="same test cases" tone="gold" />
      <Box x={500} y={38} w={130} h={44} title="Check winner" sub="on held-back cases" tone="green" />
      <Line x1={120} y1={60} x2={168} y2={24} />
      <Line x1={120} y1={60} x2={168} y2={61} />
      <Line x1={120} y1={60} x2={168} y2={99} />
      <Line x1={280} y1={24} x2={328} y2={54} />
      <Line x1={280} y1={61} x2={328} y2={60} />
      <Line x1={280} y1={99} x2={328} y2={66} />
      <Line x1={450} y1={60} x2={498} y2={60} />
    </Diagram>
  )
}

function Elbow({ d, dashed = false }: { d: string; dashed?: boolean }) {
  return (
    <path
      d={d}
      fill="none"
      stroke="#55627a"
      strokeWidth={1.6}
      strokeDasharray={dashed ? "5 4" : undefined}
      markerEnd="url(#verano-arrow)"
    />
  )
}

function VeranoLoop() {
  const steps: [string, string, Tone][] = [
    ["Keys", "add providers", "grey"],
    ["Prompt", "write and check", "blue"],
    ["Test cases", "approve 70/30", "gold"],
    ["Run", "models x repeats", "green"],
    ["Results", "quality, cost", "violet"],
    ["Improve", "3 candidates", "blue"],
  ]
  return (
    <Diagram label={LABELS["how-verano-uses-this-guide"]} height={150}>
      {steps.map(([title, sub, tone], i) => (
        <Box key={title} x={1 + i * 110} y={30} w={88} h={48} title={title} sub={sub} tone={tone} />
      ))}
      {[0, 1, 2, 3, 4].map((i) => (
        <Line key={i} x1={89 + i * 110} y1={54} x2={109 + i * 110} y2={54} />
      ))}
      <Elbow d="M595 80 V118 H155 V82" dashed />
      <Note x={375} y={136}>
        accept the winner as a new version, then measure again
      </Note>
    </Diagram>
  )
}

function WhichFirst() {
  const cols: [string, string, string, string][] = [
    ["Wrong form?", "", "Exact format", "and allowed values"],
    ["Multi-step", "mistakes?", "Reason first", "or step by step"],
    ["Format drifts?", "", "Few-shot", "2 close examples"],
    ["Answers vary?", "", "Vote or low", "temperature"],
    ["Needs facts?", "", "Ground it", "in your documents"],
  ]
  return (
    <Diagram label={LABELS["which-technique-should-i-try-first"]} height={200}>
      {cols.map(([q, qs, fix, fs], i) => (
        <g key={q}>
          <Box x={i * 132} y={14} w={112} h={48} title={q} sub={qs || undefined} tone="gold" />
          <Line x1={i * 132 + 56} y1={62} x2={i * 132 + 56} y2={104} />
          <Note x={i * 132 + 62} y={88} anchor="start">
            yes
          </Note>
          <Box x={i * 132} y={106} w={112} h={48} title={fix} sub={fs} tone="green" />
          {i < 4 ? <Line x1={i * 132 + 112} y1={38} x2={i * 132 + 130} y2={38} dashed /> : null}
        </g>
      ))}
      <Note x={320} y={182}>
        then measure: keep the change only if the gain is bigger than the spread
      </Note>
    </Diagram>
  )
}

function Delimiters() {
  return (
    <Diagram label={LABELS["delimiters-and-labelled-sections"]} height={120}>
      <Box x={10} y={26} w={130} h={50} title={"<rules>"} sub="what to do" tone="blue" />
      <Box x={160} y={26} w={140} h={50} title={"<document>"} sub="data, not orders" tone="grey" />
      <Box x={320} y={26} w={130} h={50} title={"<question>"} sub="asked last" tone="gold" />
      <Line x1={450} y1={51} x2={498} y2={51} />
      <Box x={500} y={26} w={130} h={50} title="Model" sub="reads each part by name" tone="blue" />
      <Note x={320} y={104}>
        the same tags every time, and the instruction names them
      </Note>
    </Diagram>
  )
}

function StepBack() {
  return (
    <Diagram label={LABELS["step-back-prompting"]} height={120}>
      <Box x={10} y={20} w={110} h={48} title="Question" tone="gold" />
      <Box x={170} y={20} w={150} h={48} title="Step back" sub="state the general rule" tone="violet" />
      <Box x={370} y={20} w={110} h={48} title="Apply it" sub="to this case" tone="blue" />
      <Box x={530} y={20} w={100} h={48} title="Answer" tone="green" />
      <Line x1={120} y1={44} x2={168} y2={44} />
      <Line x1={320} y1={44} x2={368} y2={44} />
      <Line x1={480} y1={44} x2={528} y2={44} />
      <Note x={320} y={104} color="#c23b22">
        without the step, a model may jump to a specific, wrong answer
      </Note>
    </Diagram>
  )
}

function TreeOfThoughts() {
  return (
    <Diagram label={LABELS["tree-of-thoughts"]} height={150}>
      <Box x={10} y={58} w={100} h={40} title="Question" tone="gold" />
      <Box x={170} y={8} w={110} h={32} title="Idea A" tone="blue" />
      <Box x={170} y={60} w={110} h={32} title="Idea B: weak" tone="grey" />
      <Box x={170} y={112} w={110} h={32} title="Idea C" tone="blue" />
      <Box x={340} y={8} w={110} h={32} title="A, extended" tone="blue" />
      <Box x={340} y={112} w={110} h={32} title="C, extended" tone="blue" />
      <Box x={500} y={58} w={130} h={40} title="Best path" tone="green" />
      <Line x1={110} y1={72} x2={168} y2={26} />
      <Line x1={110} y1={78} x2={168} y2={76} dashed />
      <Line x1={110} y1={84} x2={168} y2={124} />
      <Line x1={280} y1={24} x2={338} y2={24} />
      <Line x1={280} y1={128} x2={338} y2={128} />
      <Line x1={450} y1={28} x2={498} y2={68} />
      <Line x1={450} y1={124} x2={498} y2={88} />
      <Note x={315} y={80} color="#8b95a7">
        dropped
      </Note>
    </Diagram>
  )
}

function Grounding() {
  return (
    <Diagram label={LABELS["grounding-in-reference-text"]} height={130}>
      <Box x={10} y={22} w={100} h={50} title="Documents" tone="grey" />
      <Box x={140} y={22} w={120} h={50} title="Find passages" sub="the relevant few" tone="violet" />
      <Box x={290} y={22} w={130} h={50} title="Prompt" sub="passages + question" tone="blue" />
      <Box x={450} y={22} w={70} h={50} title="Model" tone="blue" />
      <Box x={550} y={22} w={82} h={50} title="Answer" sub="+ source" tone="green" />
      <Line x1={110} y1={47} x2={138} y2={47} />
      <Line x1={260} y1={47} x2={288} y2={47} />
      <Line x1={420} y1={47} x2={448} y2={47} />
      <Line x1={520} y1={47} x2={548} y2={47} />
      <Note x={320} y={104} color="#22804a">
        not in the documents: reply “not found” instead of guessing
      </Note>
    </Diagram>
  )
}

function ToolLoop() {
  return (
    <Diagram label={LABELS["tool-use-and-react"]} height={150}>
      <Box x={10} y={26} w={110} h={48} title="Think" sub="what do I need?" tone="blue" />
      <Box x={170} y={26} w={120} h={48} title="Call a tool" sub="search, maths, data" tone="violet" />
      <Box x={340} y={26} w={110} h={48} title="Read result" tone="gold" />
      <Box x={520} y={26} w={110} h={48} title="Answer" tone="green" />
      <Line x1={120} y1={50} x2={168} y2={50} />
      <Line x1={290} y1={50} x2={338} y2={50} />
      <Line x1={450} y1={50} x2={518} y2={50} />
      <Note x={484} y={42}>
        enough
      </Note>
      <Elbow d="M395 76 V112 H65 V78" dashed />
      <Note x={230} y={134}>
        not enough: think again (cap the number of loops)
      </Note>
    </Diagram>
  )
}

function MetaPrompt() {
  return (
    <Diagram label={LABELS["meta-prompting"]} height={130}>
      <Box x={10} y={8} w={140} h={30} title="The task" tone="gold" />
      <Box x={10} y={50} w={140} h={30} title="Good examples" tone="green" />
      <Box x={10} y={92} w={140} h={30} title="Failures" tone="red" />
      <Box x={210} y={38} w={140} h={50} title="Prompt writer" sub="a model" tone="violet" />
      <Box x={400} y={38} w={100} h={50} title="Candidates" sub="one change each" tone="blue" />
      <Box x={540} y={38} w={90} h={50} title="Score" sub="held-back check" tone="green" />
      <Line x1={150} y1={23} x2={208} y2={54} />
      <Line x1={150} y1={65} x2={208} y2={63} />
      <Line x1={150} y1={107} x2={208} y2={74} />
      <Line x1={350} y1={63} x2={398} y2={63} />
      <Line x1={500} y1={63} x2={538} y2={63} />
    </Diagram>
  )
}

function Refine() {
  return (
    <Diagram label={LABELS["critique-and-revise-with-new-information"]} height={140}>
      <Box x={10} y={22} w={110} h={48} title="Draft answer" tone="blue" />
      <Box x={170} y={22} w={150} h={48} title="Check" sub="against new information" tone="gold" />
      <Box x={370} y={22} w={110} h={48} title="Revise" tone="violet" />
      <Box x={530} y={22} w={100} h={48} title="Better answer" tone="green" />
      <Box x={170} y={100} w={150} h={30} title="test, rule or source" tone="grey" />
      <Line x1={120} y1={46} x2={168} y2={46} />
      <Line x1={320} y1={46} x2={368} y2={46} />
      <Line x1={480} y1={46} x2={528} y2={46} />
      <Line x1={245} y1={100} x2={245} y2={72} dashed />
      <Note x={350} y={120} anchor="start" color="#c23b22">
        checking with nothing new: no gain, can get worse
      </Note>
    </Diagram>
  )
}

function ReasoningLadder() {
  return (
    <Diagram label={LABELS["use-one-or-not"]} height={130}>
      <Box x={10} y={44} w={120} h={48} title="Plain model" sub="cheap, fast" tone="blue" />
      <Box x={210} y={44} w={100} h={48} title="Low effort" sub="reasoning" tone="violet" />
      <Box x={370} y={44} w={100} h={48} title="Medium" tone="violet" />
      <Box x={530} y={44} w={100} h={48} title="High" sub="slowest, dearest" tone="violet" />
      <Line x1={130} y1={68} x2={208} y2={68} />
      <Line x1={310} y1={68} x2={368} y2={68} />
      <Line x1={470} y1={68} x2={528} y2={68} />
      <Note x={170} y={60}>
        not good
      </Note>
      <Note x={340} y={60}>
        not good
      </Note>
      <Note x={500} y={60}>
        not good
      </Note>
      <Note x={320} y={20} color="#22804a">
        stop at the first one that is good enough on your test cases
      </Note>
    </Diagram>
  )
}

function TokenBudget() {
  return (
    <Diagram label={LABELS["thinking-uses-your-token-limit"]} height={150}>
      <Note x={10} y={30} anchor="start">
        Small limit
      </Note>
      <rect x={110} y={14} width={360} height={26} rx={6} fill="#f1eefb" stroke="#5a45b0" strokeWidth={1.5} />
      <Note x={290} y={31}>
        thinking uses all of it
      </Note>
      <Note x={482} y={31} anchor="start" color="#c23b22">
        no answer left
      </Note>
      <Note x={10} y={92} anchor="start">
        Enough room
      </Note>
      <rect x={110} y={76} width={220} height={26} rx={6} fill="#f1eefb" stroke="#5a45b0" strokeWidth={1.5} />
      <Note x={220} y={93}>
        thinking
      </Note>
      <rect x={334} y={76} width={130} height={26} rx={6} fill="#e6f4ec" stroke="#22804a" strokeWidth={1.5} />
      <Note x={399} y={93}>
        answer
      </Note>
      <Note x={482} y={93} anchor="start" color="#22804a">
        full answer
      </Note>
      <Note x={320} y={136}>
        max_tokens is one budget for both, and you pay for both
      </Note>
    </Diagram>
  )
}

function ContextParts() {
  const parts: [string, "blue" | "gold" | "green" | "grey" | "violet" | "red"][] = [
    ["Role and goal", "blue"],
    ["Instructions", "blue"],
    ["Output format", "blue"],
    ["Examples", "green"],
    ["Today's date", "gold"],
    ["Documents", "gold"],
    ["Tools", "violet"],
    ["Memory", "violet"],
  ]
  return (
    <Diagram label={LABELS["the-parts-of-the-context"]} height={190}>
      {parts.map(([title, tone], i) => (
        <Box
          key={title}
          x={10 + (i % 2) * 150}
          y={8 + Math.floor(i / 2) * 36}
          w={140}
          h={28}
          title={title}
          tone={tone}
        />
      ))}
      <Box x={85} y={154} w={140} h={28} title="<input> marked" tone="grey" />
      <Box x={380} y={70} w={110} h={48} title="Model" sub="knows only this" tone="violet" />
      <Box x={540} y={70} w={90} h={48} title="Answer" tone="green" />
      <Line x1={302} y1={94} x2={378} y2={94} />
      <Line x1={490} y1={94} x2={538} y2={94} />
      <Note x={340} y={86}>
        one call
      </Note>
    </Diagram>
  )
}

function WorkflowAgent() {
  return (
    <Diagram label={LABELS["workflow-or-agent"]} height={190}>
      <Note x={10} y={22} anchor="start">
        Workflow: your code fixes the steps
      </Note>
      <Box x={10} y={32} w={110} h={40} title="Step A" tone="blue" />
      <Box x={170} y={32} w={110} h={40} title="Step B" tone="blue" />
      <Box x={330} y={32} w={110} h={40} title="Step C" tone="blue" />
      <Box x={520} y={32} w={110} h={40} title="Answer" tone="green" />
      <Line x1={120} y1={52} x2={168} y2={52} />
      <Line x1={280} y1={52} x2={328} y2={52} />
      <Line x1={440} y1={52} x2={518} y2={52} />
      <Note x={10} y={112} anchor="start">
        Agent: the model picks the next step
      </Note>
      <Box x={10} y={122} w={150} h={44} title="Model decides" sub="plan, then act" tone="violet" />
      <Box x={250} y={122} w={140} h={44} title="Tools" sub="search, data, APIs" tone="gold" />
      <Box x={520} y={122} w={110} h={44} title="Answer" tone="green" />
      <Line x1={160} y1={136} x2={248} y2={136} />
      <Line x1={248} y1={154} x2={162} y2={154} />
      <Line x1={390} y1={144} x2={518} y2={144} />
      <Note x={455} y={136}>
        when done
      </Note>
      <Note x={204} y={182}>
        loops until done
      </Note>
    </Diagram>
  )
}

function ToolCalling() {
  return (
    <Diagram label={LABELS["tool-calling-step-by-step"]} height={160}>
      <Box x={10} y={30} w={140} h={50} title="Your code" sub="request + tool list" tone="blue" />
      <Box x={200} y={30} w={130} h={50} title="Model" sub="picks tool + inputs" tone="violet" />
      <Box x={380} y={30} w={120} h={50} title="Your code" sub="runs the tool" tone="gold" />
      <Box x={540} y={30} w={90} h={50} title="Answer" tone="green" />
      <Line x1={150} y1={55} x2={198} y2={55} />
      <Line x1={330} y1={55} x2={378} y2={55} />
      <Elbow d="M440 82 V118 H265 V84" dashed />
      <Note x={352} y={136}>
        the result goes back to the model as a new message
      </Note>
      <Elbow d="M330 40 H350 V16 H585 V28" />
      <Note x={468} y={12}>
        no tool needed: answer
      </Note>
    </Diagram>
  )
}

function AgentParts() {
  return (
    <Diagram label={LABELS["testing-an-agent-with-verano-today"]} height={200}>
      <Box x={10} y={70} w={110} h={50} title="Your agent" tone="violet" />
      <Box x={200} y={6} w={200} h={36} title="Routing prompt" sub="classification" tone="blue" />
      <Box x={200} y={50} w={200} h={36} title="Planning prompt" sub="JSON output" tone="blue" />
      <Box x={200} y={94} w={200} h={36} title="Tool-choice prompt" sub="classification" tone="blue" />
      <Box x={200} y={138} w={200} h={36} title="Final-answer prompt" sub="AI judge" tone="blue" />
      <Line x1={120} y1={86} x2={198} y2={24} />
      <Line x1={120} y1={91} x2={198} y2={68} />
      <Line x1={120} y1={99} x2={198} y2={112} />
      <Line x1={120} y1={104} x2={198} y2={156} />
      <Box x={450} y={40} w={180} h={50} title="Test in Verano" sub="each one, today" tone="green" />
      <Box x={450} y={120} w={180} h={50} title="Whole agent, real tools" sub="after V1" tone="grey" />
      <path d="M404 24 H414 V156 H404" fill="none" stroke="#55627a" strokeWidth={1.6} />
      <Line x1={414} y1={65} x2={448} y2={65} />
    </Diagram>
  )
}

export const DIAGRAMS: Record<string, ReactNode> = {
  "how-verano-uses-this-guide": <VeranoLoop />,
  "which-technique-should-i-try-first": <WhichFirst />,
  "delimiters-and-labelled-sections": <Delimiters />,
  "step-back-prompting": <StepBack />,
  "tree-of-thoughts": <TreeOfThoughts />,
  "grounding-in-reference-text": <Grounding />,
  "tool-use-and-react": <ToolLoop />,
  "meta-prompting": <MetaPrompt />,
  "critique-and-revise-with-new-information": <Refine />,
  "what-a-prompt-is-made-of": <Layers />,
  "the-one-habit-measure-first": <Loop />,
  "chain-of-thought": <Cot />,
  "few-shot-examples": <FewShot />,
  "reasoning-first-in-json": <JsonOrder />,
  "majority-vote": <Vote />,
  "prompt-chaining": <Chain />,
  "context-first-question-last": <ContextFirst />,
  "prompt-caching": <Cache />,
  "ai-judge": <Judge />,
  "untrusted-text-and-injection": <Injection />,
  "use-one-or-not": <ReasoningLadder />,
  "thinking-uses-your-token-limit": <TokenBudget />,
  "the-parts-of-the-context": <ContextParts />,
  "workflow-or-agent": <WorkflowAgent />,
  "tool-calling-step-by-step": <ToolCalling />,
  "testing-an-agent-with-verano-today": <AgentParts />,
  "automatic-prompt-search": <Search />,
}
