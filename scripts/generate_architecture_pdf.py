"""
NEXARION Architecture Guide Generator: Docker & CI/CD Pipeline
Generates an in-depth, publication-grade 4-page PDF document explaining Docker and CI/CD.
"""

import os
import sys
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.pdfgen import canvas
import pypdf


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to compute total page count and draw running header/footer.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Don't draw header on cover page (Page 1)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(54, 750, "NEXARION ARCHITECTURE")
            self.setFont("Helvetica", 8)
            self.drawRightString(558, 750, "Docker & CI/CD Pipeline Deep Dive Guide")
            
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(54, 742, 558, 742)

        # Footer on all pages
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 558, 45)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(54, 32, "NEXARION Multi-Agent AI Code Review System • Production Engineering Manual")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 32, page_text)
            
        self.restoreState()


def build_pdf(filename="docs/Docker_and_CI_CD_Architecture_Guide.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    PRIMARY = colors.HexColor("#0F172A")    # Deep Navy
    SECONDARY = colors.HexColor("#1E293B")  # Dark Slate
    ACCENT_BLUE = colors.HexColor("#2563EB")# Royal Tech Blue
    TEXT_MAIN = colors.HexColor("#334155")  # Slate Gray
    BG_LIGHT = colors.HexColor("#F8FAFC")   # Light background
    BORDER_LIGHT = colors.HexColor("#E2E8F0")

    # Custom Typography Styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=26,
        textColor=PRIMARY,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=ACCENT_BLUE,
        spaceAfter=14
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=PRIMARY,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=7,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=TEXT_MAIN,
        spaceAfter=6
    )

    code_block_text = ParagraphStyle(
        "CodeBlockText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#F8FAFC")
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.white
    )

    table_body_style = ParagraphStyle(
        "TableBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=TEXT_MAIN
    )

    table_body_bold = ParagraphStyle(
        "TableBodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=PRIMARY
    )

    callout_text = ParagraphStyle(
        "CalloutText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#1E293B")
    )

    story = []

    def make_callout(text, bg_color="#EFF6FF", border_color="#3B82F6"):
        p = Paragraph(text, callout_text)
        t = Table([[p]], colWidths=[504])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg_color)),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor(border_color)),
            ('LINELEFT', (0,0), (0,0), 3, colors.HexColor(border_color)),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    def make_code_box(code_lines):
        content = [Paragraph(line.replace(" ", "&nbsp;"), code_block_text) for line in code_lines]
        t = Table([[content]], colWidths=[504])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0F172A")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#1E293B")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 1: EXECUTIVE SUMMARY & CORE ARCHITECTURAL PHILOSOPHY
    # ═════════════════════════════════════════════════════════════════════════
    
    story.append(Paragraph(
        "<font color='#2563EB'><b>NEXARION CORE ARCHITECTURAL SPECIFICATION</b></font>",
        ParagraphStyle("SubHeadBadge", fontName="Helvetica-Bold", fontSize=8.5, leading=11, spaceAfter=4)
    ))
    story.append(Paragraph("Understanding Docker & The CI/CD Pipeline", title_style))
    story.append(Paragraph("A Deep-Dive Engineering Manual on Containerization, Multi-Stage Builds, Automated Quality Gates, and Production Deployments", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceAfter=10))

    story.append(Paragraph("Executive Overview", h1_style))
    story.append(Paragraph(
        "Modern multi-agent AI systems combine complex frontend interfaces with heterogeneous backend architectures: "
        "Python runtimes, native C-libraries for syntax parsing, language models, database drivers, and frontend bundlers. "
        "Without strict infrastructure standardization and automated verification, such systems suffer from environment mismatches, "
        "flaky tests, deployment failures, and security vulnerabilities. In <b>NEXARION</b>, two foundational pillars guarantee engineering stability:",
        body_style
    ))

    # Two pillars table
    pillar_data = [
        [
            Paragraph("<b>Pillar 1: Containerization (Docker)</b>", table_header_style),
            Paragraph("<b>Pillar 2: Automated Verification (CI/CD)</b>", table_header_style)
        ],
        [
            Paragraph(
                "Packages the complete environment (Node.js build tools, Python 3.12, system dependencies like Git and Curl, "
                "static assets, and database drivers) into an immutable, self-contained unit that runs identically on any operating system.",
                table_body_style
            ),
            Paragraph(
                "A 5-stage automated quality gate in GitHub Actions that validates every commit with linters (Ruff), "
                "security scanners (Bandit), matrix integration tests (Pytest on Python 3.11/3.12 with PostgreSQL), frontend unit tests, "
                "and Docker build checks before merge.",
                table_body_style
            )
        ]
    ]
    pillar_table = Table(pillar_data, colWidths=[246, 246])
    pillar_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BACKGROUND', (0,1), (-1,1), BG_LIGHT),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 9),
        ('RIGHTPADDING', (0,0), (-1,-1), 9),
    ]))
    story.append(pillar_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("The Fundamental Problem Being Solved", h1_style))
    story.append(Paragraph(
        "<b>1. The 'It Works On My Machine' Dilemma:</b> A developer running Windows 11 with Node 18 and Python 3.11 might write code "
        "that fails completely when deployed to a Linux server running Python 3.12, due to differing line endings (CRLF vs LF), "
        "missing native libraries (e.g. <code>libpq</code> or <code>git</code>), or version discrepancies.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2. Human Verification Bottlenecks:</b> Manually verifying that 64 frontend test suites pass, 7 agent scenarios work, code formatting "
        "complies with PEP 8, and no secret keys or security bugs are committed is error-prone. Automated CI/CD replaces manual checks with deterministic guarantees.",
        body_style
    ))
    story.append(Paragraph(
        "<b>3. Zero-Downtime Deployment Confidence:</b> Because production code is packaged into an immutable Docker image verified by automated tests, "
        "deployments can happen multiple times a day without fear of breaking running production users.",
        body_style
    ))

    story.append(make_callout(
        "<b>Core Takeaway:</b> Docker eliminates the <i>runtime environment problem</i> by making the execution environment reproducible anywhere. "
        "CI/CD eliminates the <i>code quality & regression problem</i> by verifying every commit automatically before it can ever touch production.",
        bg_color="#F0FDF4", border_color="#10B981"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 2: DEEP DIVE INTO DOCKER IN NEXARION
    # ═════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("1. Deep-Dive: Docker Containerization Architecture", h1_style))
    story.append(Paragraph(
        "Docker packages software into lightweight, standalone executables called <b>containers</b>. "
        "Unlike heavy Virtual Machines (VMs) that emulate entire operating systems with separate kernels, containers share the host OS kernel "
        "while providing isolated user spaces for files, processes, and network interfaces.",
        body_style
    ))

    story.append(Paragraph("The Multi-Stage Build Pattern in NEXARION's Dockerfile", h2_style))
    story.append(Paragraph(
        "In modern web applications, the frontend (React/TypeScript) requires Node.js, npm, and build toolchains (Vite). "
        "However, in production, we only need static HTML, JavaScript, and CSS files! Having Node.js, npm, and 400MB of <code>node_modules</code> "
        "in production bloats image size and introduces security vulnerabilities. NEXARION solves this using a <b>Multi-Stage Dockerfile</b>:",
        body_style
    ))

    docker_steps = [
        "STAGE 1: FRONTEND COMPILATION (node:20-alpine)",
        "  1. WORKDIR /app/frontend",
        "  2. COPY frontend/package.json ./  --> Install npm dependencies",
        "  3. COPY frontend/ ./             --> Copy TypeScript & React source",
        "  4. RUN npm run build             --> Output static files to /app/frontend/dist",
        "",
        "STAGE 2: HARDENED PRODUCTION RUNTIME (python:3.12-slim-bookworm)",
        "  5. Install minimal system OS tools: git, curl, ca-certificates",
        "  6. Create dedicated non-root user: appuser (UID 1000, GID 1000)",
        "  7. COPY pyproject.toml README.md ./  --> Install Python backend packages",
        "  8. COPY src/ scripts/ ./             --> Copy backend source code",
        "  9. COPY --from=frontend-builder /app/frontend/dist ./frontend/dist",
        " 10. HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1",
        " 11. USER appuser                      --> Drop root privileges",
        " 12. CMD uvicorn code_review.web.app:app --host 0.0.0.0 --port 8000"
    ]
    story.append(make_code_box(docker_steps))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Why This Design is Superior:", h2_style))
    table_stages_data = [
        [
            Paragraph("<b>Metric / Concern</b>", table_header_style),
            Paragraph("<b>Single-Stage Build (Naive)</b>", table_header_style),
            Paragraph("<b>NEXARION Multi-Stage (Production)</b>", table_header_style)
        ],
        [
            Paragraph("<b>Final Image Size</b>", table_body_bold),
            Paragraph("~1.2 GB (includes Node, npm, build cache)", table_body_style),
            Paragraph("~280 MB (75% smaller; only Python & static dist)", table_body_style)
        ],
        [
            Paragraph("<b>Attack Surface</b>", table_body_bold),
            Paragraph("High (Node compilers & root user present)", table_body_style),
            Paragraph("Minimal (Only runtime Python + non-root <code>appuser</code>)", table_body_style)
        ],
        [
            Paragraph("<b>Build Caching</b>", table_body_bold),
            Paragraph("Rebuilds everything on any file edit", table_body_style),
            Paragraph("Re-uses dependency layers if <code>package.json</code> hasn't changed", table_body_style)
        ],
        [
            Paragraph("<b>Health Checks</b>", table_body_bold),
            Paragraph("No automated health checks", table_body_style),
            Paragraph("Native <code>HEALTHCHECK</code> probes <code>/health</code> every 30s", table_body_style)
        ]
    ]
    t_stages = Table(table_stages_data, colWidths=[110, 192, 202])
    t_stages.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(t_stages)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Local Multi-Service Orchestration: Docker Compose", h2_style))
    story.append(Paragraph(
        "NEXARION uses <b>Docker Compose</b> (<code>docker-compose.yml</code>) to orchestrate the application and PostgreSQL database with a single command: "
        "<br/>• <b>Postgres Service (<code>postgres:16-alpine</code>):</b> Runs isolated DB with healthcheck (<code>pg_isready</code>) and named volume (<code>postgres_data</code>). "
        "<br/>• <b>Backend Service:</b> Builds the <code>Dockerfile</code> and connects over bridge network using <code>depends_on: { postgres: { condition: service_healthy } }</code>.",
        body_style
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 3: DEEP DIVE INTO CI/CD PIPELINE
    # ═════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("2. Deep-Dive: The CI/CD Pipeline Architecture", h1_style))
    story.append(Paragraph(
        "<b>CI/CD</b> stands for <b>Continuous Integration</b> and <b>Continuous Delivery / Deployment</b>. "
        "Every time code is pushed or a PR is opened on GitHub, NEXARION's workflow (<code>.github/workflows/ci.yml</code>) "
        "spins up isolated cloud runners to deterministically validate the changes.",
        body_style
    ))

    story.append(Paragraph("The 5 Automated Quality Gates in NEXARION:", h2_style))

    cicd_table_data = [
        [
            Paragraph("<b>Job Name</b>", table_header_style),
            Paragraph("<b>Tool & Runner</b>", table_header_style),
            Paragraph("<b>Exact Purpose & Verification Performed</b>", table_header_style)
        ],
        [
            Paragraph("<b>1. Lint & Format</b>", table_body_bold),
            Paragraph("Ruff<br/>(Ubuntu Latest)", table_body_style),
            Paragraph("Enforces strict PEP 8 formatting rules and syntax standards. Fails immediately if there are unused imports, bad indentation, or undefined variables.", table_body_style)
        ],
        [
            Paragraph("<b>2. Security Scan</b>", table_body_bold),
            Paragraph("Bandit<br/>(Ubuntu Latest)", table_body_style),
            Paragraph("Performs Abstract Syntax Tree (AST) static security analysis. Checks for dangerous functions, SQL injection vectors, hardcoded tokens, and weak crypto.", table_body_style)
        ],
        [
            Paragraph("<b>3. Backend Tests</b>", table_body_bold),
            Paragraph("Pytest + Live Postgres<br/>(Python 3.11 & 3.12)", table_body_style),
            Paragraph("Spawns a real live PostgreSQL 16 container service inside GitHub Actions. Runs all unit, integration, and agent execution tests across Python versions.", table_body_style)
        ],
        [
            Paragraph("<b>4. Frontend Tests</b>", table_body_bold),
            Paragraph("Vite + TypeScript<br/>(Node.js 20)", table_body_style),
            Paragraph("Executes <code>npm run build</code> to check TypeScript types and compile Vite bundle. Runs 64 frontend test suites (modals, chats, routing, toggles).", table_body_style)
        ],
        [
            Paragraph("<b>5. Docker Build</b>", table_body_bold),
            Paragraph("Docker Buildx<br/>(GHA Caching)", table_body_style),
            Paragraph("Builds the entire multi-stage Dockerfile to verify that packaging succeeds and production images can be generated without broken dependencies.", table_body_style)
        ]
    ]
    t_cicd = Table(cicd_table_data, colWidths=[105, 114, 285])
    t_cicd.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(t_cicd)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Understanding Matrix Testing & Live Services in CI", h2_style))
    story.append(Paragraph(
        "Notice in Job 3 (<code>backend-tests</code>), NEXARION uses a <b>matrix strategy</b> and a <b>service container</b>:",
        body_style
    ))

    matrix_code = [
        "strategy:",
        "  matrix:",
        "    python-version: ['3.11', '3.12']   # Runs tests simultaneously on both versions!",
        "services:",
        "  postgres:",
        "    image: postgres:16-alpine           # Spins up actual PostgreSQL in memory",
        "    env:",
        "      POSTGRES_DB: nexarion_test_db",
        "    ports: ['5432:5432']",
        "    options: --health-cmd pg_isready --health-interval 10s"
    ]
    story.append(make_code_box(matrix_code))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>Why this matters:</b> Many teams test against SQLite in CI and deploy to PostgreSQL in production. "
        "This leads to subtle bugs (different JSON operators, SQL locking, and schema migrations). "
        "NEXARION tests against the <b>exact same PostgreSQL engine in CI</b> as used in production!",
        body_style
    ))

    story.append(make_callout(
        "<b>Concurrency Optimization:</b> NEXARION's workflow includes <code>concurrency: { group: ..., cancel-in-progress: true }</code>. "
        "If a developer pushes three commits in rapid succession, the pipeline immediately cancels the older builds to save runner minutes "
        "and report results on the latest commit faster.",
        bg_color="#FEF3C7", border_color="#F59E0B"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 4: CLOUD DEPLOYMENT & COMPLETE LIFECYCLE
    # ═════════════════════════════════════════════════════════════════════════

    story.append(Paragraph("3. End-to-End Production Deployment Lifecycle", h1_style))
    story.append(Paragraph(
        "Here is the exact lifecycle of how a code commit travels from your machine through Docker and CI/CD to live production:",
        body_style
    ))

    lifecycle_steps = [
        "1. LOCAL CODE -> git commit -> git push origin feature-branch",
        "2. GITHUB ACTIONS CI GATEWAY TRIGGERS AUTOMATICALLY:",
        "   - Ruff lints & formats  --> Bandit scans security  --> Pytest tests on Postgres",
        "   - TypeScript compiles    --> Node runs 64 UI tests --> Docker Buildx verifies build",
        "   - If ANY check fails: Merge is BLOCKED. Flawed code never touches production.",
        "3. PULL REQUEST APPROVED & MERGED INTO MAIN",
        "4. CONTINUOUS DELIVERY (CD) WEBHOOK TRIGGER:",
        "   - Render detects merge -> reads render.yaml -> builds Docker image in cloud.",
        "   - Render boots new container -> verifies /health probe -> switches traffic smoothly.",
        "   - Old container is decommissioned. Zero downtime experienced by users."
    ]
    story.append(make_code_box(lifecycle_steps))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Production Cloud Ecosystem Breakdown", h2_style))

    cloud_table_data = [
        [
            Paragraph("<b>Platform</b>", table_header_style),
            Paragraph("<b>Component</b>", table_header_style),
            Paragraph("<b>Role & Integration with Docker / CI</b>", table_header_style)
        ],
        [
            Paragraph("<b>Render</b>", table_body_bold),
            Paragraph("FastAPI Backend & Container Runtime", table_body_style),
            Paragraph("Reads <code>render.yaml</code>, builds <code>Dockerfile</code> on every push to <code>main</code>, and hosts container on Port 8000.", table_body_style)
        ],
        [
            Paragraph("<b>Neon Tech</b>", table_body_bold),
            Paragraph("Serverless PostgreSQL 16 Database", table_body_style),
            Paragraph("Provides persistent relational database storage with connection pooling URL (<code>postgresql+psycopg://...</code>).", table_body_style)
        ],
        [
            Paragraph("<b>Vercel</b>", table_body_bold),
            Paragraph("Decoupled React Edge Frontend (Optional)", table_body_style),
            Paragraph("Connects via <code>BACKEND_URL</code> environment variable, routing API calls and WebSockets to the Render container.", table_body_style)
        ],
        [
            Paragraph("<b>NVIDIA NIM</b>", table_body_bold),
            Paragraph("Cloud AI Inference (Nemotron)", table_body_style),
            Paragraph("Container injects <code>NVIDIA_API_KEY</code> to orchestrate multi-agent LLM analysis without hardcoding keys.", table_body_style)
        ]
    ]
    t_cloud = Table(cloud_table_data, colWidths=[90, 140, 274])
    t_cloud.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(t_cloud)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Developer Cheatsheet: Commands You Can Run Locally", h2_style))
    story.append(Paragraph(
        "You can run the exact same verification commands locally that the automated CI/CD pipeline runs:",
        body_style
    ))
    
    dev_cmds = [
        "# 1. Run linting and code formatting checks locally:",
        "ruff check . && ruff format --check .",
        "# 2. Run security static analysis locally:",
        "bandit -r src -ll",
        "# 3. Run backend unit & integration tests:",
        "pytest --cov=code_review",
        "# 4. Run frontend compilation & test suite:",
        "npm --prefix frontend run build && npm --prefix frontend test",
        "# 5. Build and launch the entire stack in Docker locally:",
        "docker compose up --build -d"
    ]
    story.append(make_code_box(dev_cmds))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    shutil.copy(filename, "Docker_and_CI_CD_Architecture_Guide.pdf")
    print(f"Successfully generated PDF: {filename} and copied to root.")


if __name__ == "__main__":
    out_path = "docs/Docker_and_CI_CD_Architecture_Guide.pdf"
    if len(sys.argv) > 1:
        out_path = sys.argv[1]
    build_pdf(out_path)
