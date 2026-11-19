import { useEffect, useState } from "react";

export default function App() {
  const [question, setQuestion] = useState("");
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");

  async function start(event) {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dilemma: question }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(data.detail));
      setSession({ id: data.id, status: "running" });
    } catch (problem) {
      setError(problem.message);
    }
  }

  useEffect(() => {
    if (!session?.id || session.status !== "running") return undefined;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/sessions/${session.id}`);
        const data = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(data.detail));
        if (active) setSession(data);
      } catch (problem) {
        if (active) setError(problem.message);
      }
    }, 2500);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [session]);

  return (
    <main>
      <h1>The Unchosen Life</h1>
      <form onSubmit={start}>
        <label htmlFor="question">Your question</label>
        <input
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          required
        />
        <button disabled={session?.status === "running"}>Explore</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {session && (
        <p>
          Status: {session.status} {session.stage}
        </p>
      )}
      {session?.error && <p role="alert">{session.error}</p>}
      {session?.exhibit && <pre>{session.exhibit}</pre>}
    </main>
  );
}
