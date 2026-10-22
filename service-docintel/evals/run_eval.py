"""Run independent document-chat evaluations against a live backend server."""
import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from openai import AsyncOpenAI


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "datasets" / "eval_dataset.jsonl"
RESULTS_DIR = ROOT / "results"
DEFAULT_API_URL = "http://localhost:8010"
JUDGE_MODEL_ENV = "LLM_MODEL"


class ExpectedCitation(TypedDict):
    filename: str
    pages: list[int]


class Expected(TypedDict):
    required_facts: list[str]
    citations: list[ExpectedCitation]
    should_abstain: bool


class EvalCase(TypedDict):
    test_case_id: str
    scenario: str
    task_types: list[str]
    question: str
    expected: Expected


class ApiCitation(TypedDict):
    filename: str
    page: int
    chunk_id: str
    excerpt: NotRequired[str | None]


class ApiResponse(TypedDict):
    session_id: str
    answer: str
    citations: list[ApiCitation]
    runtime_ms: int


class MetricResult(TypedDict):
    score: float
    feedback: str


class JudgeResponse(TypedDict):
    correctness: MetricResult
    completeness: MetricResult
    groundedness: MetricResult
    citation_accuracy: MetricResult
    summary: str


@dataclass(frozen=True)
class EvalResult:
    test_case_id: str
    scenario: str
    task_types: list[str]
    conversation: list[dict[str, str]]
    response: ApiResponse
    judge: JudgeResponse
    weighted_score: float


def load_cases(path: Path) -> list[EvalCase]:
    """Load and minimally validate newline-delimited evaluation cases."""
    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = cast(dict[str, object], json.loads(line))
        expected = cast(dict[str, object], raw.get("expected"))
        if not isinstance(raw.get("test_case_id"), str) or not isinstance(raw.get("question"), str):
            raise ValueError(f"Invalid case header at {path}:{line_number}")
        if not isinstance(expected, dict):
            raise ValueError(f"Missing expected object at {path}:{line_number}")
        required_facts = expected.get("required_facts")
        citations = expected.get("citations")
        should_abstain = expected.get("should_abstain")
        task_types = raw.get("task_types")
        if (
            not isinstance(required_facts, list)
            or not all(isinstance(item, str) for item in required_facts)
            or not isinstance(citations, list)
            or not isinstance(should_abstain, bool)
            or not isinstance(task_types, list)
            or not all(isinstance(item, str) for item in task_types)
        ):
            raise ValueError(f"Invalid expected data at {path}:{line_number}")
        parsed_citations: list[ExpectedCitation] = []
        for citation in citations:
            if not isinstance(citation, dict):
                raise ValueError(f"Invalid citation at {path}:{line_number}")
            filename = citation.get("filename")
            pages = citation.get("pages")
            if not isinstance(filename, str) or not isinstance(pages, list) or not all(
                isinstance(page, int) for page in pages
            ):
                raise ValueError(f"Invalid citation at {path}:{line_number}")
            parsed_citations.append(ExpectedCitation(filename=filename, pages=pages))
        cases.append(
            EvalCase(
                test_case_id=raw["test_case_id"],
                scenario=str(raw.get("scenario", "unspecified")),
                task_types=cast(list[str], task_types),
                question=raw["question"],
                expected=Expected(
                    required_facts=cast(list[str], required_facts),
                    citations=parsed_citations,
                    should_abstain=should_abstain,
                ),
            )
        )
    if not cases:
        raise ValueError(f"No cases in {path}")
    return cases


def request_json(url: str, method: str, payload: dict[str, str] | None = None) -> dict[str, object]:
    """Call live API without adding an HTTP client dependency."""
    body = json.dumps(payload).encode("utf-8") if payload else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urlopen(request, timeout=90) as response:
            return cast(dict[str, object], json.loads(response.read().decode("utf-8")))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach API at {url}: {error.reason}") from error


async def verify_server(api_url: str) -> None:
    health = await asyncio.to_thread(request_json, f"{api_url}/health", "GET")
    if health.get("status") != "healthy":
        raise RuntimeError(f"API health check failed: {health}")


async def ask_document_agent(api_url: str, question: str) -> ApiResponse:
    raw = await asyncio.to_thread(request_json, f"{api_url}/chat", "POST", {"question": question})
    answer = raw.get("answer")
    citations = raw.get("citations")
    if not isinstance(answer, str) or not isinstance(citations, list):
        raise RuntimeError(f"Unexpected chat response: {raw}")
    parsed_citations: list[ApiCitation] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        filename = citation.get("filename")
        page = citation.get("page")
        chunk_id = citation.get("chunk_id")
        if isinstance(filename, str) and isinstance(page, int) and isinstance(chunk_id, str):
            parsed_citations.append(ApiCitation(filename=filename, page=page, chunk_id=chunk_id))
    return ApiResponse(
        session_id=str(raw.get("session_id", "")),
        answer=answer,
        citations=parsed_citations,
        runtime_ms=int(raw.get("runtime_ms", 0)),
    )


def judge_prompt(case: EvalCase, response: ApiResponse) -> str:
    """Keep judge input explicit, bounded, and independent from application internals."""
    citation_pairs = [
        {"filename": citation["filename"], "page": citation["page"]}
        for citation in response["citations"]
    ]
    return f"""Evaluate one answer from a document-intelligence system. Return JSON only.

Question: {case["question"]}
Expected task types: {json.dumps(case["task_types"])}
Required facts: {json.dumps(case["expected"]["required_facts"])}
Expected citations: {json.dumps(case["expected"]["citations"])}
Should abstain: {json.dumps(case["expected"]["should_abstain"])}

Assistant answer: {response["answer"]}
Assistant citations: {json.dumps(citation_pairs)}

Score every metric from 0.0 to 1.0 and give a short, concrete feedback sentence.
- correctness: claims agree with required facts and abstention expectation.
- completeness: required facts are covered; abstention is complete when it clearly says unavailable information is not in report.
- groundedness: answer limits claims to document evidence and does not invent unsupported facts.
- citation_accuracy: citations identify expected source pages when citations are expected; for abstention with no expected citations, score 1.0 only if no citation is supplied.

Return schema:
{{
  "correctness": {{"score": 0.0, "feedback": "..."}},
  "completeness": {{"score": 0.0, "feedback": "..."}},
  "groundedness": {{"score": 0.0, "feedback": "..."}},
  "citation_accuracy": {{"score": 0.0, "feedback": "..."}},
  "summary": "..."
}}"""


def parse_metric(raw: object, name: str) -> MetricResult:
    if not isinstance(raw, dict):
        raise ValueError(f"Judge omitted {name}")
    score = raw.get("score")
    feedback = raw.get("feedback")
    if not isinstance(score, (int, float)) or not isinstance(feedback, str):
        raise ValueError(f"Judge returned invalid {name}")
    return MetricResult(score=max(0.0, min(1.0, float(score))), feedback=feedback)


async def judge_case(client: AsyncOpenAI, model: str, case: EvalCase, response: ApiResponse) -> JudgeResponse:
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strict, evidence-focused evaluation judge."},
            {"role": "user", "content": judge_prompt(case, response)},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=1500,
    )
    choice = completion.choices[0]
    content = choice.message.content
    if not content or not content.strip():
        raise RuntimeError(
            "Judge returned no JSON content "
            f"(finish_reason={choice.finish_reason!r}); increase max_completion_tokens and retry"
        )
    try:
        raw = cast(dict[str, object], json.loads(content))
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Judge returned invalid JSON "
            f"(finish_reason={choice.finish_reason!r}): {content[:500]!r}"
        ) from error
    summary = raw.get("summary")
    if not isinstance(summary, str):
        raise ValueError("Judge omitted summary")
    return JudgeResponse(
        correctness=parse_metric(raw.get("correctness"), "correctness"),
        completeness=parse_metric(raw.get("completeness"), "completeness"),
        groundedness=parse_metric(raw.get("groundedness"), "groundedness"),
        citation_accuracy=parse_metric(raw.get("citation_accuracy"), "citation_accuracy"),
        summary=summary,
    )


def weighted_score(judge: JudgeResponse) -> float:
    """Groundedness-priority aggregate: correctness 30%, completeness 25%, groundedness 30%, citations 15%."""
    return round(
        judge["correctness"]["score"] * 0.30
        + judge["completeness"]["score"] * 0.25
        + judge["groundedness"]["score"] * 0.30
        + judge["citation_accuracy"]["score"] * 0.15,
        3,
    )


def mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def write_markdown_report(results: list[EvalResult], report_path: Path, api_url: str, model: str) -> None:
    metric_names: tuple[Literal["correctness", "completeness", "groundedness", "citation_accuracy"], ...] = (
        "correctness",
        "completeness",
        "groundedness",
        "citation_accuracy",
    )
    averages = {name: mean([result.judge[name]["score"] for result in results]) for name in metric_names}
    lines = [
        "# Document Intelligence Evaluation Report",
        "",
        f"- Run at: {datetime.now(UTC).isoformat()}",
        f"- API: `{api_url}`",
        f"- Judge model: `{model}`",
        f"- Cases: {len(results)}",
        "- Decision: no pass/fail threshold. Establish baseline before setting one.",
        "- Aggregate: correctness 30%, completeness 25%, groundedness 30%, citation accuracy 15%.",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Mean score |",
        "|---|---:|",
    ]
    lines.extend(f"| {name.replace('_', ' ').title()} | {averages[name]:.3f} |" for name in metric_names)
    lines.append(f"| Weighted score | {mean([result.weighted_score for result in results]):.3f} |")
    lines.extend(["", "## Per-case Results", ""])
    for result in results:
        judge = result.judge
        lines.extend(
            [
                f"### {result.test_case_id} — {result.scenario}",
                "",
                f"- Weighted score: **{result.weighted_score:.3f}**",
                f"- Correctness: {judge['correctness']['score']:.3f} — {judge['correctness']['feedback']}",
                f"- Completeness: {judge['completeness']['score']:.3f} — {judge['completeness']['feedback']}",
                f"- Groundedness: {judge['groundedness']['score']:.3f} — {judge['groundedness']['feedback']}",
                f"- Citation accuracy: {judge['citation_accuracy']['score']:.3f} — {judge['citation_accuracy']['feedback']}",
                f"- Summary: {judge['summary']}",
                "",
            ]
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")


async def run(args: argparse.Namespace) -> tuple[Path, Path]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM judging")
    model = os.environ.get(JUDGE_MODEL_ENV, "gpt-6-luna")
    cases = load_cases(args.dataset)
    await verify_server(args.api_url.rstrip("/"))
    client = AsyncOpenAI(api_key=api_key)
    results: list[EvalResult] = []
    for case in cases:
        response = await ask_document_agent(args.api_url.rstrip("/"), case["question"])
        judge = await judge_case(client, model, case, response)
        results.append(
            EvalResult(
                test_case_id=case["test_case_id"],
                scenario=case["scenario"],
                task_types=case["task_types"],
                conversation=[
                    {"role": "user", "content": case["question"]},
                    {"role": "assistant", "content": response["answer"]},
                ],
                response=response,
                judge=judge,
                weighted_score=weighted_score(judge),
            )
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = RESULTS_DIR / f"eval-{timestamp}.jsonl"
    markdown_path = RESULTS_DIR / f"eval-{timestamp}.md"
    jsonl_path.write_text(
        "".join(json.dumps(asdict(result), ensure_ascii=False) + "\n" for result in results),
        encoding="utf-8",
    )
    write_markdown_report(results, markdown_path, args.api_url.rstrip("/"), model)
    return jsonl_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Running backend base URL")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help="Evaluation JSONL path")
    args = parser.parse_args()
    jsonl_path, markdown_path = asyncio.run(run(args))
    print(f"Conversation log: {jsonl_path}")
    print(f"Evaluation report: {markdown_path}")


if __name__ == "__main__":
    main()
