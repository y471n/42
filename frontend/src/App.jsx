import { useEffect, useState } from "react";
import "./App.css";

const SESSION_KEY = "42-session";
const philosopherPortraits = {
  "Arthur Schopenhauer": "/philosophers/schopenhauer.jpg",
  "Baruch Spinoza": "/philosophers/spinoza.jpg",
  "David Hume": "/philosophers/hume.jpg",
  "Immanuel Kant": "/philosophers/kant.jpg",
  "John Stuart Mill": "/philosophers/mill.jpg",
  "Mary Wollstonecraft": "/philosophers/wollstonecraft.jpg",
  "Michel de Montaigne": "/philosophers/montaigne.jpg",
  "Sophie de Grouchy": "/philosophers/grouchy.jpg",
  "William James": "/philosophers/james.jpg",
};
const traceNodes = [
  {
    group: "select_topic",
    number: "01",
    name: "Understand the question",
    type: "ROUTER",
  },
  {
    group: "research",
    number: "02",
    name: "Research & discovery",
    type: "SUBGRAPH",
  },
  {
    group: "roundtable",
    number: "03",
    name: "Philosophers’ roundtable",
    type: "SUBGRAPH",
  },
  {
    group: "future_a",
    number: "04A",
    name: "Imagine path one",
    type: "OPTIONAL WORKER",
  },
  {
    group: "future_b",
    number: "04B",
    name: "Imagine path two",
    type: "OPTIONAL WORKER",
  },
  {
    group: "critic",
    number: "05",
    name: "Critique the ideas",
    type: "CONDITIONAL LOOP",
  },
  {
    group: "curate",
    number: "06",
    name: "Curate the exhibit",
    type: "SYNTHESIS",
  },
  {
    group: "review",
    number: "07",
    name: "Your review",
    type: "HUMAN IN THE LOOP",
  },
];

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check your input and try again.",
    );
  }
  return data;
}

function Arrow({ diagonal = false }) {
  return (
    <span aria-hidden="true" className="button-arrow">
      {diagonal ? "↗" : "→"}
    </span>
  );
}

function ModerationText({ text = "" }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("*") && part.endsWith("*")) {
          return <em key={`${part}-${index}`}>{part.slice(1, -1)}</em>;
        }
        return <span key={`${part}-${index}`}>{part}</span>;
      })}
    </>
  );
}

function ThinkerPortrait({ name, compact = false }) {
  const portrait = philosopherPortraits[name];
  return (
    <div
      className={`thinker-portrait ${compact ? "thinker-portrait-compact" : ""}`}
      aria-label={portrait ? `Portrait of ${name}` : undefined}
      role={portrait ? "img" : undefined}
    >
      {portrait && (
        <img
          src={portrait}
          alt=""
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      )}
    </div>
  );
}

function Logo() {
  return (
    <a className="brand" href="/" aria-label="42, home">
      <span className="brand-mark" aria-hidden="true">
        42
      </span>
      <span>
        FORTY
        <br />
        TWO<span className="brand-period">.</span>
      </span>
    </a>
  );
}

function HallArtwork() {
  return (
    <div className="zine-cover" aria-hidden="true">
      <div className="zine-tape" />
      <div className="zine-cover-top">
        <span>FIELD NOTES / VOL. 001</span>
        <span>AN UNFINISHED PUBLICATION</span>
      </div>
      <div className="zine-collage">
        <div className="zine-circle" />
        <div className="zine-cutout zine-cutout-one">WHAT</div>
        <div className="zine-cutout zine-cutout-two">
          IF<span>?</span>
        </div>
        <div className="zine-eye">
          <div className="zine-pupil" />
        </div>
        <div className="zine-scribble">
          a field guide
          <br />
          for the <em>undecided</em> ↗
        </div>
      </div>
      <div className="zine-cover-bottom">
        <span>FOR THE THINGS WE ALMOST DID</span>
        <span>ISSUE 01 / ∞</span>
      </div>
      <div className="zine-stamp">
        OPEN
        <br />
        TO
        <br />
        DOUBT <span>✳</span>
      </div>
    </div>
  );
}

function Landing({ onStart, busy, error }) {
  const [dilemma, setDilemma] = useState("");

  function submit(event) {
    event.preventDefault();
    onStart({ dilemma: dilemma.trim() });
  }

  return (
    <>
      <section className="hero wrap">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="eyebrow-line" /> A FIELD GUIDE TO BEING HUMAN /
            ISSUE 01
          </div>
          <h1>
            For the questions
            <br />
            that <em>stay</em> with you<span className="hero-dot">.</span>
          </h1>
          <p className="hero-description">
            A small publication for big questions. Bring a philosophical puzzle,
            a personal dilemma, or an idea you’d like to explore.
          </p>
          <a className="text-link" href="#your-question">
            Begin with a question <span aria-hidden="true">↘</span>
          </a>
          <div className="hero-ticket">
            <span>A NOTE TO SELF / 001</span>
            <strong>
              Not knowing
              <br />
              <em>is allowed.</em>
            </strong>
            <span>KEEP THIS CLOSE ↗</span>
          </div>
        </div>
        <HallArtwork />
        <div className="hero-footnote">
          <span>AN EXPERIMENT IN SELF-DISCOVERY</span>
          <span>SCROLL TO EXPLORE ↓</span>
        </div>
      </section>

      <div className="fortytwo-ribbon" aria-hidden="true">
        <div>
          THINKING IS A CONTACT SPORT <span>✳</span> QUESTION EVERYTHING
          (INCLUDING THIS) <span>✳</span> THINKING IS A CONTACT SPORT{" "}
          <span>✳</span> QUESTION EVERYTHING
        </div>
      </div>

      <section className="intro-band">
        <div className="wrap intro-band-inner">
          <span className="section-index">
            EDITOR’S NOTE
            <br />
            NO. 001 / PLEASE READ
          </span>
          <p>
            No crystal ball. No perfect answer.
            <br />
            <em>Just a more interesting question.</em>
          </p>
          <span className="intro-mark" aria-hidden="true">
            ✳
          </span>
        </div>
      </section>

      <section id="your-question" className="question-section wrap">
        <div className="section-heading">
          <span className="section-index">01 / THE QUESTION ON THE TABLE</span>
          <h2>
            What’s on
            <br />
            <em>your mind?</em>
          </h2>
          <p>
            Bring the question that has been quietly following you around. There
            are no wrong answers here.
          </p>
          <div className="aside-note">
            <span aria-hidden="true">✳</span> YOUR STORY STAYS ON THIS MACHINE.
            <br />
            ONLY BROAD TOPICS ARE SEARCHED ONLINE.
          </div>
        </div>
        <div className="form-shell">
          <form className="question-form" onSubmit={submit}>
            <div className="form-header">
              <span>FIELD NOTES / YOUR TURN</span>
              <span>FILE UNDER: WHAT IF</span>
            </div>
            <label htmlFor="dilemma">
              The question on your mind <span>01</span>
            </label>
            <textarea
              id="dilemma"
              required
              maxLength={4000}
              rows={3}
              value={dilemma}
              onChange={(event) => setDilemma(event.target.value)}
              placeholder="What makes a life meaningful?"
            />
            <p className="question-examples">
              Try a big idea, like “Is free will real?”, or a decision you’re
              facing.
            </p>
            {error && (
              <p className="error-message" role="alert">
                {error}
              </p>
            )}
            <button
              className="primary-button"
              disabled={busy || !dilemma.trim()}
              type="submit"
            >
              <span>
                {busy ? "Opening your discussion…" : "Explore this question"}
              </span>
              <Arrow />
            </button>
            <p className="form-caption">
              Takes a few minutes · Your words are sent only to your local model
            </p>
          </form>
        </div>
      </section>

      <section className="how-section">
        <div className="wrap">
          <div className="how-header">
            <span className="section-index">02 / THE THINKING MACHINE</span>
            <h2>
              A little philosophy.
              <br />
              <em>A lot of perspective.</em>
            </h2>
          </div>
          <div className="how-grid">
            <div>
              <span className="how-number">01</span>
              <h3>Ideas, not answers.</h3>
              <p>
                We look for philosophical perspectives relevant to your
                question, with links back to their sources.
              </p>
            </div>
            <div>
              <span className="how-number">02</span>
              <h3>A conversation.</h3>
              <p>
                AI-generated perspectives meet at a roundtable. A moderator
                draws out the tensions between them.
              </p>
            </div>
            <div>
              <span className="how-number">03</span>
              <h3>Room to reflect.</h3>
              <p>
                Explore the ideas, continue the conversation, and, for clear
                choices, imagine possible futures.
              </p>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

function ThreadSidebar({
  threads,
  sessionId,
  onSelect,
  onNew,
  error,
  onRetry,
}) {
  return (
    <aside className="thread-sidebar" aria-label="Your conversations">
      <div className="sidebar-heading">
        <span className="section-index">YOUR FIELD NOTES</span>
        <button onClick={onNew} className="sidebar-new">
          + New question
        </button>
      </div>
      <p className="sidebar-caption">Saved on this machine</p>
      {error && (
        <div className="sidebar-error" role="alert">
          {error}{" "}
          <button className="text-button" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
      <nav aria-label="Saved conversations">
        {threads.length ? (
          threads.map((thread) => (
            <button
              key={thread.id}
              className={`thread-link ${thread.id === sessionId ? "is-active" : ""}`}
              onClick={() => onSelect(thread.id)}
              aria-current={thread.id === sessionId ? "page" : undefined}
            >
              <span>{thread.question}</span>
              <small>{thread.status.replaceAll("_", " ")}</small>
            </button>
          ))
        ) : (
          <p className="sidebar-empty">Your questions will appear here.</p>
        )}
      </nav>
    </aside>
  );
}

function Clarify({ session, busy, error, onClarify }) {
  const [answer, setAnswer] = useState("");
  const events = (session.trace || []).map((event, index) => ({
    ...event,
    index,
  }));
  function submit(event) {
    event.preventDefault();
    onClarify(answer.trim());
  }
  return (
    <main className="work-area wrap">
      <div className="work-heading">
        <span className="section-index">A QUESTION BEFORE WE BEGIN</span>
        <h1>
          Let’s get
          <br />
          <em>clearer.</em>
        </h1>
        <p>{session.clarification_question}</p>
        <form className="clarify-form" onSubmit={submit}>
          <label htmlFor="clarification">Your response</label>
          <textarea
            id="clarification"
            rows={4}
            maxLength={4000}
            required
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Tell us a little more…"
          />
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
          <button
            className="primary-button"
            disabled={busy || !answer.trim()}
            type="submit"
          >
            Continue <Arrow />
          </button>
        </form>
      </div>
      <section className="progress-card" aria-label="Latest activity">
        <div className="progress-top">
          <span>THE LATEST</span>
          <span>{events.length} EVENTS</span>
        </div>
        <ActivityList events={events.slice(-3).reverse()} />
      </section>
      <TraceInspector trace={session.trace || []} running />
    </main>
  );
}

function ProgressOrbit({ session, events }) {
  const steps = [
    { number: "01", name: "Question", groups: ["understand_paths", "clarify_paths", "select_topic"] },
    { number: "02", name: "Research", groups: ["research", "assess_follow_up"] },
    { number: "03", name: "Roundtable", groups: ["roundtable"] },
    { number: "04", name: "Futures", groups: ["future_a", "future_b"] },
    { number: "05", name: "Critique", groups: ["critic", "revise"] },
    { number: "06", name: "Exhibit", groups: ["curate", "review"] },
  ];
  const completed = steps.map((step) =>
    step.groups.some((group) => events.some((event) => event.group === group)),
  );
  let active = completed.findIndex((done) => !done);
  if (active < 0) active = steps.length - 1;
  if (active > 3 && events.some((event) =>
    event.node === "understand_paths" &&
    event.details.some((detail) =>
      detail.label === "Mode" && detail.value === "Open discussion",
    ),
  )) active = 5;

  return (
    <section className="progress-orbit" aria-label="Conversation progress">
      <div className="orbit-visual" aria-hidden="true">
        <div className="orbit-ring orbit-ring-one" />
        <div className="orbit-ring orbit-ring-two" />
        <div className="orbit-core">
          <span>{String(active + 1).padStart(2, "0")}</span>
          <strong>of 06</strong>
        </div>
        <span className="orbit-moon" />
      </div>
      <div className="orbit-status" role="status" aria-live="polite">
        <span>NOW THINKING / STEP {String(active + 1).padStart(2, "0")}</span>
        <strong>{session.stage || "Preparing your question"}</strong>
      </div>
      <ol className="progress-steps">
        {steps.map((step, index) => {
          const state = index < active
            ? "complete"
            : index === active
              ? "active"
              : "waiting";
          return (
            <li className={`progress-step progress-step-${state}`} key={step.number}>
              <span>{step.number}</span>
              <i aria-hidden="true" />
              <strong>{step.name}</strong>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Loading({ session, error, onRetry }) {
  const trace = session.trace || [];
  const events = trace.map((event, index) => ({ ...event, index }));
  const latest = events.slice(-3).reverse();
  return (
    <main className="work-area wrap">
      <div className="work-heading">
        <span className="section-index">YOUR EXHIBIT IS TAKING SHAPE</span>
        <h1>
          Good questions
          <br />
          <em>take a little time.</em>
        </h1>
        <p>
          Your local model is thinking. This can take several minutes; you can
          return to this tab while it works.
        </p>
        <ProgressOrbit session={session} events={events} />
        {error && (
          <div className="error-actions">
            <p className="error-message" role="alert">
              {error}
            </p>
            <button className="text-button" onClick={onRetry}>
              Retry connection
            </button>
          </div>
        )}
      </div>
      <section className="progress-card" aria-label="Latest activity">
        <div className="progress-top">
          <span className="latest-live-loader" aria-label="Latest activity is updating">
            <i aria-hidden="true" />
            THE LATEST / LIVE
          </span>
          <span>{events.length} EVENTS</span>
        </div>
        <p className="activity-intro">
          Completed steps appear here as they happen.
        </p>
        <ActivityList events={latest} />
      </section>
      <section className="work-conversation" aria-label="Live conversation">
        <LiveRoundtable events={events} running />
      </section>
      <section className="activity-timeline">
        <div className="activity-timeline-heading">
          <div>
            <span className="record-loader" aria-label="Process record is updating">
              <i aria-hidden="true" />
              THE RUNNING RECORD
            </span>
            <h2>
              Notes from <em>the process.</em>
            </h2>
          </div>
          <p>
            Every completed action, in the order it arrived. The newest is
            first.
          </p>
        </div>
        <ActivityList events={[...events].reverse()} />
      </section>
      <TraceInspector trace={trace} running />
    </main>
  );
}

function ActivityList({ events }) {
  const omitted = [
    "Thinker",
    "Verified excerpts",
    "Verification",
    "Source list",
  ];
  return events.length ? (
    <ol className="activity-list">
      {events.map((event) => (
        <li className="activity-item" key={event.index}>
          <span className="activity-number">
            {String(event.index + 1).padStart(2, "0")}
          </span>
          <div>
            <h3>{event.title}</h3>
            {event.details
              .filter((detail) => !omitted.includes(detail.label))
              .slice(0, 2)
              .map((detail, index) => {
                const value =
                  detail.value.length > 230
                    ? `${detail.value.slice(0, 230)}…`
                    : detail.value;
                return (
                  <p key={`${detail.label}-${index}`}>
                    <strong>{detail.label}:</strong> {value}
                  </p>
                );
              })}
          </div>
        </li>
      ))}
    </ol>
  ) : (
    <p className="trace-empty">Waiting for the first completed step.</p>
  );
}

function TraceNode({ node, events, skipped = false }) {
  return (
    <details className={`trace-node ${events.length ? "has-events" : ""}`}>
      <summary>
        <span className="trace-node-number">{node.number}</span>
        <span className="trace-node-heading">
          <strong>{node.name}</strong>
          <small>{node.type}</small>
        </span>
        <span className="trace-node-count">
          {events.length
            ? `${events.length} ${events.length === 1 ? "EVENT" : "EVENTS"}`
            : skipped
              ? "SKIPPED"
              : "AWAITING"}
        </span>
        <span className="trace-chevron" aria-hidden="true">
          +
        </span>
      </summary>
      <div className="trace-events">
        {events.length ? (
          events.map((event) => (
            <details className="trace-event" key={event.index}>
              <summary>
                <span className="trace-event-index">
                  {String(event.index + 1).padStart(2, "0")}
                </span>
                <span>{event.title}</span>
                <span aria-hidden="true">↗</span>
              </summary>
              <dl>
                {event.details.map((detail, index) => (
                  <div key={`${detail.label}-${index}`}>
                    <dt>{detail.label}</dt>
                    <dd>{detail.value}</dd>
                  </div>
                ))}
              </dl>
            </details>
          ))
        ) : (
          <p className="trace-empty">
            {skipped
              ? "Not needed for this open question."
              : "No completed activity recorded yet."}
          </p>
        )}
      </div>
    </details>
  );
}

function LiveRoundtable({ events, running }) {
  const discussion = events.filter(
    (event) =>
      event.group === "roundtable" &&
      ["philosopher", "moderator", "skip"].includes(event.node),
  );
  const perspectiveCount = discussion.filter(
    (event) => event.node === "philosopher",
  ).length;
  const detail = (event, label) =>
    event.details.find((item) => item.label === label)?.value;

  return (
    <section className="live-roundtable">
      <div className="live-roundtable-heading">
        <div>
          <span className="section-index light-index">
            {running ? "A CONVERSATION IN PROGRESS" : "FROM THE DISCUSSION"}
          </span>
          <h3>
            At the <em>roundtable.</em>
          </h3>
        </div>
        <span className="roundtable-count">
          {perspectiveCount}{" "}
          {perspectiveCount === 1 ? "PERSPECTIVE" : "PERSPECTIVES"}
        </span>
      </div>
      <p className="live-roundtable-note">
        AI-generated interpretations, not the thinkers’ own words. Responses
        appear when each contribution completes.
      </p>
      <div
        className="live-discussion"
        role="log"
        aria-label="Roundtable discussion"
        aria-relevant="additions"
      >
        {discussion.length ? (
          discussion.map((event, position) => {
            if (event.node === "moderator" || event.node === "skip") {
              return (
                <article
                  className="live-turn live-moderator"
                  key={event.index}
                >
                  <span className="moderator-seal" aria-hidden="true">✳</span>
                  <div className="roundtable-speaker-label">
                    <strong>THE MODERATOR</strong>
                    <small>THE TABLE’S REFLECTION</small>
                  </div>
                  <p>
                    <ModerationText text={
                      detail(
                        event,
                        event.node === "moderator" ? "Distillation" : "Reason",
                      ) || ""
                    } />
                  </p>
                  {detail(event, "Decision") && (
                    <small>{detail(event, "Decision")}</small>
                  )}
                </article>
              );
            }
            const thinker =
              detail(event, "Thinker") ||
              event.title.replace(/^.*· /, "");
            return (
              <article
                className={`live-turn roundtable-seat ${position % 2 ? "roundtable-seat-right" : "roundtable-seat-left"}`}
                key={event.index}
              >
                <div className="roundtable-seat-person">
                  <ThinkerPortrait name={thinker} compact />
                  <div className="roundtable-speaker-label">
                    <strong>{thinker}</strong>
                    <small>SEAT {String(position + 1).padStart(2, "0")}</small>
                  </div>
                </div>
                <p>
                  {detail(event, "Perspective")}
                </p>
                {detail(event, "Verification") && (
                  <small>{detail(event, "Verification")}</small>
                )}
              </article>
            );
          })
        ) : (
          <p className="live-discussion-empty">
            {running
              ? "The first perspectives will appear here as they finish."
              : "No roundtable contributions were recorded for this session."}
          </p>
        )}
      </div>
    </section>
  );
}

function TraceInspector({ trace, running = false }) {
  const events = trace.map((event, index) => ({ ...event, index }));
  const isGeneral = events.some(
    (event) =>
      event.node === "understand_paths" &&
      event.details.some(
        (detail) =>
          detail.label === "Mode" && detail.value === "Open discussion",
      ),
  );
  const renderNode = (node) => (
    <TraceNode
      key={node.group}
      node={node}
      events={events.filter(
        (event) =>
          event.group === node.group ||
          (node.group === "critic" && event.group === "revise") ||
          (node.group === "select_topic" &&
            ["understand_paths", "clarify_paths"].includes(event.group)) ||
          (node.group === "research" && event.group === "assess_follow_up"),
      )}
      skipped={isGeneral && ["future_a", "future_b"].includes(node.group)}
    />
  );

  const body = (
    <div className="trace-inner">
      <div className="trace-intro">
        <div>
          <span className="section-index">THE WORK BEHIND THE WORDS</span>
          <h2>
            Inside the <em>process.</em>
          </h2>
        </div>
        <p>
          Explore the actual completed steps, from research to review. Open a
          node to see what happened inside.
        </p>
      </div>
      {!running && <LiveRoundtable events={events} running={false} />}
      <div className="trace-legend">
        <span className="graph-loader" aria-label="Graph activity is updating">
          <i aria-hidden="true" />
          RECORDED ACTIVITY
        </span>
        <span>LANGGRAPH / LOCAL ORCHESTRATION</span>
      </div>
      {!running && !events.length && (
        <p className="trace-notice">
          No activity was recorded for this session. New sessions will show
          their trace here.
        </p>
      )}
      <div className="trace-graph">
        {traceNodes.slice(0, 3).map(renderNode)}
        <div className="trace-branch">
          <div className="trace-branch-label">OPTIONAL FOR TWO CHOICES</div>
          <div className="trace-branch-nodes">
            {traceNodes.slice(3, 5).map(renderNode)}
          </div>
        </div>
        {traceNodes.slice(5).map(renderNode)}
      </div>
      <p className="trace-footnote">
        Events appear when a step completes. Imagined futures are only created
        for questions with two clear choices; the roundtable has at most four
        contributions.
      </p>
    </div>
  );

  return running ? (
    <section className="trace-panel trace-live" aria-label="Graph inspector">
      {body}
    </section>
  ) : (
    <details className="trace-panel trace-archive">
      <summary>
        <span>✳</span> Explore how this exhibit was made{" "}
        <span aria-hidden="true">↗</span>
      </summary>
      {body}
    </details>
  );
}

function sourceUrl(id, sources) {
  const url = sources?.find((source) => source.id === id)?.url;
  if (!url) return null;
  try {
    const parsed = new URL(url, window.location.origin);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function Citation({ citation, sources }) {
  const url = sourceUrl(citation.source_id, sources);
  return (
    <blockquote className="citation">
      “{citation.quote}”{" "}
      {url && (
        <a href={url} target="_blank" rel="noreferrer">
          [{citation.source_id}] ↗
        </a>
      )}
    </blockquote>
  );
}

function Letter({ label, option, letter, sources }) {
  if (!letter) return null;
  return (
    <article className="letter-card">
      <div className="letter-top">
        <span>{label}</span>
        <span>AN IMAGINED FUTURE</span>
      </div>
      <h3>{option}</h3>
      <div className="letter-body">{letter.text}</div>
      {letter.citations?.map((citation, index) => (
        <Citation
          key={`${citation.source_id}-${index}`}
          citation={citation}
          sources={sources}
        />
      ))}
      <div className="letter-signature">A life, imagined.</div>
    </article>
  );
}

function downloadExhibit(session) {
  const blob = new Blob([session.exhibit], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `42-${session.id}.md`;
  link.click();
  URL.revokeObjectURL(url);
}

function Exhibit({ session, onReview, onFollowUp, onNew, busy, error }) {
  const [notes, setNotes] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [showRevision, setShowRevision] = useState(false);
  const turns = session.discussion_turns || [];
  const sources = session.sources || [];
  const issues = session.critique?.needs_revision
    ? session.critique.issues || []
    : [];
  const warnings = [...(session.warnings || []), ...issues];
  const hasFutures = Boolean(session.future_a && session.future_b);

  return (
    <main className="exhibit-page wrap">
      <div className="exhibit-heading">
        <span className="section-index">
          YOUR PERSONAL EXHIBIT /{" "}
          {session.status === "approved" ? "SAVED" : "READY FOR REVIEW"}
        </span>
        <h1>
          {hasFutures ? "Two lives." : "Many ideas."}
          <br />
          <em>One question.</em>
        </h1>
        <p className="exhibit-question">“{session.dilemma}”</p>
        <div className="exhibit-disclaimer">
          <span aria-hidden="true">✳</span>{" "}
          {hasFutures
            ? "THESE LETTERS ARE FICTION, NOT PREDICTIONS OR PROFESSIONAL ADVICE."
            : "THESE VOICES ARE AI-GENERATED INTERPRETATIONS, NOT THE THINKERS’ OWN WORDS."}
        </div>
      </div>

      <TraceInspector trace={session.trace || []} />

      {hasFutures && (
        <>
          <div className="exhibit-section-title">
            <div>
              <span className="section-index">01 / THE LETTERS</span>
              <h2>
                From the other side
                <br />
                <em>of the decision.</em>
              </h2>
            </div>
            <p>
              Two imagined futures, written from the same question. Neither is
              the right answer.
            </p>
          </div>
          <div className="letters-grid">
            <Letter
              label="POSSIBILITY 01"
              option={session.option_a}
              letter={session.future_a}
              sources={sources}
            />
            <Letter
              label="POSSIBILITY 02"
              option={session.option_b}
              letter={session.future_b}
              sources={sources}
            />
          </div>
        </>
      )}

      <section className="roundtable-section">
        <div className="roundtable-header">
          <div>
            <span className="section-index light-index">
              02 / THE ROUNDTABLE
            </span>
            <h2>
              Ideas in
              <br />
              <em>conversation.</em>
            </h2>
          </div>
          <p>
            AI-generated interpretations inspired by sources—not statements or
            endorsements by the thinkers.
          </p>
        </div>
        {session.messages?.length ? (
          <div className="thread-messages">
            {session.messages.map((message, index) => (
              <div
                className={`thread-message thread-message-${message.role}`}
                key={index}
              >
                {message.content && (
                  <p>
                    <strong>
                      {message.role === "user" ? "You" : "Curator"}:
                    </strong>{" "}
                    {message.content}
                  </p>
                )}
                {message.turns?.map((turn, i) => (
                  <article
                    className={`turn roundtable-seat ${i % 2 ? "roundtable-seat-right" : "roundtable-seat-left"}`}
                    key={`${turn.thinker}-${i}`}
                  >
                    <div className="roundtable-seat-person">
                      <div className="roundtable-speaker-label">
                        <strong>{turn.thinker}</strong>
                        <small>SEAT {String(i + 1).padStart(2, "0")}</small>
                      </div>
                      <ThinkerPortrait name={turn.thinker} />
                    </div>
                    <p>{turn.text}</p>
                    {turn.citations?.map((citation, j) => (
                      <Citation
                        key={`${citation.source_id}-${j}`}
                        citation={citation}
                        sources={sources}
                      />
                    ))}
                    {turn.unverified && (
                      <small>
                        Some citations or inline quotations could not be
                        verified.
                      </small>
                    )}
                  </article>
                ))}
                {message.distillation && (
                  <div className="distillation moderator-distillation">
                    <span className="section-index light-index">
                      THE MODERATOR’S REFLECTION
                    </span>
                    <p><ModerationText text={message.distillation} /></p>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : turns.length ? (
          <div className="turns">
            {turns.map((turn, index) => (
              <article
                className={`turn roundtable-seat ${index % 2 ? "roundtable-seat-right" : "roundtable-seat-left"}`}
                key={`${turn.thinker}-${turn.round}-${index}`}
              >
                <div className="roundtable-seat-person">
                  <div className="roundtable-speaker-label">
                    <strong>{turn.thinker}</strong>
                    <small>SEAT {String(index + 1).padStart(2, "0")}</small>
                  </div>
                  <ThinkerPortrait name={turn.thinker} />
                </div>
                <p>{turn.text}</p>
                {turn.citations?.map((citation, i) => (
                  <Citation
                    key={`${citation.source_id}-${i}`}
                    citation={citation}
                    sources={sources}
                  />
                ))}
                {turn.unverified && (
                  <small>
                    Some citations or inline quotations could not be verified.
                  </small>
                )}
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-note">
            Not enough distinct source-linked perspectives were found for a
            roundtable.
          </p>
        )}
        {!session.messages?.length && (
          <div className="distillation">
            <span className="section-index light-index">
              THE MODERATOR’S REFLECTION
            </span>
            <p><ModerationText text={session.distillation} /></p>
          </div>
        )}
        <form
          className="follow-up-form"
          onSubmit={(event) => {
            event.preventDefault();
            onFollowUp(followUp.trim());
          }}
        >
          <label htmlFor="follow-up">Continue the conversation</label>
          <textarea
            id="follow-up"
            rows={3}
            maxLength={4000}
            required
            value={followUp}
            onChange={(event) => setFollowUp(event.target.value)}
            placeholder="What would you like to explore next?"
          />
          {error && (
            <p className="review-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="cream-button"
            disabled={busy || !followUp.trim()}
            type="submit"
          >
            Ask the roundtable <Arrow />
          </button>
        </form>
      </section>

      <section className="reflection-section">
        <div className="reflection-intro">
          <span className="section-index">03 / THE TAKEAWAY</span>
          <h2>
            What stays
            <br />
            <em>with you?</em>
          </h2>
          <p>
            {hasFutures
              ? "Perhaps the most important things aren’t on either side of the choice."
              : "Take the ideas that invite you to think a little further."}
          </p>
        </div>
        <div className="reflection-content">
          <div className="reflection-block">
            <span className="section-index">
              {hasFutures
                ? "WHAT SURVIVES IN BOTH LIVES"
                : "THEMES TO CONSIDER"}
            </span>
            <ul>
              {session.reflection?.shared_values?.map((value, i) => (
                <li key={i}>{value}</li>
              ))}
            </ul>
          </div>
          <div className="reflection-block">
            <span className="section-index">QUESTIONS TO SIT WITH</span>
            <ul>
              {session.reflection?.questions?.map((question, i) => (
                <li key={i}>{question}</li>
              ))}
            </ul>
          </div>
          {session.reflection?.experiment && (
            <div className="experiment">
              <span className="section-index">ONE SMALL EXPERIMENT</span>
              <p>{session.reflection.experiment}</p>
            </div>
          )}
        </div>
      </section>

      <section className="sources-section">
        <div>
          <span className="section-index">04 / THE FOOTNOTES</span>
          <h2>
            Follow the
            <br />
            <em>thoughts.</em>
          </h2>
          <p>
            Quotes are checked against retrieved text, but that does not verify
            attribution or interpretation. Read the sources for yourself.
          </p>
        </div>
        <div className="source-list">
          {sources.length ? (
            sources.map((source) => {
              const url = sourceUrl(source.id, sources);
              return (
                <div className="source-row" key={source.id}>
                  <span>{source.id}</span>
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer">
                      {source.title} <span>↗</span>
                    </a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                </div>
              );
            })
          ) : (
            <p>No sources were retrieved.</p>
          )}
          {warnings.length > 0 && (
            <div className="limitations">
              <strong>Things to take with a grain of salt</strong>
              <ul>
                {warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      <section className="review-section">
        <div>
          <span className="section-index light-index">05 / YOUR TURN</span>
          <h2>
            Take what
            <br />
            <em>resonates.</em>
          </h2>
          <p>
            {session.status === "approved"
              ? "Your exhibit has been saved on this machine."
              : "This is yours to question, revise, or keep."}
          </p>
        </div>
        <div className="review-controls">
          {error && (
            <p className="review-error" role="alert">
              {error}
            </p>
          )}
          {(session.status === "review" || session.status === "approved") && (
            <>
              {showRevision && (
                <>
                  <label htmlFor="notes">What would you like to change?</label>
                  <textarea
                    id="notes"
                    rows={3}
                    maxLength={4000}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder={
                      hasFutures
                        ? "Make the first future more hopeful…"
                        : "Explore the disagreement about happiness in more depth…"
                    }
                  />
                </>
              )}
              <button
                className="cream-button"
                disabled={busy}
                onClick={() => onReview("approve", "")}
              >
                Save this exhibit <Arrow />
              </button>
              {showRevision ? (
                <button
                  className="outline-button"
                  disabled={busy || !notes.trim()}
                  onClick={() => onReview("revise", notes.trim())}
                >
                  Request revision <Arrow />
                </button>
              ) : (
                <button
                  className="outline-button"
                  disabled={busy}
                  onClick={() => setShowRevision(true)}
                >
                  Make a revision <Arrow />
                </button>
              )}
            </>
          )}
          {session.status === "approved" && (
            <button
              className="cream-button"
              onClick={() => downloadExhibit(session)}
            >
              Download Markdown <Arrow />
            </button>
          )}
          <button className="subtle-button" onClick={onNew}>
            Start another question ↗
          </button>
        </div>
      </section>
      {session.status === "review" && (
        <span className="exhibit-brand-mark" aria-label="42">
          42
        </span>
      )}
    </main>
  );
}

function App() {
  const [sessionId, setSessionId] = useState(
    () => sessionStorage.getItem(SESSION_KEY) || "",
  );
  const [session, setSession] = useState(null);
  const [threads, setThreads] = useState([]);
  const [threadError, setThreadError] = useState("");
  const [threadRefresh, setThreadRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    request("/api/sessions")
      .then((data) => {
        if (active) {
          setThreads(data);
          setThreadError("");
        }
      })
      .catch((problem) => {
        if (active)
          setThreadError(`Could not load conversations: ${problem.message}`);
      });
    return () => {
      active = false;
    };
  }, [sessionId, session?.status, threadRefresh]);

  useEffect(() => {
    if (!sessionId) return undefined;
    let active = true;
    let timer;
    async function poll() {
      try {
        const data = await request(`/api/sessions/${sessionId}`);
        if (!active) return;
        setSession(data);
        setError("");
        if (data.status === "running") timer = setTimeout(poll, 2500);
      } catch (problem) {
        if (active) setError(`Could not load this session: ${problem.message}`);
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [sessionId, refresh]);

  async function start(data) {
    setBusy(true);
    setError("");
    try {
      const result = await request("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      sessionStorage.setItem(SESSION_KEY, result.id);
      setSession({
        id: result.id,
        status: "running",
        stage: "Preparing your question",
      });
      setSessionId(result.id);
      window.scrollTo(0, 0);
    } catch (problem) {
      setError(`Could not start: ${problem.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function review(action, notes) {
    setBusy(true);
    setError("");
    try {
      await request(`/api/sessions/${sessionId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, notes }),
      });
      setSession((current) => ({
        ...current,
        status: "running",
        stage: "Applying your review",
      }));
      setRefresh((value) => value + 1);
      window.scrollTo(0, 0);
    } catch (problem) {
      setError(`Could not submit review: ${problem.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function clarify(clarification) {
    setBusy(true);
    setError("");
    try {
      await request(`/api/sessions/${sessionId}/clarify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clarification }),
      });
      setSession((current) => ({
        ...current,
        status: "running",
        stage: "Considering your clarification",
      }));
      setRefresh((value) => value + 1);
      window.scrollTo(0, 0);
    } catch (problem) {
      setError(`Could not submit clarification: ${problem.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function followUp(question) {
    setBusy(true);
    setError("");
    try {
      await request(`/api/sessions/${sessionId}/follow-up`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      setSession((current) => ({
        ...current,
        status: "running",
        stage: "Considering your follow-up",
      }));
      setRefresh((value) => value + 1);
      window.scrollTo(0, 0);
    } catch (problem) {
      setError(`Could not continue: ${problem.message}`);
    } finally {
      setBusy(false);
    }
  }

  function selectThread(id) {
    sessionStorage.setItem(SESSION_KEY, id);
    setSession(null);
    setError("");
    setSessionId(id);
    if (id === sessionId) setRefresh((value) => value + 1);
    window.scrollTo(0, 0);
  }

  function reset() {
    sessionStorage.removeItem(SESSION_KEY);
    setSessionId("");
    setSession(null);
    setError("");
    window.scrollTo(0, 0);
  }

  return (
    <div className="site">
      <ThreadSidebar
        threads={threads}
        sessionId={sessionId}
        onSelect={selectThread}
        onNew={reset}
        error={threadError}
        onRetry={() => setThreadRefresh((value) => value + 1)}
      />
      <div className="app-content">
        <header className="site-header wrap">
          <Logo />
          <div className="header-note">
            AN EXERCISE IN PERSPECTIVE <span>✳</span>
          </div>
          {sessionId ? (
            session?.status !== "running" && (
              <button className="header-link" onClick={reset}>
                New reflection <span>↗</span>
              </button>
            )
          ) : (
            <a className="header-link" href="#your-question">
              Begin exploring <span>↗</span>
            </a>
          )}
        </header>
        {!sessionId ? (
          <Landing onStart={start} busy={busy} error={error} />
        ) : session?.status === "running" ? (
          <Loading
            session={session}
            error={error}
            onRetry={() => setRefresh((value) => value + 1)}
          />
        ) : session?.status === "clarification" ? (
          <Clarify
            session={session}
            onClarify={clarify}
            busy={busy}
            error={error}
          />
        ) : session?.status === "review" || session?.status === "approved" ? (
          <Exhibit
            session={session}
            onReview={review}
            onFollowUp={followUp}
            onNew={reset}
            busy={busy}
            error={error}
          />
        ) : (
          <main className="work-area wrap">
            <div className="work-heading">
              <span className="section-index">A PAUSE IN THE JOURNEY</span>
              <h1>
                Let’s try
                <br />
                <em>that again.</em>
              </h1>
              <p role="alert">
                {error || session?.error || "Loading your session…"}
              </p>
              <div className="error-actions">
                <button
                  className="primary-button"
                  onClick={() => setRefresh((value) => value + 1)}
                >
                  Retry connection <Arrow />
                </button>
                <button className="text-button" onClick={reset}>
                  Start a new reflection
                </button>
              </div>
            </div>
            {session?.trace?.length > 0 && (
              <TraceInspector trace={session.trace} running />
            )}
          </main>
        )}
        <footer className="site-footer">
          <div className="wrap footer-inner">
            <Logo />
            <p>
              A small space for the questions
              <br />
              without easy answers.
            </p>
            <span>MADE FOR THE IN-BETWEEN ✳</span>
          </div>
        </footer>
      </div>
    </div>
  );
}

export default App;
