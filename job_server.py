from fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlencode

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
    "associate": "3"   # Associate (1-3 yrs)
}

@mcp.tool()
async def search_linkedin_jobs(
    roles: list[str],
    location: str = "India",
    time_window: str = "24h",
    experience: str = "entry",
    limit: int = 15
) -> list[dict]:
    """
    Fetches LinkedIn job openings based on role titles, location, time_window (24h, 48h, 1w),
    and experience level (intern, entry, associate).
    """
    # Formats roles into: "SDE" OR "SDE 1" OR "ASE"
    keyword_query = " OR ".join([f'"{role}"' for role in roles])
    
    params = {
        "keywords": keyword_query,
        "location": location,
        "f_TPR": TIME_MAP.get(time_window.lower(), "r86400"),
        "f_E": EXP_MAP.get(experience.lower(), "2"),
        "start": 0
    }
    
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=15.0)
        
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

        if title_tag and link_tag:
            jobs.append({
                "title": title_tag.get_text(strip=True),
                "company": company_tag.get_text(strip=True) if company_tag else "N/A",
                "location": loc_tag.get_text(strip=True) if loc_tag else location,
                "posted": time_tag.get_text(strip=True) if time_tag else "Recently",
                "apply_link": link_tag["href"].split("?")[0]
            })
            
    return jobs if jobs else [{"message": "No jobs found matching these exact filters."}]

if __name__ == "__main__":
    mcp.run(show_banner=False)