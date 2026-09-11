"""Static knowledge used for dropdowns, normalization and deterministic checks.

Keep this file data-only so it can be reviewed and extended without touching
agent logic. Lists that depend on law or market conventions (pay-transparency
states, sponsorship phrasing) should be re-checked periodically.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Dropdown options
# --------------------------------------------------------------------------- #
ROLE_FAMILIES: dict[str, list[str]] = {
    "Software Engineering": ["Software Engineer", "Software Developer", "SWE"],
    "Backend": ["Backend Engineer", "Back End Developer", "Server Engineer"],
    "Frontend": ["Frontend Engineer", "Front End Developer", "UI Engineer"],
    "Full Stack": ["Full Stack Engineer", "Full-Stack Developer"],
    "Machine Learning / AI": [
        "Machine Learning Engineer", "ML Engineer", "AI Engineer",
        "Applied Scientist", "LLM Engineer", "Applied AI Engineer",
    ],
    "Data Science": ["Data Scientist", "Applied Data Scientist", "Decision Scientist"],
    "Data Engineering": ["Data Engineer", "Analytics Engineer", "Big Data Engineer"],
    "Data Analytics": ["Data Analyst", "Business Intelligence Analyst", "Product Analyst"],
    "Research": ["Research Scientist", "Research Engineer", "AI Research Scientist"],
    "DevOps / SRE / Cloud": [
        "DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer", "Platform Engineer",
    ],
    "Security": ["Security Engineer", "Application Security Engineer", "Security Analyst"],
    "Mobile": ["iOS Engineer", "Android Engineer", "Mobile Engineer"],
    "Embedded / Hardware": ["Embedded Software Engineer", "Firmware Engineer"],
    "Product Management": ["Product Manager", "Technical Product Manager"],
    "QA / Test": ["QA Engineer", "Software Development Engineer in Test", "Test Engineer"],
}

INDUSTRIES = [
    "AI / ML", "Big Tech", "Fintech", "Healthcare / Biotech", "E-commerce / Retail",
    "Enterprise SaaS", "Developer Tools", "Cybersecurity", "Gaming / Media",
    "Automotive / Robotics", "Energy / Climate", "Education", "Government / Defense",
    "Consulting", "Semiconductors / Hardware", "Logistics", "Social / Consumer",
]

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
STATE_NAME_TO_ABBR = {v.lower(): k for k, v in US_STATES.items()}

# Metro → cities that count as "the same place" for location matching.
US_METROS: dict[str, list[str]] = {
    "San Francisco Bay Area, CA": [
        "San Francisco", "South San Francisco", "Oakland", "Berkeley", "San Jose", "Palo Alto",
        "Mountain View", "Sunnyvale", "Santa Clara", "Menlo Park", "Redwood City",
        "San Mateo", "Cupertino", "Fremont", "Foster City", "Milpitas", "Emeryville",
    ],
    "Seattle, WA": ["Seattle", "Bellevue", "Redmond", "Kirkland", "Bothell", "Tacoma"],
    "New York City, NY": ["New York", "NYC", "Brooklyn", "Manhattan", "Jersey City", "Hoboken"],
    "Boston, MA": ["Boston", "Cambridge", "Somerville", "Waltham", "Burlington"],
    "Austin, TX": ["Austin", "Round Rock"],
    "Dallas–Fort Worth, TX": ["Dallas", "Fort Worth", "Plano", "Irving", "Frisco", "Richardson"],
    "Houston, TX": ["Houston"],
    "Los Angeles, CA": ["Los Angeles", "Santa Monica", "Culver City", "Irvine", "Pasadena", "Playa Vista"],
    "San Diego, CA": ["San Diego", "La Jolla", "Carlsbad"],
    "Chicago, IL": ["Chicago", "Evanston"],
    "Washington DC Metro": ["Washington", "Arlington", "Reston", "McLean", "Herndon", "Bethesda", "Alexandria", "Tysons"],
    "Atlanta, GA": ["Atlanta", "Alpharetta"],
    "Denver–Boulder, CO": ["Denver", "Boulder"],
    "Raleigh–Durham, NC": ["Raleigh", "Durham", "Research Triangle Park", "Cary", "Chapel Hill"],
    "Pittsburgh, PA": ["Pittsburgh"],
    "Philadelphia, PA": ["Philadelphia"],
    "Portland, OR": ["Portland", "Beaverton", "Hillsboro"],
    "Salt Lake City, UT": ["Salt Lake City", "Lehi", "Provo", "Draper"],
    "Phoenix, AZ": ["Phoenix", "Tempe", "Scottsdale", "Chandler"],
    "Minneapolis, MN": ["Minneapolis", "St. Paul", "Saint Paul"],
    "Kansas City, MO–KS": ["Kansas City", "Overland Park", "Lawrence"],
    "Detroit / Ann Arbor, MI": ["Detroit", "Ann Arbor"],
    "Miami, FL": ["Miami", "Fort Lauderdale"],
    "Columbus, OH": ["Columbus"],
    "Nashville, TN": ["Nashville"],
    "St. Louis, MO": ["St. Louis", "Saint Louis"],
}

# --------------------------------------------------------------------------- #
# Skill normalization
# --------------------------------------------------------------------------- #
SKILL_SYNONYMS: dict[str, list[str]] = {
    "python": ["python3", "py"],
    "javascript": ["js", "ecmascript"],
    "typescript": ["ts"],
    "golang": ["go", "go lang"],
    "c++": ["cpp", "c plus plus"],
    "c#": ["csharp", ".net c#"],
    "kubernetes": ["k8s"],
    "machine learning": ["ml"],
    "deep learning": ["dl", "neural networks"],
    "artificial intelligence": ["ai"],
    "natural language processing": ["nlp"],
    "computer vision": ["cv"],
    "large language models": ["llm", "llms", "large language model", "genai", "generative ai"],
    "retrieval-augmented generation": ["rag", "retrieval augmented generation"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "pytorch": ["torch"],
    "tensorflow": ["tf", "keras"],
    "postgresql": ["postgres", "psql"],
    "amazon web services": ["aws"],
    "google cloud platform": ["gcp", "google cloud"],
    "microsoft azure": ["azure"],
    "continuous integration": ["ci/cd", "ci", "cicd", "continuous delivery"],
    "react": ["react.js", "reactjs"],
    "node.js": ["node", "nodejs"],
    "next.js": ["nextjs"],
    "vue": ["vue.js", "vuejs"],
    "sql": ["structured query language"],
    "nosql": ["mongodb", "dynamodb", "cassandra"],
    "docker": ["containers", "containerization"],
    "terraform": ["infrastructure as code", "iac"],
    "rest api": ["restful", "rest apis", "restful api"],
    "graphql": ["gql"],
    "apache spark": ["spark", "pyspark"],
    "apache kafka": ["kafka"],
    "airflow": ["apache airflow"],
    "mlops": ["ml ops", "model deployment"],
    "data structures": ["algorithms", "data structures and algorithms", "dsa"],
    "statistics": ["statistical analysis", "stats"],
    "a/b testing": ["experimentation", "ab testing"],
    "linux": ["unix"],
    "git": ["github", "version control"],
    "vector database": ["vector search", "faiss", "pinecone", "weaviate", "milvus", "chroma"],
    "huggingface": ["hugging face", "transformers"],
}

# Related (not identical) skills → PARTIAL evidence.
RELATED_SKILLS: dict[str, list[str]] = {
    "pytorch": ["tensorflow", "jax"],
    "tensorflow": ["pytorch", "jax"],
    "amazon web services": ["google cloud platform", "microsoft azure"],
    "google cloud platform": ["amazon web services", "microsoft azure"],
    "microsoft azure": ["amazon web services", "google cloud platform"],
    "react": ["vue", "angular", "svelte"],
    "vue": ["react", "angular"],
    "postgresql": ["mysql", "sql server", "sql"],
    "mysql": ["postgresql", "sql"],
    "golang": ["rust", "java", "c++"],
    "java": ["kotlin", "scala", "c#"],
    "kubernetes": ["docker", "ecs", "nomad"],
    "apache kafka": ["kinesis", "pub/sub", "rabbitmq"],
    "apache spark": ["dask", "ray", "hadoop"],
    "large language models": ["natural language processing", "transformers", "huggingface"],
    "retrieval-augmented generation": ["vector database", "large language models"],
    "terraform": ["cloudformation", "pulumi"],
}

_CANON: dict[str, str] = {}
for canon, alts in SKILL_SYNONYMS.items():
    _CANON[canon] = canon
    for alt in alts:
        _CANON.setdefault(alt, canon)


def canonical_skill(term: str) -> str:
    key = re.sub(r"\s+", " ", term.strip().lower())
    return _CANON.get(key, key)


def skill_variants(term: str) -> list[str]:
    canon = canonical_skill(term)
    variants = {canon, term.strip().lower()}
    variants.update(SKILL_SYNONYMS.get(canon, []))
    # Very short aliases ("go", "ai", "ml", "ci", "ts") are only safe as exact tokens;
    # term_in_text() enforces word boundaries so they are kept.
    return sorted(v for v in variants if v)


def term_in_text(term: str, text: str) -> bool:
    """Word-boundary aware match. Fixes the old substring bug where 'go'
    matched 'algorithms' and 'r' matched almost every sentence."""
    t = term.strip().lower()
    if not t:
        return False
    if len(t) <= 2 and t not in {"go", "ai", "ml", "ci", "ts", "js", "r", "c", "ui", "ux", "qa"}:
        return False
    pattern = r"(?<![a-z0-9+#.])" + re.escape(t) + r"(?![a-z0-9+#]|\.[a-z0-9])"
    if t == "go":  # 'Go' is ambiguous in English: require language-like context.
        return bool(re.search(r"(?<![a-z])(golang|go\s*(lang|language|programming|developer|microservices?|services?)|(in|with|using)\s+go\b)", text.lower())) or bool(
            re.search(r"(^|[,/;(|]\s*)go(\s*[,/;)|]|$)", text.lower(), flags=re.M)
        )
    return bool(re.search(pattern, text.lower()))


KNOWN_SKILLS: list[str] = sorted(
    set(SKILL_SYNONYMS)
    | {
        "java", "rust", "scala", "kotlin", "swift", "ruby", "php", "r", "matlab", "bash",
        "html", "css", "tailwind", "angular", "svelte", "django", "flask", "fastapi",
        "spring", "express", "redis", "elasticsearch", "snowflake", "bigquery", "databricks",
        "dbt", "tableau", "power bi", "looker", "pandas", "numpy", "jax", "langchain",
        "llamaindex", "openai api", "prompt engineering", "fine-tuning", "reinforcement learning",
        "recommendation systems", "time series", "etl", "microservices", "distributed systems",
        "system design", "grpc", "websockets", "jenkins", "github actions", "ansible",
        "prometheus", "grafana", "datadog", "splunk", "owasp", "penetration testing",
        "threat modeling", "iam", "networking", "tcp/ip", "ios", "android", "flutter",
        "react native", "unity", "cuda", "opencv", "embedded c", "rtos", "mlflow", "ray",
        "kinesis", "rabbitmq", "mysql", "sql server", "oracle", "hadoop", "hive", "excel",
        "jira", "agile", "scrum", "figma", "selenium", "cypress", "jest", "pytest",
        "streamlit", "gemini", "langgraph", "bm25", "vertex ai", "sagemaker", "lambda", "s3", "ec2",
    }
)

# --------------------------------------------------------------------------- #
# Seniority & degree inference
# --------------------------------------------------------------------------- #
SENIORITY_TITLE_PATTERNS: list[tuple[str, str]] = [
    ("intern", r"\b(intern|internship|co-?op)\b"),
    ("principal", r"\b(principal|distinguished|fellow|chief architect)\b"),
    ("staff", r"\b(staff|lead architect)\b"),
    ("manager", r"\b(manager|director|head of|vp|vice president)\b"),
    ("senior", r"\b(senior|sr\.?|lead|iii|level\s*3|l5)\b"),
    ("entry", r"\b(new\s*grad|graduate|entry[-\s]?level|junior|jr\.?|associate|early career|university grad|i\b|level\s*1|l3)\b"),
    ("mid", r"\b(mid[-\s]?level|ii\b|level\s*2|l4)\b"),
]

DEGREE_PATTERNS: list[tuple[str, str]] = [
    ("phd", r"\b(ph\.?\s?d|doctorate|doctoral)\b"),
    ("master", r"\b(master'?s?|m\.?s\.?|msc|m\.?eng|mba)\b"),
    ("bachelor", r"\b(bachelor'?s?|b\.?s\.?|b\.?a\.?|bsc|b\.?eng|undergraduate degree)\b"),
    ("associate", r"\bassociate'?s? degree\b"),
]

# --------------------------------------------------------------------------- #
# Work authorization language (checked against the raw posting text)
# --------------------------------------------------------------------------- #
SPONSORSHIP_PATTERNS: dict[str, list[str]] = {
    "no_sponsorship": [
        r"(unable|not able|cannot|can ?not|can't|will not|won't|do(es)? not|are not able to|is not able to)\s+(to\s+)?(provide|offer|support|consider)?\s*(visa\s+|employment\s+|immigration\s+|work\s+)?sponsor",
        r"(visa|immigration|employment|h-?1b)\s+sponsorship\s+(is\s+|will\s+)?(not|un)\s*(available|provided|offered|supported|be provided)",
        r"no\s+(visa\s+|immigration\s+|h-?1b\s+)?sponsorship",
        r"without\s+(the\s+)?(need\s+for\s+|requiring\s+)?(current\s+or\s+future\s+|now\s+or\s+in\s+the\s+future\s+)?(employer\s+|visa\s+|immigration\s+)?sponsorship",
        r"(now\s+or\s+in\s+the\s+future|current\s+or\s+future)\s+(visa\s+|immigration\s+)?sponsorship\s+(is\s+)?(not|will not)",
        r"not\s+(eligible|open)\s+(for|to)\s+(visa\s+)?sponsorship",
        r"sponsorship\s+(is\s+)?not\s+(available|an option)",
    ],
    "citizen_only": [
        r"(must|required to)\s+be\s+(a\s+)?(u\.?s\.?|united states)\s+citizen",
        r"(u\.?s\.?|united states)\s+citizenship\s+(is\s+)?(required|mandatory)",
        r"(only|open to)\s+(u\.?s\.?\s+)?citizens?\s+(and|or)\s+(permanent residents|green card holders)",
        r"green\s*card\s+holders?\s+(only|or\s+(u\.?s\.?\s+)?citizens)",
        r"\bu\.?s\.?\s+persons?\b.*\b(itar|export control)",
        r"\b(itar|ear)\b.*\bu\.?s\.?\s+person",
    ],
    "clearance": [
        r"(active|current|existing|ability to obtain|able to obtain|eligible (for|to obtain))\s+(an?\s+)?(dod\s+)?(secret\s+|top secret\s+|ts/sci\s+|ts\s*/\s*sci\s+|public trust\s+)?(security\s+)?clearance",
        r"(secret|top secret|ts/sci)\s+clearance\s+(is\s+)?(required|needed)",
        r"clearance\s+(is\s+)?required",
    ],
    "sponsors": [
        r"(visa|h-?1b|immigration)\s+sponsorship\s+(is\s+)?(available|provided|offered|supported)",
        r"(we|will|can|able to)\s+(do\s+)?(sponsor|provide sponsorship)",
        r"sponsorship\s+(is\s+)?available",
        r"open\s+to\s+(visa\s+)?sponsorship",
        r"(offer|provide)s?\s+(visa|h-?1b)\s+sponsorship",
    ],
}

CLOSED_POSTING_PATTERNS = [
    r"no longer accepting applications",
    r"(job|position|posting|role|requisition) (is )?(no longer|not) (available|open|active)",
    r"this (job|position) has (been filled|expired|been closed)",
    r"the job you are (looking for|trying to apply for) (is no longer|has expired|was not found)",
    r"position (has been )?(filled|closed)",
    r"job not found",
    r"page (you requested )?(could not|cannot) be found",
    r"this job (post|posting)? ?is closed",
]

PAY_TRANSPARENCY_STATES = {"CA", "CO", "NY", "WA", "IL", "MD", "HI", "MN", "VT", "MA", "NJ", "DC"}

ATS_SITE_FILTER = (
    "(site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co "
    "OR site:jobs.ashbyhq.com OR site:myworkdayjobs.com OR site:jobs.smartrecruiters.com)"
)

AGGREGATOR_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com", "monster.com",
    "simplyhired.com", "careerbuilder.com", "dice.com", "wellfound.com", "builtin.com",
    "jooble.org", "talent.com", "adzuna.com", "jobright.ai", "levels.fyi", "handshake.com",
    "joinhandshake.com", "google.com",
}

NON_US_REMOTE_MARKERS = [
    "canada", "united kingdom", " uk", "europe", "emea", "india", "germany", "latam",
    "latin america", "apac", "mexico", "brazil", "poland", "spain", "portugal", "philippines",
    "australia", "singapore", "netherlands", "ireland", "france", "japan", "china", "israel",
]
