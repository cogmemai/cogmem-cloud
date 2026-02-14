"""Workbench API routes — experiment management and execution."""

import csv
import io
import json
import sys

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

csv.field_size_limit(sys.maxsize)

router = APIRouter(prefix="/workbench", tags=["workbench"])

# Lazy singleton — initialized on first use
_runner = None


def _get_runner():
    """Get or create the ExperimentRunner singleton."""
    global _runner
    if _runner is None:
        from kos.cloud.app import _get_registry
        from kos.cloud.workbench.experiment_runner import ExperimentRunner

        reg = _get_registry()
        _runner = ExperimentRunner(
            object_store=reg.object_store,
            text_search=reg.text_search,
            vector_search=reg.vector_search,
            strategy_store=reg.strategy_store,
            outcome_store=reg.outcome_store,
            proposal_store=reg.proposal_store,
        )
    return _runner


@router.get("/experiments")
async def list_experiments():
    """List all experiments."""
    runner = _get_runner()
    return [exp.model_dump(mode="json") for exp in runner.list_experiments()]


@router.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str):
    """Get a single experiment with all cycle results."""
    runner = _get_runner()
    exp = runner.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp.model_dump(mode="json")


@router.post("/experiments")
async def create_experiment(
    file: UploadFile = File(...),
    name: str = Form("Untitled Experiment"),
    max_cycles: int = Form(3),
    test_queries: str = Form(""),
):
    """Create a new experiment from an uploaded CSV file.

    Profiles the data and derives an initial strategy.
    Does NOT start ingestion — call POST /workbench/experiments/{id}/run next.

    Args:
        file: CSV file to upload.
        name: Experiment name.
        max_cycles: Maximum evaluation cycles (1-20).
        test_queries: Comma-separated test queries. Auto-generated if empty.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    csv_content = content.decode("utf-8")

    queries = [q.strip() for q in test_queries.split(",") if q.strip()] if test_queries else None

    runner = _get_runner()
    experiment = await runner.create_experiment(
        name=name,
        csv_content=csv_content,
        test_queries=queries,
        max_cycles=max_cycles,
    )
    return experiment.model_dump(mode="json")


@router.post("/experiments/{experiment_id}/run")
async def run_next_cycle(experiment_id: str):
    """Run the next evaluation cycle for an experiment.

    Each call advances the experiment by one cycle:
    ingest → test → evaluate → (propose strategy change) → done.
    """
    runner = _get_runner()
    exp = runner.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    try:
        cycle = await runner.run_next_cycle(experiment_id)
        return {
            "cycle": cycle.model_dump(mode="json"),
            "experiment": runner.get_experiment(experiment_id).model_dump(mode="json"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/{experiment_id}/run-all")
async def run_all_cycles(experiment_id: str):
    """Run all remaining cycles for an experiment.

    Convenience endpoint that calls run_next_cycle repeatedly until
    max_cycles is reached or the experiment fails.
    """
    runner = _get_runner()
    exp = runner.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    cycles_run = 0
    try:
        remaining = exp.max_cycles - len(exp.cycles)
        for _ in range(remaining):
            await runner.run_next_cycle(experiment_id)
            cycles_run += 1
    except ValueError:
        pass  # Max cycles reached
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed after {cycles_run} cycles: {str(e)}",
        )

    return runner.get_experiment(experiment_id).model_dump(mode="json")


class GenerateQueriesRequest(BaseModel):
    """Request body for AI query generation."""
    csv_sample: str
    num_queries: int = 8


@router.post("/generate-queries")
async def generate_test_queries(req: GenerateQueriesRequest):
    """Use OpenAI to generate test queries from a sample of CSV data.

    Sends a few sample rows to the LLM and asks it to propose realistic
    search queries a user might ask about this data.
    """
    from kos.cloud.config import get_cloud_settings

    settings = get_cloud_settings()

    # Parse CSV sample to extract column names and a few rows
    reader = csv.DictReader(io.StringIO(req.csv_sample))
    columns = reader.fieldnames or []
    sample_rows = []
    for i, row in enumerate(reader):
        if i >= 5:
            break
        sample_rows.append(dict(row))

    if not sample_rows:
        raise HTTPException(status_code=400, detail="CSV sample is empty")

    # Build a concise data summary for the prompt
    data_summary = f"Columns: {', '.join(columns)}\n\nSample rows:\n"
    for i, row in enumerate(sample_rows):
        # Truncate long values
        truncated = {k: (v[:200] + "..." if len(v) > 200 else v) for k, v in row.items()}
        data_summary += f"Row {i+1}: {truncated}\n"

    prompt = f"""You are analyzing a dataset to generate test search queries for a knowledge retrieval system.

Here is a sample of the data:

{data_summary}

Generate exactly {req.num_queries} diverse, realistic search queries that a user might ask when searching this data. The queries should:
1. Cover different columns and aspects of the data
2. Include both specific lookups and broader topical queries
3. Use natural language (how a real user would search)
4. Vary in complexity (simple keyword, phrase, question)

Return ONLY a JSON array of strings, no other text. Example:
["query one", "query two", "query three"]"""

    try:
        import os
        import openai
        from dotenv import load_dotenv

        load_dotenv()  # Ensure .env vars are in os.environ
        api_key = settings.litellm_api_key or os.environ.get("OPENAI_API_KEY") or None
        base_url = settings.litellm_api_base or None

        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="No API key configured. Set OPENAI_API_KEY or LITELLM_API_KEY in backend/.env",
            )

        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        response = client.chat.completions.create(
            model=settings.litellm_default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        content = response.choices[0].message.content or "[]"
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        queries = json.loads(content)
        if not isinstance(queries, list):
            raise ValueError("Expected a JSON array")
        return {"queries": [str(q) for q in queries]}

    except ImportError:
        raise HTTPException(status_code=500, detail="openai package not installed")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM returned invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query generation failed: {str(e)}")
