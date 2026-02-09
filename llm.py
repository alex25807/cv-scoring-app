import json
from openai import OpenAI

SYSTEM_PROMPT = """
Ты — HR-ассистент. Оцени соответствие резюме вакансии.

Верни ответ СТРОГО в JSON (без markdown) по схеме:

{
  "evidence": {
    "skills_mentioned": ["..."], 
    "languages_mentioned": ["..."],
    "embedded_experience": "есть/нет + 1-2 факта из текста",
    "projects_or_tasks": ["1-3 конкретных задач/проектов из резюме"]
  },
  "requirements": {
    "must_have": ["..."],
    "nice_to_have": ["..."]
  },
  "gaps": [
    "чего не хватает или что не подтверждено (формулируй строго)"
  ],
  "scores": {
    "fit_score": 1-10,
    "skills_match": 1-10,
    "experience_relevance": 1-10,
    "resume_quality_score": 1-10
  },
  "summary": "краткий вывод 3-6 предложений",
  "pros": [
    "сильные стороны — ТОЛЬКО те, что подтверждены evidence"
  ],
  "cons": [
    "слабые стороны — ТОЛЬКО те, что следуют из gaps/requirements"
  ],
  "recommendations": [
    "что улучшить/дописать в резюме и чему доучиться под вакансию"
  ],
  "consistency_check": {
    "contradictions_found": false,
    "notes": "если contradictions_found=true, кратко опиши противоречия"
  }
}

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА КОНСИСТЕНТНОСТИ:
1) Нельзя писать в pros то, что указано в gaps.
2) Если навык/язык упомянут в резюме, но уровень/глубина не соответствует вакансии — это НЕ 'отсутствует', а 'есть, но недостаточно под требования'.
3) Все пункты pros/cons должны опираться на evidence/requirements/gaps.
4) В конце выполни самопроверку и заполни consistency_check.
""".strip()


def score_cv(api_key: str, model: str, temperature: float, prompt: str) -> dict:
    client = OpenAI(api_key=api_key)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=1200,
    )

    content = resp.choices[0].message.content.strip()

    # Попытка распарсить JSON (LLM иногда добавляет мусор)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # "спасалка": вытащить JSON-объект по первой/последней скобке
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start:end+1])
        raise
