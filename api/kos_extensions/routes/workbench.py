"""Workbench API routes — experiment management and execution.

All routes are tenant-scoped — each user's experiments are isolated.
"""

import csv
import io
import json
import sys

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.config import settings as app_settings
from kos_extensions.tenant_deps import get_tenant_registry, TenantRegistry

csv.field_size_limit(sys.maxsize)

router = APIRouter(prefix="/workbench", tags=["workbench"])


def _make_runner(reg: TenantRegistry):
    """Create an ExperimentRunner wired to the tenant's providers (lazy import)."""
    from kos_extensions.workbench.experiment_runner import ExperimentRunner

    return ExperimentRunner(
        object_store=reg.object_store,
        text_search=reg.text_search,
        vector_search=reg.vector_search,
        strategy_store=reg.strategy_store,
        outcome_store=reg.outcome_store,
        proposal_store=reg.proposal_store,
    )


@router.get("/experiments")
async def list_experiments(reg: TenantRegistry = Depends(get_tenant_registry)):
    """List all experiments."""
    runner = _make_runner(reg)
    return [exp.model_dump(mode="json") for exp in runner.list_experiments()]


@router.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Get a single experiment with all cycle results."""
    runner = _make_runner(reg)
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
    reg: TenantRegistry = Depends(get_tenant_registry),
):
    """Create a new experiment from an uploaded CSV file."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    csv_content = content.decode("utf-8")

    queries = [q.strip() for q in test_queries.split(",") if q.strip()] if test_queries else None

    runner = _make_runner(reg)
    experiment = await runner.create_experiment(
        name=name,
        csv_content=csv_content,
        test_queries=queries,
        max_cycles=max_cycles,
    )
    return experiment.model_dump(mode="json")


@router.post("/experiments/{experiment_id}/run")
async def run_next_cycle(experiment_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Run the next evaluation cycle for an experiment."""
    runner = _make_runner(reg)
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
async def run_all_cycles(experiment_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Run all remaining cycles for an experiment."""
    runner = _make_runner(reg)
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
        pass
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
async def generate_test_queries(
    req: GenerateQueriesRequest,
    current_user: CurrentUser,
):
    """Use OpenRouter to generate test queries from a sample of CSV data."""
    reader = csv.DictReader(io.StringIO(req.csv_sample))
    columns = reader.fieldnames or []
    sample_rows = []
    for i, row in enumerate(reader):
        if i >= 5:
            break
        sample_rows.append(dict(row))

    if not sample_rows:
        raise HTTPException(status_code=400, detail="CSV sample is empty")

    data_summary = f"Columns: {', '.join(columns)}\n\nSample rows:\n"
    for i, row in enumerate(sample_rows):
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
        import openai as openai_lib

        if not app_settings.OPENROUTER_API_KEY:
            raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")

        client = openai_lib.OpenAI(
            api_key=app_settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        content = response.choices[0].message.content or "[]"
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

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM returned invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query generation failed: {str(e)}")
