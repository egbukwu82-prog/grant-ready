import { useState } from "react";

const EMPTY_ANSWERS = {
  in_alberta: true,
  crop_type: "",
  livestock_type: "",
  acreage: "",
  annual_farm_revenue: "",
  has_efp: false,
  plans: "",
  planned_investment: "",
  certifications: "",
  is_new_or_young_farmer: false,
  is_indigenous: false,
  is_woman: false,
  is_greenhouse_operation: false,
};

const TIER_META = {
  enrollment_deadline: {
    title: "Enrollment deadline — use it or lose it",
    note: "Missing these deadlines costs a full program year with no late option.",
    className: "tier-urgent",
    badge: "Hard deadline",
  },
  rolling: {
    title: "Rolling / cost-share intake",
    note: "Continuous or cyclical intake — missing a cycle means waiting for the next one.",
    className: "tier-rolling",
    badge: "Rolling intake",
  },
  invite_only: {
    title: "Invite-only / large-scale",
    note: "Relationship-driven intake for processor-scale projects.",
    className: "tier-invite",
    badge: "Invite only",
  },
};

function Questionnaire({ answers, setAnswers, onSubmit, loading, error }) {
  const set = (key) => (e) =>
    setAnswers({
      ...answers,
      [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    });

  return (
    <form
      className="questionnaire"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h2>Tell us about your operation</h2>

      <label className="check">
        <input type="checkbox" checked={answers.in_alberta} onChange={set("in_alberta")} />
        My operation is in Alberta
      </label>

      <div className="grid">
        <label>
          Crop type(s)
          <input
            type="text"
            placeholder="e.g. wheat, canola, market vegetables"
            value={answers.crop_type}
            onChange={set("crop_type")}
          />
        </label>
        <label>
          Livestock type(s)
          <input
            type="text"
            placeholder="e.g. cow-calf, hogs — leave blank if none"
            value={answers.livestock_type}
            onChange={set("livestock_type")}
          />
        </label>
        <label>
          Acreage
          <input
            type="number"
            min="0"
            placeholder="e.g. 1500"
            value={answers.acreage}
            onChange={set("acreage")}
          />
        </label>
        <label>
          Annual farm commodity revenue (CAD)
          <input
            type="number"
            min="0"
            placeholder="e.g. 250000"
            value={answers.annual_farm_revenue}
            onChange={set("annual_farm_revenue")}
            required
          />
        </label>
      </div>

      <label className="check">
        <input type="checkbox" checked={answers.has_efp} onChange={set("has_efp")} />
        I have a current Environmental Farm Plan (EFP) certificate
      </label>

      <label>
        What are you planning? (equipment, technology, practices, projects)
        <textarea
          rows="3"
          placeholder="e.g. buy a grain dryer, add solar panels, start rotational grazing, build irrigation"
          value={answers.plans}
          onChange={set("plans")}
        />
      </label>

      <div className="grid">
        <label>
          Estimated project investment (CAD, if known)
          <input
            type="number"
            min="0"
            placeholder="optional"
            value={answers.planned_investment}
            onChange={set("planned_investment")}
          />
        </label>
        <label>
          Certifications
          <input
            type="text"
            placeholder="e.g. organic — leave blank if none"
            value={answers.certifications}
            onChange={set("certifications")}
          />
        </label>
      </div>

      <fieldset>
        <legend>Do any of these apply to you? (used only for targeted programs)</legend>
        <label className="check">
          <input
            type="checkbox"
            checked={answers.is_new_or_young_farmer}
            onChange={set("is_new_or_young_farmer")}
          />
          New farmer or under 40
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={answers.is_indigenous}
            onChange={set("is_indigenous")}
          />
          I identify as Indigenous
        </label>
        <label className="check">
          <input type="checkbox" checked={answers.is_woman} onChange={set("is_woman")} />
          I identify as a woman working in agriculture
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={answers.is_greenhouse_operation}
            onChange={set("is_greenhouse_operation")}
          />
          I run a greenhouse / controlled-environment operation
        </label>
      </fieldset>

      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={loading}>
        {loading ? "Matching…" : "Find my grants"}
      </button>
    </form>
  );
}

function ProgramCard({ match, tierKey }) {
  const [blurb, setBlurb] = useState(match.blurb);
  const meta = TIER_META[tierKey];
  return (
    <article className={`card ${meta.className}`}>
      <header>
        <div>
          <h4>
            {match.name}
            {match.acronym ? ` (${match.acronym})` : ""}
          </h4>
          <p className="agency">
            {match.agency} · <span className="gov-tier">{match.gov_tier}</span>
          </p>
        </div>
        <div className="badges">
          <span className={`badge ${meta.className}`}>{meta.badge}</span>
          {match.flag && <span className="badge badge-flag">⚠ Verify before applying</span>}
        </div>
      </header>

      {match.flag && (
        <div className="flag-box">
          <strong>Verify before applying:</strong> {match.flag}
        </div>
      )}

      <div className="section">
        <h5>Funding</h5>
        <ul>
          {match.funding_plain.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>

      <div className="section">
        <h5>Deadline &amp; intake</h5>
        <p>
          <strong>Deadline:</strong> {match.deadline}
        </p>
        <p>
          <strong>Intake:</strong> {match.intake}
        </p>
      </div>

      <div className="section">
        <h5>Required documents</h5>
        <ul className="docs">
          {match.required_documents.map((doc, i) => (
            <li key={i}>
              <label className="check">
                <input type="checkbox" /> {doc}
              </label>
            </li>
          ))}
        </ul>
      </div>

      <p className="why">{match.why_matched}</p>

      <div className="section">
        <h5>
          Draft application blurb{" "}
          <span className="blurb-source">
            ({match.blurb_source === "llm" ? "AI-drafted" : "template"} — edit freely)
          </span>
        </h5>
        <textarea rows="5" value={blurb} onChange={(e) => setBlurb(e.target.value)} />
      </div>

      <footer>
        <a href={match.source_url} target="_blank" rel="noreferrer">
          Source: {match.source_url}
        </a>
        <span>Last verified: {match.last_verified}</span>
      </footer>
    </article>
  );
}

function Results({ results, onBack }) {
  return (
    <div className="results">
      <div className="results-header">
        <h2>
          {results.total_matched} of {results.total_programs} programs matched your operation
        </h2>
        <button onClick={onBack}>← Edit answers</button>
      </div>
      <p className="dataset-note">
        Program data compiled {results.dataset_compiled}. Programs change frequently — always
        confirm details at the linked official source before applying.
      </p>
      {["enrollment_deadline", "rolling", "invite_only"].map((tierKey) => {
        const matches = results[tierKey];
        if (!matches.length) return null;
        const meta = TIER_META[tierKey];
        return (
          <section key={tierKey} className={`tier ${meta.className}`}>
            <h3>{meta.title}</h3>
            <p className="tier-note">{meta.note}</p>
            {matches.map((m) => (
              <ProgramCard key={m.program_id} match={m} tierKey={tierKey} />
            ))}
          </section>
        );
      })}
      {results.total_matched === 0 && (
        <p className="no-results">
          No programs matched. Check your revenue figure and EFP status — most Alberta
          cost-share programs require $25,000+ in annual farm commodities.
        </p>
      )}
    </div>
  );
}

export default function App() {
  const [answers, setAnswers] = useState(EMPTY_ANSWERS);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        ...answers,
        acreage: Number(answers.acreage) || 0,
        annual_farm_revenue: Number(answers.annual_farm_revenue) || 0,
        planned_investment:
          answers.planned_investment === "" ? null : Number(answers.planned_investment),
      };
      const res = await fetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      setResults(await res.json());
      window.scrollTo(0, 0);
    } catch (e) {
      setError(e.message || "Something went wrong — is the backend running on port 8001?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <header className="app-header">
        <h1>GrantReady</h1>
        <p>Find the Alberta and federal farm programs you actually qualify for.</p>
      </header>
      {results ? (
        <Results results={results} onBack={() => setResults(null)} />
      ) : (
        <Questionnaire
          answers={answers}
          setAnswers={setAnswers}
          onSubmit={submit}
          loading={loading}
          error={error}
        />
      )}
    </main>
  );
}
