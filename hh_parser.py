import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text

def extract_vacancy_data(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    def safe(selector, attrs=None, default="Не найдено"):
        el = soup.find(selector, attrs or {})
        return el.get_text(" ", strip=True) if el else default

    title = safe("h1")
    salary = safe("span", {"data-qa": "vacancy-salary"})
    company = safe("a", {"data-qa": "vacancy-company-name"})
    desc = soup.find("div", {"data-qa": "vacancy-description"})
    desc_text = desc.get_text("\n", strip=True) if desc else "Описание не найдено"

    return f"# {title}\n\nКомпания: {company}\nЗарплата: {salary}\n\nОписание:\n{desc_text}".strip()

def extract_resume_data(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    def safe(selector, attrs=None, default="Не найдено"):
        el = soup.find(selector, attrs or {})
        return el.get_text(" ", strip=True) if el else default

    name = safe("h2", {"data-qa": "bloko-header-1"})
    location = safe("span", {"data-qa": "resume-personal-address"})
    job_title = safe("span", {"data-qa": "resume-block-title-position"})
    job_status = safe("span", {"data-qa": "job-search-status"})

    # опыт
    experiences = []
    section = soup.find("div", {"data-qa": "resume-block-experience"})
    if section:
        items = section.find_all("div", class_="resume-block-item-gap")
        for item in items:
            position = item.find("div", {"data-qa": "resume-block-experience-position"})
            descr = item.find("div", {"data-qa": "resume-block-experience-description"})
            company = item.find("div", class_="bloko-text_strong")
            if position and company:
                experiences.append(
                    f"- {position.get_text(' ', strip=True)} — {company.get_text(' ', strip=True)}\n"
                    f"  {descr.get_text(' ', strip=True) if descr else ''}"
                )

    # навыки
    skills = []
    skills_section = soup.find("div", {"data-qa": "skills-table"})
    if skills_section:
        skills = [t.get_text(" ", strip=True) for t in skills_section.find_all("span", {"data-qa": "bloko-tag__text"})]

    exp_text = "\n".join(experiences) if experiences else "Опыт работы не найден."
    skills_text = ", ".join(skills) if skills else "Навыки не указаны."

    return (
        f"# {name}\n\n"
        f"Местоположение: {location}\n"
        f"Желаемая должность: {job_title}\n"
        f"Статус: {job_status}\n\n"
        f"Опыт:\n{exp_text}\n\n"
        f"Навыки:\n{skills_text}"
    ).strip()
