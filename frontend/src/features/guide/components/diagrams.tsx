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
    <Diagram label="Four layers of a prompt feed the model, which writes the answer" height={170}>
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
    <Diagram
      label="The measuring loop: write a variant, run it repeatedly, grade, compare the gap with the spread"
      height={150}
    >
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
    <Diagram
      label="Chain of thought: the question, then written steps, then a marked final answer"
      height={120}
    >
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
    <Diagram label="Few-shot: solved examples come before the real question" height={110}>
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
    <Diagram label="JSON written left to right: reasoning first lets the answer use the working" height={120}>
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
    <Diagram label="Majority vote: ask three times, keep the most common answer" height={120}>
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
    <Diagram label="Prompt chaining: small prompts in a row, each checked on its own" height={110}>
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
    <Diagram label="Context first, question last: the model reads left to right" height={110}>
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
    <Diagram label="Prompt caching: an unchanged start is reused, only the end is new" height={120}>
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
    <Diagram
      label="AI judge: a second model grades the answer against a rubric, and the judge itself is audited"
      height={130}
    >
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
    <Diagram label="Injection: instructions hidden in untrusted text can reach the model" height={130}>
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
    <Diagram
      label="Automatic prompt search: candidates are scored on the same cases and the winner is checked on held-back cases"
      height={120}
    >
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

export const DIAGRAMS: Record<string, ReactNode> = {
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
  "automatic-prompt-search": <Search />,
}
