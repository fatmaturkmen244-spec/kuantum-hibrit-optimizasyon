from __future__ import annotations

import os

from openai import AzureOpenAI
from dotenv import load_dotenv

from .models import RouteResult


load_dotenv()


def _local_explanation(results: list[RouteResult]) -> str:
    ranked = sorted(results, key=lambda item: item.distance)
    best = ranked[0]
    comparison = ", ".join(f"{item.solver.value}: {item.distance:.2f}" for item in ranked)
    return (
        f"En düşük maliyetli rota {best.solver.value} yöntemiyle {best.distance:.2f} "
        f"{best.cost_unit} bulundu. "
        f"Karşılaştırma — {comparison}."
    )


def explain_results(results: list[RouteResult]) -> str:
    """Use Azure OpenAI when configured; otherwise return a deterministic summary."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not all((endpoint, api_key, deployment)):
        return _local_explanation(results)

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    compact = [result.model_dump() for result in results]
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "system",
                "content": (
                    "Sen bir optimizasyon analistisin. Sonuçları Türkçe, en fazla üç kısa "
                    "cümlede açıkla. Kuantum üstünlüğü iddia etme; mesafe ve süreleri karşılaştır."
                ),
            },
            {"role": "user", "content": str(compact)},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or _local_explanation(results)
