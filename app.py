import json
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
import streamlit as st

from hh_parser import get_html, extract_vacancy_data, extract_resume_data
from llm import score_cv  # score_cv(api_key: str, model: str, temperature: float, prompt: str) -> dict


# =========================
# Page config
# =========================
st.set_page_config(page_title="CV Scoring App (Portfolio)", layout="centered")


# =========================
# Helpers
# =========================
def is_valid_url(url: str) -> bool:
    try:
        r = urlparse((url or "").strip())
        return bool(r.scheme and r.netloc)
    except Exception:
        return False


def clamp_text(text: str, limit: int) -> str:
    return (text or "")[:limit]


def format_bullets(items: List[str]) -> str:
    if not items:
        return "—"
    return "\n".join([f"- {x}" for x in items])


def decision_label(fit_score: Any) -> Tuple[str, str]:
    """
    Returns (status, message) where status in {"success","info","warning","error"}.
    """
    try:
        s = float(fit_score)
    except Exception:
        return "info", "Рекомендация: оценка недоступна — проверь корректность ответа модели."

    if s >= 7:
        return "success", "Рекомендация: **Рекомендуется к собеседованию** (высокая вероятность соответствия)."
    if s >= 5:
        return "success", "Рекомендация: **Рекомендуется к собеседованию** (есть потенциал/частичное соответствие)."
    if s >= 3:
        return "warning", "Рекомендация: **Возможен первичный скрининг** (нужно уточняющее интервью по must-have)."
    return "error", "Рекомендация: **Не рекомендуется** (много критичных несоответствий)."


def humanize_requests_error(e: requests.exceptions.RequestException) -> str:
    if isinstance(e, requests.exceptions.HTTPError):
        status = getattr(e.response, "status_code", None)
        if status in (401, 403):
            return "HH.ru вернул 401/403 (возможна защита/ограничение доступа). Попробуй позже или с другой сети."
        if status == 404:
            return "Страница не найдена (404). Проверь ссылки."
        if status == 429:
            return "Слишком много запросов (429). Подожди немного и повтори."
        return f"HTTP ошибка при загрузке страниц (status={status})."
    if isinstance(e, requests.exceptions.Timeout):
        return "Таймаут при загрузке страницы. Попробуй ещё раз."
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Не удалось подключиться к сайту. Проверь интернет/доступность."
    return "Ошибка сети при загрузке страниц."


# =========================
# Cached fetching/parsing
# =========================
@st.cache_data(show_spinner=False, ttl=60 * 30)  # 30 min cache
def fetch_and_parse(job_url: str, resume_url: str, text_limit: int) -> Tuple[str, str]:
    job_html = get_html(job_url)
    resume_html = get_html(resume_url)

    job_text = clamp_text(extract_vacancy_data(job_html), text_limit)
    resume_text = clamp_text(extract_resume_data(resume_html), text_limit)

    return job_text, resume_text


# =========================
# UI
# =========================
st.title("📄 CV Scoring App (Portfolio)")
st.caption("Учебный прототип: HH-парсинг + LLM-скоринг (структурированный вывод и проверка консистентности)")

with st.sidebar:
    st.header("⚙️ Настройки")
    model = st.selectbox("Модель", ["gpt-4o-mini"], index=0)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.0, 0.1)
    text_limit = st.slider("Лимит текста (символы)", 2000, 12000, 7000, 500)

    st.divider()
    show_parsed = st.checkbox("Показывать распарсенный текст", value=False)
    show_debug_json = st.checkbox("Показывать JSON ответа", value=False)
    clear_cache = st.button("🧹 Очистить кэш парсинга")

if clear_cache:
    st.cache_data.clear()
    st.success("Кэш очищен.")

api_key = st.secrets.get("OPENAI_API_KEY", "")
if not api_key:
    st.warning(
        "Не найден `OPENAI_API_KEY` в `.streamlit/secrets.toml`.\n\n"
        "Создай файл `.streamlit/secrets.toml` и добавь:\n"
        '`OPENAI_API_KEY = "sk-..."`'
    )

job_url = st.text_input("🔗 Ссылка на вакансию (HH)", placeholder="https://hh.ru/vacancy/...")
resume_url = st.text_input("🔗 Ссылка на резюме (HH)", placeholder="https://hh.ru/resume/...")

analyze = st.button("🚀 Проанализировать соответствие")

if analyze:
    # ---- Validation
    if not api_key:
        st.error("Нужен API-ключ: добавь OPENAI_API_KEY в `.streamlit/secrets.toml`.")
        st.stop()

    if not job_url or not resume_url:
        st.warning("Заполни обе ссылки.")
        st.stop()

    if not is_valid_url(job_url) or not is_valid_url(resume_url):
        st.error("Некорректный формат URL. Проверь, что ссылки начинаются с http(s)://")
        st.stop()

    # ---- Fetch + parse
    with st.spinner("Скачиваю страницы и парсю данные..."):
        try:
            job_text, resume_text = fetch_and_parse(job_url.strip(), resume_url.strip(), text_limit)
        except requests.exceptions.RequestException as e:
            st.error(humanize_requests_error(e))
            st.caption(str(e))
            st.stop()
        except Exception as e:
            st.error("Ошибка при парсинге страниц.")
            st.exception(e)
            st.stop()

    if show_parsed:
        with st.expander("🔎 Распарсенные данные (для прозрачности)"):
            st.markdown("### Вакансия")
            st.text(job_text)
            st.markdown("### Резюме")
            st.text(resume_text)

    # ---- Prompt
    prompt = f"# ВАКАНСИЯ\n{job_text}\n\n# РЕЗЮМЕ\n{resume_text}".strip()

    # ---- LLM
    with st.spinner("Отправляю запрос в LLM и формирую результат..."):
        try:
            result: Dict[str, Any] = score_cv(api_key=api_key, model=model, temperature=temperature, prompt=prompt)
        except json.JSONDecodeError:
            st.error(
                "LLM вернула невалидный JSON. Попробуй ещё раз (и оставь temperature=0.0)."
            )
            st.stop()
        except Exception as e:
            st.error("Ошибка при запросе к LLM.")
            st.exception(e)
            st.stop()

    # =========================
    # Render
    # =========================
    scores = result.get("scores", {}) if isinstance(result, dict) else {}
    fit_score = scores.get("fit_score", "?")

    st.subheader("📊 Метрики")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fit", f"{scores.get('fit_score', '?')}/10")
    c2.metric("Skills", f"{scores.get('skills_match', '?')}/10")
    c3.metric("Experience", f"{scores.get('experience_relevance', '?')}/10")
    c4.metric("Resume quality", f"{scores.get('resume_quality_score', '?')}/10")

    # ✅ Explicit "recommended to interview" style message
    status, msg = decision_label(fit_score)
    if status == "success":
        st.success(msg)
    elif status == "warning":
        st.warning(msg)
    elif status == "error":
        st.error(msg)
    else:
        st.info(msg)

    # Consistency warning (if model detected contradictions)
    cc = result.get("consistency_check", {})
    if isinstance(cc, dict) and cc.get("contradictions_found") is True:
        st.warning("⚠️ Модель сообщает о возможных противоречиях в выводе.")
        notes = cc.get("notes")
        if notes:
            st.caption(notes)

    # Requirements block (front and center)
    requirements = result.get("requirements", {}) if isinstance(result, dict) else {}
    must_have = requirements.get("must_have", []) if isinstance(requirements, dict) else []
    nice_to_have = requirements.get("nice_to_have", []) if isinstance(requirements, dict) else []

    st.subheader("📌 Требования вакансии")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Must-have**")
        st.write(format_bullets(must_have))
    with col_b:
        st.markdown("**Nice-to-have**")
        st.write(format_bullets(nice_to_have))

    # Summary
    st.subheader("🧾 Вывод")
    st.write(result.get("summary", "—"))

    # Evidence / confirmed skills (fixes the “Python disappeared” perception)
    evidence = result.get("evidence", {}) if isinstance(result, dict) else {}
    if isinstance(evidence, dict):
        languages = evidence.get("languages_mentioned", []) or []
        skills = evidence.get("skills_mentioned", []) or []
        embedded_exp = evidence.get("embedded_experience", "")
        tasks = evidence.get("projects_or_tasks", []) or []

        st.subheader("🔎 Подтверждено в резюме")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Языки/технологии (упомянутые кандидатом)**")
            st.write(format_bullets(languages))
        with col2:
            st.markdown("**Навыки (упомянутые кандидатом)**")
            st.write(format_bullets(skills))

        if embedded_exp:
            st.markdown("**Embedded / низкоуровневый опыт**")
            st.write(embedded_exp)

        if tasks:
            st.markdown("**Примеры задач/проектов (из резюме)**")
            st.write(format_bullets(tasks))

    # Strengths / Risks / Gaps / Recommendations
    st.subheader("✅ Сильные стороны")
    st.write(format_bullets(result.get("pros", [])))

    st.subheader("⚠️ Риски / слабые стороны")
    st.write(format_bullets(result.get("cons", [])))

    st.subheader("❌ Несоответствие требованиям вакансии")
    st.write(format_bullets(result.get("gaps", [])))
    if must_have and result.get("gaps"):
        st.caption("Подсказка: несоответствие must-have требованиям — главный фактор снижения Fit score.")

    st.subheader("🛠 Рекомендации")
    st.write(format_bullets(result.get("recommendations", [])))

    # Interpretation as a reference (not a verdict banner)
    with st.expander("ℹ️ Как интерпретировать Fit score"):
        st.markdown(
            """
**Fit score — ориентир, а не автоматический вердикт.**

- **7–10** — высокая вероятность соответствия  
- **5–6** — **рекомендуется к собеседованию** при наличии релевантных задач  
- **3–4** — возможен первичный скрининг / уточняющее интервью по must-have  
- **0–2** — маловероятное соответствие

Решение всегда остаётся за рекрутёром.
"""
        )

    if show_debug_json:
        with st.expander("🧩 JSON ответа модели (debug)"):
            st.json(result)
