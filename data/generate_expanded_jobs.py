"""Generate expanded corpus of 40 diverse, realistic tech job postings.

Covers:
- Machine Learning / AI / Data Science (10 roles)
- Backend & Distributed Systems (8 roles)
- Frontend & Full-Stack (6 roles)
- Cloud, Platform & DevOps (6 roles)
- Data Engineering & Analytics (5 roles)
- Cybersecurity & Governance (5 roles)
"""

import json
from pathlib import Path

JOBS = [
    # --- 10 ORIGINAL JOBS PRESERVED FOR CONSISTENCY ---
    {
        "id": "northstar-ml-001",
        "title": "Machine Learning Engineer",
        "company": "Northstar Health AI",
        "location": "Chicago, IL",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$118,000–$148,000",
        "description": "Build and operate machine-learning services that help hospital care teams identify patients who may benefit from earlier clinical intervention. You will partner with data scientists and platform engineers to turn validated models into monitored, auditable production APIs. This role works with sensitive health data and values reproducibility, careful model evaluation, and clear documentation over experimentation for its own sake.",
        "responsibilities": [
            "Productionize PyTorch and scikit-learn models behind reliable Python APIs",
            "Create model monitoring for drift, calibration, latency, and data-quality signals",
            "Collaborate with clinical stakeholders to document assumptions and failure modes",
            "Improve containerized training and deployment workflows on AWS"
        ],
        "required_skills": ["Python", "PyTorch", "SQL", "AWS", "Docker", "MLOps"],
        "preferred_skills": ["FastAPI", "MLflow", "Healthcare data", "Kubernetes"]
    },
    {
        "id": "loopline-fe-002",
        "title": "Frontend Product Engineer",
        "company": "Loopline Collaboration",
        "location": "Remote — United States",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$110,000–$142,000",
        "description": "Own polished user-facing workflows for a collaborative planning product used by distributed teams. The product includes data-dense timelines, real-time presence, and accessible keyboard interactions. Engineers work directly with design and customer research, ship in small increments, and are expected to contribute to frontend architecture as well as product decisions.",
        "responsibilities": [
            "Develop responsive product experiences with React, TypeScript, and Next.js",
            "Translate design-system patterns into accessible, reusable components",
            "Write unit and browser-level tests for critical planning workflows",
            "Use product analytics and customer feedback to refine shipped features"
        ],
        "required_skills": ["React", "TypeScript", "Next.js", "CSS", "Testing", "Accessibility"],
        "preferred_skills": ["Playwright", "Design systems", "WebSockets", "Product analytics"]
    },
    {
        "id": "greengrid-ds-003",
        "title": "Data Scientist, Energy Analytics",
        "company": "GreenGrid Systems",
        "location": "Austin, TX",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$112,000–$145,000",
        "description": "Develop forecasting and decision-support models for commercial energy customers managing solar generation, storage, and time-of-use pricing. The team combines telemetry, weather, and billing data to recommend operational changes with measurable cost and emissions outcomes. Success requires both statistical rigor and the ability to explain results to non-technical partners.",
        "responsibilities": [
            "Build and evaluate time-series forecasts and causal impact analyses",
            "Create reproducible data preparation and model-evaluation pipelines",
            "Design decision-ready Tableau dashboards for operations teams",
            "Present model limitations and business recommendations to customers"
        ],
        "required_skills": ["Python", "SQL", "scikit-learn", "Statistics", "Time series", "Tableau"],
        "preferred_skills": ["Causal inference", "Energy markets", "dbt", "Airflow"]
    },
    {
        "id": "finwave-be-004",
        "title": "Backend Systems Engineer",
        "company": "FinWave Clearing",
        "location": "New York, NY",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$145,000–$185,000",
        "description": "Scale mission-critical transaction reconciliation pipelines handling millions of high-throughput ledger entries daily. We value determinism, transaction isolation, strict schema contracts, and observable telemetry across high-availability microservices.",
        "responsibilities": [
            "Architect high-throughput settlement services in Go and Java",
            "Design idempotent event-driven pipelines using Apache Kafka and PostgreSQL",
            "Mitigate latency regressions and audit memory bottlenecks under peak traffic",
            "Participate in on-call rotation and lead root-cause postmortems"
        ],
        "required_skills": ["Go", "PostgreSQL", "Kafka", "Distributed Systems", "Docker", "Linux"],
        "preferred_skills": ["Java", "gRPC", "Kubernetes", "FinTech"]
    },
    {
        "id": "skyward-platform-005",
        "title": "Cloud Platform & DevOps Engineer",
        "company": "Skyward Cloud Solutions",
        "location": "Seattle, WA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$125,000–$155,000",
        "description": "Provide a reliable, self-service Kubernetes infrastructure platform for 50+ backend microservice teams. Eliminate deployment friction while maintaining zero-trust cloud security and SOC2 compliance standards.",
        "responsibilities": [
            "Maintain multi-region AWS and GCP Kubernetes clusters via Terraform and GitOps",
            "Construct automated CI/CD deployment pipelines using GitHub Actions and ArgoCD",
            "Implement end-to-end observability using Prometheus, Grafana, and OpenTelemetry",
            "Automate resource governance and cost optimization across cloud fleets"
        ],
        "required_skills": ["Kubernetes", "Terraform", "AWS", "CI/CD", "Docker", "Python"],
        "preferred_skills": ["ArgoCD", "Prometheus", "GCP", "Go"]
    },
    {
        "id": "nexus-nlp-006",
        "title": "NLP / LLM Research Engineer",
        "company": "Nexus Cognition",
        "location": "San Francisco, CA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$160,000–$210,000",
        "description": "Design retrieval-augmented generation (RAG) pipelines, model fine-tuning architectures, and evaluation guardrails for enterprise customer knowledge search engines.",
        "responsibilities": [
            "Implement production RAG workflows using vector databases, LangChain, and dense embeddings",
            "Conduct parameter-efficient fine-tuning (LoRA, QLoRA) on open-source foundation models",
            "Establish automated hallucination detection, guardrail scoring, and benchmark evals",
            "Optimize inference serving latency with vLLM and TensorRT-LLM"
        ],
        "required_skills": ["Python", "PyTorch", "Transformers", "NLP", "Vector Databases", "LLM"],
        "preferred_skills": ["LangChain", "vLLM", "RAG", "FAISS"]
    },
    {
        "id": "sentinel-sec-007",
        "title": "Application Security Engineer",
        "company": "Sentinel Defense Labs",
        "location": "Washington, DC",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$120,000–$150,000",
        "description": "Protect customer-facing cloud APIs, web applications, and internal CI/CD pipelines from injection vulnerabilities, authentication bypasses, and supply-chain exploits.",
        "responsibilities": [
            "Perform vulnerability assessments, penetration testing, and code security audits",
            "Integrate SAST, DAST, and secret scanning into GitHub Actions pipelines",
            "Partner with software engineers to remediate OWASP Top 10 vulnerabilities",
            "Author security architecture standards and incident response playbooks"
        ],
        "required_skills": ["Python", "Application Security", "Penetration Testing", "OWASP", "Linux", "CI/CD"],
        "preferred_skills": ["Burp Suite", "OAuth2", "Cryptography", "AWS Security"]
    },
    {
        "id": "flowdata-de-008",
        "title": "Data Platform Engineer",
        "company": "FlowData Infrastructure",
        "location": "Boston, MA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$148,000",
        "description": "Design reliable lakehouse pipelines moving billions of clickstream events and transactional records into warehouse analytics stores with sub-minute SLAs.",
        "responsibilities": [
            "Build robust batch and streaming ELT pipelines using Apache Spark and Apache Kafka",
            "Manage data models and transformations in Snowflake and BigQuery using dbt",
            "Implement automated data quality checks, anomaly detection, and schema migration tests",
            "Collaborate with BI analysts to deliver clean, documented semantic schemas"
        ],
        "required_skills": ["Python", "SQL", "Apache Spark", "dbt", "Snowflake", "Data Warehousing"],
        "preferred_skills": ["Kafka", "Airflow", "BigQuery", "Iceberg"]
    },
    {
        "id": "omniview-fullstack-009",
        "title": "Full-Stack Web Engineer",
        "company": "OmniView Analytics",
        "location": "Denver, CO",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$110,000–$140,000",
        "description": "Develop full-lifecycle web features across an interactive SaaS analytics suite, connecting intuitive React/TypeScript interfaces to performant FastAPI and PostgreSQL backends.",
        "responsibilities": [
            "Deliver end-to-end features spanning React/Tailwind frontends and Python APIs",
            "Design relational schemas, SQL indexes, and RESTful endpoints for analytical queries",
            "Write comprehensive automated unit, integration, and E2E Cypress tests",
            "Monitor application health, error tracking with Sentry, and user engagement metrics"
        ],
        "required_skills": ["React", "TypeScript", "Python", "FastAPI", "PostgreSQL", "REST API"],
        "preferred_skills": ["Tailwind CSS", "Docker", "Cypress", "Redis"]
    },
    {
        "id": "apex-ai-cv-010",
        "title": "Computer Vision & Edge ML Engineer",
        "company": "Apex Autonomous Mobility",
        "location": "San Jose, CA",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$155,000–$195,000",
        "description": "Develop and optimize real-time computer vision models (object detection, depth estimation) deployed directly to embedded robotic edge devices.",
        "responsibilities": [
            "Train and quantize PyTorch deep learning vision models for edge runtimes (ONNX, TensorRT)",
            "Build automated data labeling, augmentation, and synthetic generation pipelines",
            "Benchmark and minimize frame latency and power consumption on Jetson platforms",
            "Interface with hardware teams to validate camera sensor calibration and driver integrity"
        ],
        "required_skills": ["Python", "C++", "PyTorch", "Computer Vision", "OpenCV", "Deep Learning"],
        "preferred_skills": ["TensorRT", "ONNX", "Embedded Systems", "CUDA"]
    },

    # --- 30 EXPANDED REALISTIC TECH JOBS ---
    {
        "id": "quantedge-ml-011",
        "title": "Quantitative ML Researcher",
        "company": "QuantEdge Capital",
        "location": "New York, NY",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$150,000–$220,000",
        "description": "Apply machine learning and statistical signal processing to tick-level financial market data to discover predictive alpha signals and execute algorithmic trading strategies.",
        "responsibilities": [
            "Develop gradient-boosted and recurrent neural networks for time-series alpha generation",
            "Backtest trading hypotheses with realistic transaction costs, slippage, and market impact",
            "Construct clean data pipelines for petabyte-scale historical order book logs",
            "Collaborate with traders to deploy low-latency inference models"
        ],
        "required_skills": ["Python", "C++", "scikit-learn", "Statistics", "Time series", "SQL"],
        "preferred_skills": ["NumPy", "Pandas", "Quantitative Finance", "KDB+/Q"]
    },
    {
        "id": "biotrack-bioinfo-012",
        "title": "Computational Biology & Genomics Scientist",
        "company": "BioTrack Therapeutics",
        "location": "Cambridge, MA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$125,000–$160,000",
        "description": "Analyze single-cell RNA sequencing and clinical trial genomics data to identify biomarkers for targeted oncology therapeutics.",
        "responsibilities": [
            "Process high-throughput sequencing datasets using Nextflow and Python pipelines",
            "Apply clustering, differential expression, and pathway enrichment algorithms",
            "Maintain reproducible scientific computing notebooks and statistical reports",
            "Integrate public clinical databases (TCGA, ClinVar, Ensembl) with internal assays"
        ],
        "required_skills": ["Python", "R", "Statistics", "Genomics", "Nextflow", "Bioinformatics"],
        "preferred_skills": ["Single-cell RNA", "Bioconductor", "Docker", "Machine Learning"]
    },
    {
        "id": "hypercloud-sre-013",
        "title": "Site Reliability Engineer (SRE)",
        "company": "HyperCloud Systems",
        "location": "Dallas, TX",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$135,000–$175,000",
        "description": "Ensure the 99.99% availability, resilience, and operational scalability of global multi-tenant microservices through automation and chaos engineering.",
        "responsibilities": [
            "Define and monitor Service Level Objectives (SLOs), Error Budgets, and Alerting policies",
            "Automate incident mitigation scripts and self-healing cloud routines using Python and Go",
            "Execute chaos engineering experiments to discover distributed failure modes",
            "Optimize Kubernetes autoscaling, egress traffic, and multi-region failover"
        ],
        "required_skills": ["Kubernetes", "Linux", "Go", "Python", "Prometheus", "Terraform"],
        "preferred_skills": ["Chaos Mesh", "Datadog", "Istio", "Cloud Networking"]
    },
    {
        "id": "retailiq-ds-014",
        "title": "E-Commerce Data Scientist, Personalization",
        "company": "RetailIQ Marketplace",
        "location": "Seattle, WA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Junior",
        "salary_range": "$95,000–$125,000",
        "description": "Help design and evaluate recommendation algorithms and two-sided ranking mechanisms for millions of active online shopping consumers.",
        "responsibilities": [
            "Analyze large customer clickstream logs using SQL and PySpark",
            "Implement collaborative filtering and two-tower vector retrieval models",
            "Design and analyze rigorous online A/B hypothesis tests with power calculations",
            "Synthesize feature importance findings into product strategy recommendations"
        ],
        "required_skills": ["Python", "SQL", "scikit-learn", "A/B Testing", "Statistics", "Pandas"],
        "preferred_skills": ["Spark", "Recommendation Systems", "PyTorch", "GCP"]
    },
    {
        "id": "streambyte-infra-015",
        "title": "Distributed Streaming Infrastructure Engineer",
        "company": "StreamByte Networks",
        "location": "San Francisco, CA",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$160,000–$205,000",
        "description": "Architect and maintain ultra-reliable, petabyte-scale stream processing backbones built on Apache Kafka, Apache Flink, and Rust.",
        "responsibilities": [
            "Design low-latency stateful stream processing engines handling 5M+ events/sec",
            "Manage distributed Kafka clusters with strict zero data loss guarantees",
            "Profile network socket I/O, JVM GC pauses, and Linux kernel TCP buffers",
            "Develop declarative client SDKs and schema validation registries"
        ],
        "required_skills": ["Go", "Kafka", "Distributed Systems", "Linux", "Docker", "Java"],
        "preferred_skills": ["Rust", "Flink", "Netty", "OpenTelemetry"]
    },
    {
        "id": "vitalhealth-ds-016",
        "title": "Healthcare Clinical Data Scientist",
        "company": "VitalHealth Informatics",
        "location": "Nashville, TN",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$145,000",
        "description": "Mine electronic health record (EHR) longitudinal data to forecast hospital readmission risk and identify adverse drug interactions.",
        "responsibilities": [
            "Query and harmonize messy HL7/FHIR and OMOP common data model schemas with SQL",
            "Train interpretable risk prediction models (logistic regression, survival analysis, XGBoost)",
            "Collaborate with medical researchers to validate epidemiological study designs",
            "Ensure compliance with HIPAA patient privacy de-identification protocols"
        ],
        "required_skills": ["Python", "SQL", "scikit-learn", "Healthcare data", "Statistics", "Pandas"],
        "preferred_skills": ["FHIR", "Survival Analysis", "XGBoost", "R"]
    },
    {
        "id": "cloudshield-sec-017",
        "title": "Cloud Security & Compliance Engineer",
        "company": "CloudShield Networks",
        "location": "Atlanta, GA",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$125,000–$155,000",
        "description": "Enforce automated security baselines, identity governance (IAM), and continuous compliance monitoring across multi-tenant AWS and Azure environments.",
        "responsibilities": [
            "Author Infrastructure-as-Code security policies using OPA Rego and Terraform",
            "Configure AWS Security Hub, GuardDuty, and CloudTrail automated remediation",
            "Manage enterprise identity lifecycle, SAML/SSO, and least-privilege RBAC roles",
            "Lead SOC2 and ISO27001 evidence collection and technical audit defense"
        ],
        "required_skills": ["AWS", "Terraform", "Cloud Security", "Python", "CI/CD", "Linux"],
        "preferred_skills": ["OPA Rego", "IAM", "Azure", "SOC2"]
    },
    {
        "id": "paypulse-be-018",
        "title": "Payment API Backend Engineer",
        "company": "PayPulse Systems",
        "location": "Chicago, IL",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Junior",
        "salary_range": "$90,000–$120,000",
        "description": "Build resilient REST APIs and webhook ingestion engines powering seamless merchant checkout experiences and ledger synchronizations.",
        "responsibilities": [
            "Write clean, well-tested Python/FastAPI and PostgreSQL microservices",
            "Integrate external banking and card processor settlement protocols",
            "Maintain asynchronous background task queues using Redis and Celery",
            "Author detailed OpenAPI/Swagger documentation and client quickstart guides"
        ],
        "required_skills": ["Python", "FastAPI", "SQL", "PostgreSQL", "REST API", "Git"],
        "preferred_skills": ["Docker", "Redis", "Celery", "Stripe API"]
    },
    {
        "id": "visioncraft-fe-019",
        "title": "Senior Frontend Architecture Engineer",
        "company": "VisionCraft Creative Suite",
        "location": "San Francisco, CA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$150,000–$190,000",
        "description": "Drive the architecture of a high-performance in-browser canvas design tool handling complex vector graphics, WebGL rendering, and multi-user collaboration.",
        "responsibilities": [
            "Architect modular React and TypeScript applications with strict state isolation",
            "Optimize 60fps canvas render loops using WebGL and WebAssembly",
            "Establish automated frontend performance benchmarks (LCP, INP, memory profiling)",
            "Mentor engineering team on modern component patterns and accessibility standards"
        ],
        "required_skills": ["React", "TypeScript", "JavaScript", "CSS", "Testing", "Performance"],
        "preferred_skills": ["WebGL", "WebAssembly", "Zustand", "Canvas API"]
    },
    {
        "id": "cyberguard-soc-020",
        "title": "Incident Response & Detection Engineer",
        "company": "CyberGuard SOC",
        "location": "Reston, VA",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$145,000",
        "description": "Analyze network telemetry, endpoint alerts, and SIEM logs to investigate suspicious adversary intrusion attempts and automate response playbooks.",
        "responsibilities": [
            "Investigate endpoint detection and response (EDR) alerts across enterprise hosts",
            "Write detection engineering rules (Sigma, YARA, Splunk SPL) for emerging threats",
            "Automate forensic triage workflows using Python and SOAR orchestration",
            "Participate in live incident response and conduct adversary postmortems"
        ],
        "required_skills": ["Python", "Linux", "SIEM", "Incident Response", "Network Security", "Cybersecurity"],
        "preferred_skills": ["Splunk", "EDR", "YARA", "Threat Hunting"]
    },
    {
        "id": "neuroverse-ai-021",
        "title": "Generative AI Solutions Engineer",
        "company": "NeuroVerse AI",
        "location": "New York, NY",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$130,000–$165,000",
        "description": "Partner with enterprise customers to design, prototype, and ship custom LLM agent workflows, semantic search indexes, and autonomous conversational assistants.",
        "responsibilities": [
            "Build multimodal agent workflows using LangChain, LlamaIndex, and function calling",
            "Tune vector similarity search indexes and hybrid reranking mechanisms",
            "Evaluate model output accuracy, prompt injections, and grounded attribution",
            "Deploy secure containerized AI microservices on Google Cloud Platform (GCP)"
        ],
        "required_skills": ["Python", "NLP", "LLM", "Vector Databases", "Docker", "GCP"],
        "preferred_skills": ["LangChain", "LlamaIndex", "FastAPI", "Prompt Engineering"]
    },
    {
        "id": "datalake-eng-022",
        "title": "Big Data & Spark Pipeline Engineer",
        "company": "DataLake Dynamics",
        "location": "Minneapolis, MN",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$140,000–$175,000",
        "description": "Scale enterprise big data architectures processing multi-terabyte analytical workloads across distributed Apache Spark and Apache Iceberg storage layers.",
        "responsibilities": [
            "Tune complex PySpark and Scala jobs to eliminate shuffle skew and memory OOMs",
            "Migrate legacy Hive tables to modern open table formats (Apache Iceberg, Delta Lake)",
            "Automate DAG orchestration schedules with Apache Airflow and dbt",
            "Implement metadata governance, data lineage, and column-level encryption"
        ],
        "required_skills": ["Python", "Apache Spark", "SQL", "Airflow", "Data Warehousing", "AWS"],
        "preferred_skills": ["Scala", "Iceberg", "dbt", "Delta Lake"]
    },
    {
        "id": "cloudbridge-devops-023",
        "title": "DevOps Automation Specialist",
        "company": "CloudBridge Systems",
        "location": "Austin, TX",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Junior",
        "salary_range": "$85,000–$115,000",
        "description": "Modernize team deployment infrastructure, automate testing pipelines, and accelerate feature shipping velocity for an agile SaaS team.",
        "responsibilities": [
            "Maintain GitHub Actions and GitLab CI/CD pipelines with caching and parallel stages",
            "Manage container images with Dockerfile multi-stage builds and vulnerability audits",
            "Write modular Terraform configurations for AWS RDS, S3, and ECS services",
            "Monitor server health with CloudWatch and draft on-call operational runbooks"
        ],
        "required_skills": ["Linux", "Docker", "AWS", "CI/CD", "Git", "Python"],
        "preferred_skills": ["Terraform", "Bash", "GitHub Actions", "Kubernetes"]
    },
    {
        "id": "deepvision-robotics-024",
        "title": "Robotics Perception & SLAM Engineer",
        "company": "DeepVision Robotics",
        "location": "Pittsburgh, PA",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$150,000–$190,000",
        "description": "Build real-time 3D perception, point-cloud segmentation, and visual-inertial odometry algorithms for autonomous warehouse logistics robots.",
        "responsibilities": [
            "Implement Visual SLAM and LiDAR odometry algorithms running on ROS2 in C++",
            "Develop deep learning models for dynamic obstacle detection and track prediction",
            "Optimize point cloud processing using PCL and GPU acceleration",
            "Validate vehicle navigation safety in both simulated Gazebo and physical environments"
        ],
        "required_skills": ["C++", "Python", "Computer Vision", "ROS2", "Linux", "Deep Learning"],
        "preferred_skills": ["SLAM", "LiDAR", "PyTorch", "CUDA"]
    },
    {
        "id": "marketpulse-analytics-025",
        "title": "Business Intelligence & Product Analyst",
        "company": "MarketPulse Media",
        "location": "Los Angeles, CA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Junior",
        "salary_range": "$80,000–$105,000",
        "description": "Uncover user retention trends, conversion funnel drop-offs, and feature adoption metrics to guide executive product roadmaps.",
        "responsibilities": [
            "Write complex SQL analytical queries (window functions, cohort analysis, retention curves)",
            "Build automated executive KPI dashboards in Tableau and PowerBI",
            "Partner with product managers to formulate clear quantitative hypotheses",
            "Conduct exploratory data analysis using Python and Pandas for ad-hoc inquiries"
        ],
        "required_skills": ["SQL", "Tableau", "Python", "Data Analysis", "Statistics", "Pandas"],
        "preferred_skills": ["PowerBI", "A/B Testing", "dbt", "Excel"]
    },
    {
        "id": "securefin-appsec-026",
        "title": "Product Security Engineer",
        "company": "SecureFin Digital Banking",
        "location": "New York, NY",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$145,000–$185,000",
        "description": "Act as the primary security partner for fintech engineering pods, ensuring zero cryptographic regressions, hardened API authentication, and PCI-DSS compliance.",
        "responsibilities": [
            "Conduct threat modeling and architectural security reviews for new financial features",
            "Audit OAuth2/OIDC implementation, JWT token handling, and session storage",
            "Review third-party open source dependency risk and maintain software bill of materials (SBOM)",
            "Champion secure coding best practices and organize internal capture-the-flag workshops"
        ],
        "required_skills": ["Application Security", "Python", "OWASP", "OAuth2", "Cryptography", "REST API"],
        "preferred_skills": ["Java", "FinTech", "Threat Modeling", "Kubernetes"]
    },
    {
        "id": "novanlp-research-027",
        "title": "Machine Learning Scientist, Multimodal AI",
        "company": "NovaNLP Laboratories",
        "location": "Seattle, WA",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$165,000–$215,000",
        "description": "Lead applied research in cross-attention architectures linking vision and language models for zero-shot video understanding and document reasoning.",
        "responsibilities": [
            "Train large-scale multimodal models using PyTorch, DeepSpeed, and Megatron-LM",
            "Curate high-quality synthetic pre-training and reinforcement learning (RLHF/DPO) datasets",
            "Publish findings in top academic machine learning conferences (NeurIPS, ICML, ACL)",
            "Translate scientific breakthroughs into lightweight deployable checkpoint artifacts"
        ],
        "required_skills": ["Python", "PyTorch", "Deep Learning", "Transformers", "NLP", "Machine Learning"],
        "preferred_skills": ["Computer Vision", "DeepSpeed", "RLHF", "CUDA"]
    },
    {
        "id": "agilestack-mobile-028",
        "title": "iOS Mobile Application Engineer",
        "company": "AgileStack Mobile",
        "location": "San Diego, CA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$145,000",
        "description": "Craft smooth, battery-efficient iOS client apps connecting hundreds of thousands of active users to real-time audio and social interactions.",
        "responsibilities": [
            "Develop modern declarative iOS interfaces with Swift and SwiftUI",
            "Architect offline-first local cache synchronization using CoreData and SwiftData",
            "Instrument mobile telemetry, crash analytics, and memory footprint tracking",
            "Ship reliable weekly App Store releases via Fastlane automation"
        ],
        "required_skills": ["Swift", "iOS", "SwiftUI", "Git", "REST API", "Testing"],
        "preferred_skills": ["CoreData", "Fastlane", "Combine", "GraphQL"]
    },
    {
        "id": "cloudmatrix-k8s-029",
        "title": "Kubernetes Infrastructure Specialist",
        "company": "CloudMatrix Systems",
        "location": "Austin, TX",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$145,000–$180,000",
        "description": "Build high-density container orchestration clusters running heterogeneous GPU and CPU compute workloads across bare-metal and hybrid public clouds.",
        "responsibilities": [
            "Author custom Kubernetes Operators in Go using Kubebuilder and Controller-Runtime",
            "Optimize Cilium eBPF network routing and pod network throughput",
            "Automate cluster provisioning across multi-tenant regions with Cluster API",
            "Manage hardware-accelerated GPU device plugin drivers for AI inference pods"
        ],
        "required_skills": ["Kubernetes", "Go", "Linux", "Docker", "Terraform", "Distributed Systems"],
        "preferred_skills": ["eBPF", "Cilium", "GPU Orchestration", "Prometheus"]
    },
    {
        "id": "dataweave-etl-030",
        "title": "Analytics Engineer & Semantic Modeler",
        "company": "DataWeave Insights",
        "location": "Chicago, IL",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$110,000–$138,000",
        "description": "Bridge raw data warehousing infrastructure and business intelligence by crafting rigorous, tested dbt models and self-service semantic metrics.",
        "responsibilities": [
            "Develop modular, incremental dbt models adhering to star-schema modeling conventions",
            "Automate data quality testing, freshness alerts, and schema documentation",
            "Optimize Snowflake warehouse query costs, clustering keys, and caching",
            "Partner with growth and finance teams to codify enterprise metric definitions"
        ],
        "required_skills": ["SQL", "dbt", "Snowflake", "Data Warehousing", "Python", "Git"],
        "preferred_skills": ["Airflow", "BigQuery", "Looker", "CI/CD"]
    },
    {
        "id": "infinitenet-backend-031",
        "title": "Backend Microservices Architect",
        "company": "InfiniteNet Telecom",
        "location": "Philadelphia, PA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$140,000–$175,000",
        "description": "Lead the modernization of legacy monolithic services into resilient, event-driven microservices processing network signaling and subscriber billing.",
        "responsibilities": [
            "Develop scalable microservices in Java/Spring Boot and Go",
            "Design event streaming schemas using Apache Kafka and Avro",
            "Refactor relational database queries in Oracle and PostgreSQL for zero downtime",
            "Enforce microservice observability standards with Jaeger distributed tracing"
        ],
        "required_skills": ["Java", "Spring Boot", "SQL", "Kafka", "Microservices", "Docker"],
        "preferred_skills": ["Go", "PostgreSQL", "Kubernetes", "gRPC"]
    },
    {
        "id": "pixelwave-ux-032",
        "title": "UI/UX Design Systems Engineer",
        "company": "PixelWave Studio",
        "location": "New York, NY",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$145,000",
        "description": "Design and engineer enterprise design system components uniting Figma mockups with bulletproof, accessible React/TypeScript web implementations.",
        "responsibilities": [
            "Build accessible headless components (Radix/Aria) in React, TypeScript, and Tailwind",
            "Maintain Storybook documentation and automated visual regression test suites",
            "Conduct WCAG 2.1 AA accessibility audits and screen-reader usability trials",
            "Partner with UX designers to translate fluid design tokens into CSS variables"
        ],
        "required_skills": ["React", "TypeScript", "CSS", "Accessibility", "Design systems", "Testing"],
        "preferred_skills": ["Storybook", "Tailwind CSS", "Figma", "Playwright"]
    },
    {
        "id": "trustauth-security-033",
        "title": "Zero Trust Security Architect",
        "company": "TrustAuth Identity",
        "location": "Washington, DC",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$150,000–$195,000",
        "description": "Architect zero-trust access fabrics, microsegmentation, and device health attestation across thousands of remote corporate workstations and cloud resources.",
        "responsibilities": [
            "Architect mutual TLS (mTLS), SPIFFE/SPIRE, and identity-aware proxy perimeters",
            "Develop automated identity lifecycle management and privileged access policies",
            "Conduct adversary emulation and purple-team exercises against perimeter gateways",
            "Present threat models and executive risk briefings to C-level stakeholders"
        ],
        "required_skills": ["Cybersecurity", "Network Security", "Linux", "Application Security", "Python", "Cloud Security"],
        "preferred_skills": ["mTLS", "Zero Trust", "OAuth2", "PKI"]
    },
    {
        "id": "algosphere-ds-034",
        "title": "Recommendation Systems Engineer",
        "company": "AlgoSphere Social",
        "location": "New York, NY",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$135,000–$170,000",
        "description": "Build two-stage retrieval and ranking models driving personalized video discovery feeds for 20M+ daily active mobile viewers.",
        "responsibilities": [
            "Train graph neural networks and deep factorization machines in PyTorch",
            "Scale approximate nearest neighbor (ANN) vector search indexes (HNSW, ScaNN)",
            "Run multivariate online A/B trials tracking long-term user engagement and diversity",
            "Collaborate with trust and safety teams to down-rank clickbait and toxic content"
        ],
        "required_skills": ["Python", "PyTorch", "Recommendation Systems", "SQL", "A/B Testing", "Machine Learning"],
        "preferred_skills": ["Graph Neural Networks", "HNSW", "Spark", "MLOps"]
    },
    {
        "id": "corepulse-go-035",
        "title": "Go Backend Developer, Cloud Core",
        "company": "CorePulse Technologies",
        "location": "Austin, TX",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Junior",
        "salary_range": "$92,000–$122,000",
        "description": "Write fast, concurrent microservices in Go backing our multi-tenant cloud storage gateway and metadata caching services.",
        "responsibilities": [
            "Develop gRPC and REST service endpoints in idiomatic Go",
            "Write comprehensive unit and integration tests with race detector validation",
            "Implement connection pooling, retries with backoff, and distributed rate limiting",
            "Package services into minimal scratch Docker containers and deploy to Kubernetes"
        ],
        "required_skills": ["Go", "SQL", "Docker", "REST API", "Git", "Linux"],
        "preferred_skills": ["gRPC", "PostgreSQL", "Kubernetes", "Redis"]
    },
    {
        "id": "healthai-cv-036",
        "title": "Medical Imaging AI Research Engineer",
        "company": "HealthAI Diagnostics",
        "location": "Boston, MA",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$155,000–$195,000",
        "description": "Develop 3D convolutional neural networks and vision transformers for automated anomaly detection in MRI and CT radiology scans.",
        "responsibilities": [
            "Preprocess and augment volumetric DICOM imaging scans with MONAI and PyTorch",
            "Train segmentation and classification models with certified clinical accuracy",
            "Validate model explainability using Grad-CAM and integrated gradients",
            "Ensure full adherence to FDA software-as-a-medical-device (SaMD) validation"
        ],
        "required_skills": ["Python", "PyTorch", "Computer Vision", "Deep Learning", "Healthcare data", "Statistics"],
        "preferred_skills": ["MONAI", "DICOM", "Medical Imaging", "3D Segmentation"]
    },
    {
        "id": "edgeflow-iot-037",
        "title": "Embedded Linux & IoT Firmware Engineer",
        "company": "EdgeFlow Technologies",
        "location": "Phoenix, AZ",
        "work_mode": "On-site",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$110,000–$140,000",
        "description": "Develop robust, secure firmware and device drivers for industrial IoT telemetry gateways operating in harsh environmental conditions.",
        "responsibilities": [
            "Write C and C++ firmware for ARM Cortex processors and embedded Linux",
            "Implement low-power MQTT and CoAP wireless telemetry protocols with TLS",
            "Build secure over-the-air (OTA) dual-bank A/B firmware update routines",
            "Debug hardware timing issues using logic analyzers and oscilloscopes"
        ],
        "required_skills": ["C++", "C", "Linux", "Embedded Systems", "Git", "Network Security"],
        "preferred_skills": ["Yocto", "ARM", "MQTT", "Device Drivers"]
    },
    {
        "id": "statgen-biostat-038",
        "title": "Biostatistician & Clinical Trial Methodologist",
        "company": "StatGen Clinical Research",
        "location": "Raleigh, NC",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Mid-level",
        "salary_range": "$115,000–$145,000",
        "description": "Design statistical analysis plans (SAPs), calculate sample sizes, and perform survival analysis for Phase II/III clinical oncology studies.",
        "responsibilities": [
            "Author rigorous statistical analysis plans in compliance with FDA and ICH guidelines",
            "Perform Kaplan-Meier survival analysis and Cox proportional hazards regression in R",
            "Prepare automated clinical study reports and electronic Common Technical Documents (eCTD)",
            "Perform blinded data reviews and present efficacy interim reports to safety boards"
        ],
        "required_skills": ["R", "Statistics", "Healthcare data", "Time series", "Data Analysis", "Python"],
        "preferred_skills": ["Survival Analysis", "Clinical Trials", "SAS", "Biostatistics"]
    },
    {
        "id": "cloudnexus-architect-039",
        "title": "Principal Enterprise Cloud Architect",
        "company": "CloudNexus Consulting",
        "location": "Chicago, IL",
        "work_mode": "Hybrid",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$175,000–$225,000",
        "description": "Lead enterprise multi-cloud transformation roadmaps, migrating legacy financial core applications to scalable AWS and GCP cloud architectures.",
        "responsibilities": [
            "Author enterprise architecture blueprints spanning hybrid clouds and landing zones",
            "Conduct high-level architectural trade-off reviews and disaster recovery designs",
            "Advise Fortune 500 VP of Engineering on cloud FinOps and organizational scaling",
            "Direct technical proofs-of-concept for mission-critical migration workstreams"
        ],
        "required_skills": ["AWS", "Kubernetes", "Distributed Systems", "Cloud Security", "Terraform", "Microservices"],
        "preferred_skills": ["GCP", "Enterprise Architecture", "FinOps", "Disaster Recovery"]
    },
    {
        "id": "deepguard-ai-safety-040",
        "title": "AI Safety & Alignment Research Engineer",
        "company": "DeepGuard Safety Institute",
        "location": "San Francisco, CA",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "experience_level": "Senior",
        "salary_range": "$160,000–$210,000",
        "description": "Develop adversarial red-teaming, mechanistic interpretability probes, and unlearning algorithms to guarantee foundation models cannot be jailbroken.",
        "responsibilities": [
            "Construct automated adversarial red-teaming harnesses testing LLM jailbreaks",
            "Train probe classifiers to detect deceptive alignment and hidden reasoning states",
            "Implement machine unlearning techniques to remove hazardous domain knowledge",
            "Publish empirical safety benchmarks and release open-source defense tools"
        ],
        "required_skills": ["Python", "PyTorch", "Transformers", "LLM", "NLP", "Machine Learning"],
        "preferred_skills": ["Mechanistic Interpretability", "Red Teaming", "AI Safety", "RLHF"]
    }
]

def main():
    target_path = Path(__file__).parent / "expanded_jobs.json"
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(JOBS, f, indent=2, ensure_ascii=False)
    print(f"Successfully generated {len(JOBS)} structured job postings at {target_path}")

if __name__ == "__main__":
    main()
