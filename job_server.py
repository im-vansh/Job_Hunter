import os
import re
from urllib.parse import urlencode
from pypdf import PdfReader
from fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup

# Initialize the MCP Server
mcp = FastMCP("LinkedIn-Job-Hunter")

# LinkedIn URL filter mappings
TIME_MAP = {
    "24h": "r86400",   # Past 24 hours
    "48h": "r172800",  # Past 48 hours
    "1w": "r604800"    # Past 1 week
}

EXP_MAP = {
    "intern": "1",     # Internship
    "entry": "2",      # Entry Level (0-1 yr: SDE-1, ASE, ASDE)
    "associate": "3"   # Associate / Experienced (1-3 yrs)
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


@mcp.tool()
def read_resume(file_path: str = "resume.pdf") -> str:
    """
    Reads the user's resume PDF file from disk and returns the extracted text
    so the agent can analyze tech stack, experience, projects, and education.
    Defaults to 'resume.pdf' in the project root directory.
    """
    clean_path = file_path.strip().strip('"').strip("'")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = clean_path if os.path.isabs(clean_path) else os.path.join(base_dir, clean_path)

    if not os.path.exists(full_path):
        return (
            f"Error: Resume file not found at '{full_path}'. "
            "Please place 'resume.pdf' in the project folder, provide the full file path, "
            "or attach/paste your resume directly in the chat."
        )

    try:
        reader = PdfReader(full_path)
        extracted_pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                extracted_pages.append(f"--- Page {i + 1} ---\n{text.strip()}")

        full_text = "\n\n".join(extracted_pages)
        if not full_text.strip():
            return "Error: Could not extract readable text from the PDF (it might be a scanned image)."

        return full_text

    except Exception as e:
        return f"Error reading resume PDF: {str(e)}"


@mcp.tool()
async def search_linkedin_jobs(
    roles: list[str],
    location: str = "India",
    time_window: str = "24h",
    experience: str = "entry",
    limit: int = 10
) -> list[dict]:
    """
    Fetches LinkedIn job openings based on role titles (e.g., ["SDE 1", "ASE"]),
    location (default "India"), time_window ("24h", "48h", "1w"),
    and experience level ("intern" for Internship, "entry" for 0-1 yr Fresher, "associate" for 1-3 yrs).
    """
    keyword_query = " OR ".join([f'"{role}"' for role in roles])

    params = {
        "keywords": keyword_query,
        "location": location if location.strip() else "India",
        "f_TPR": TIME_MAP.get(time_window.lower(), "r86400"),
        "f_E": EXP_MAP.get(experience.lower(), "2"),
        "start": 0
    }

    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params)}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=HEADERS, timeout=15.0)

    if response.status_code != 200:
        return [{"error": f"LinkedIn returned status code {response.status_code}"}]

    soup = BeautifulSoup(response.text, "html.parser")
    job_cards = soup.find_all("li")

    jobs = []
    for card in job_cards[:limit]:
        title_tag = card.find("h3", class_="base-search-card__title")
        company_tag = card.find("h4", class_="base-search-card__subtitle")
        loc_tag = card.find("span", class_="job-search-card__location")
        link_tag = card.find("a", class_="base-card__full-link")
        time_tag = card.find("time")
        entity_div = card.find("div", class_="base-card")

        if title_tag and link_tag:
            clean_link = link_tag["href"].split("?")[0]

            # Extract numeric LinkedIn job_id for get_job_details
            job_id = None
            if entity_div and entity_div.get("data-entity-urn"):
                job_id = entity_div["data-entity-urn"].split(":")[-1]
            else:
                match = re.search(r"-(\d+)$", clean_link)
                if match:
                    job_id = match.group(1)

            jobs.append({
                "job_id": job_id or "N/A",
                "title": title_tag.get_text(strip=True),
                "company": company_tag.get_text(strip=True) if company_tag else "N/A",
                "location": loc_tag.get_text(strip=True) if loc_tag else location,
                "posted": time_tag.get_text(strip=True) if time_tag else "Recently",
                "apply_link": clean_link
            })

    return jobs if jobs else [{"message": "No jobs found matching these exact filters."}]


@mcp.tool()
async def get_job_details(job_id: str) -> dict:
    """
    Fetches the full job description and criteria for a specific LinkedIn job_id
    so the agent can verify exact years of experience required and tech stack match.
    """
    clean_id = re.sub(r"\D", "", str(job_id))
    if not clean_id:
        return {"error": f"Invalid job_id: {job_id}"}

    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{clean_id}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=HEADERS, timeout=15.0)

    if response.status_code != 200:
        return {"error": f"Could not fetch details for job {clean_id} (HTTP {response.status_code})"}

    soup = BeautifulSoup(response.text, "html.parser")
    desc_div = soup.find("div", class_="show-more-less-html__markup")
    description = desc_div.get_text(separator="\n", strip=True) if desc_div else "Description unavailable."

    return {
        "job_id": clean_id,
        "description": description[:4000]
    }


if __name__ == "__main__":
    mcp.run(show_banner=False)