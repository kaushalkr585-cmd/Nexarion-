"""
NEXARION Master Engineering Curriculum Guide Generator
Generates an in-depth, publication-grade, beginner-friendly PDF document
explaining the 10 core engineering phases required for the Nexarion codebase.
"""

import os
import sys
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas
import pypdf


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to compute total page count and draw running header and footer.
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
        
        # Header on pages 2+
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(45, 755, "NEXARION MASTER CURRICULUM")
            self.setFont("Helvetica", 8)
            self.drawRightString(567, 755, "Backend Engineering & Multi-Agent Architecture Guide")
            
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(45, 747, 567, 747)

        # Footer on all pages
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(45, 38, 567, 38)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(45, 26, "NEXARION Multi-Agent AI Code Review System • Master Engineering Curriculum")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(567, 26, page_text)
            
        self.restoreState()


def build_pdf(filename="docs/Nexarion_Master_Engineering_Curriculum_Guide.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=45,
        rightMargin=45,
        topMargin=48,
        bottomMargin=48
    )

    styles = getSampleStyleSheet()

    # Color Palette
    PRIMARY = colors.HexColor("#0F172A")     # Deep Navy
    SECONDARY = colors.HexColor("#1E293B")   # Dark Slate
    ACCENT_BLUE = colors.HexColor("#2563EB") # Tech Blue
    ACCENT_GREEN = colors.HexColor("#059669")# Emerald
    ACCENT_PURPLE = colors.HexColor("#7C3AED")# Violet
    TEXT_MAIN = colors.HexColor("#334155")   # Slate Body
    TEXT_MUTED = colors.HexColor("#64748B")  # Muted Text
    BG_LIGHT = colors.HexColor("#F8FAFC")    # Slate 50
    BORDER_LIGHT = colors.HexColor("#E2E8F0")

    # Typography
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=PRIMARY,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=ACCENT_BLUE,
        spaceAfter=10
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=16,
        textColor=PRIMARY,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13.5,
        textColor=SECONDARY,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_MAIN,
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        "BulletItem",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=TEXT_MAIN,
        leftIndent=12,
        spaceAfter=3
    )

    code_block_text = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.2,
        leading=9.8,
        textColor=colors.HexColor("#F8FAFC")
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=colors.white
    )

    table_body_style = ParagraphStyle(
        "TableBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.5,
        textColor=TEXT_MAIN
    )

    table_body_bold = ParagraphStyle(
        "TableBodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=10.5,
        textColor=PRIMARY
    )

    callout_title_style = ParagraphStyle(
        "CalloutTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=PRIMARY,
        spaceAfter=2
    )

    callout_text = ParagraphStyle(
        "CalloutText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#1E293B")
    )

    story = []

    def make_callout(title, text, bg_color="#EFF6FF", border_color="#3B82F6", width=522):
        elems = []
        if title:
            elems.append(Paragraph(f"<b>{title}</b>", callout_title_style))
        elems.append(Paragraph(text, callout_text))
        t = Table([[elems]], colWidths=[width])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg_color)),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor(border_color)),
            ('LINELEFT', (0,0), (0,0), 3, colors.HexColor(border_color)),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 9),
            ('RIGHTPADDING', (0,0), (-1,-1), 9),
        ]))
        return t

    def make_code_box(code_lines, width=522):
        content = [Paragraph(line.replace(" ", "&nbsp;").replace("<", "&lt;").replace(">", "&gt;"), code_block_text) for line in code_lines]
        t = Table([[content]], colWidths=[width])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0F172A")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#1E293B")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        return t

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 1: TITLE, EXECUTIVE OVERVIEW & COMPLETE CURRICULUM ROADMAP
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("<font color='#2563EB'><b>NEXARION MASTER CURRICULUM & ENGINEERING GUIDE</b></font>", 
                           ParagraphStyle("Badge", fontName="Helvetica-Bold", fontSize=8.5, leading=11, spaceAfter=3)))
    story.append(Paragraph("FastAPI, Python & Multi-Agent Architecture", title_style))
    story.append(Paragraph("A Complete, Deep-Dive Learning Blueprint Specifically Filtered & Explained for the NEXARION Codebase", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph("Executive Summary & Project Context", h1_style))
    story.append(Paragraph(
        "<b>NEXARION</b> is a production-grade Multi-Agent AI Code Review System. It combines an asynchronous <b>FastAPI</b> backend "
        "with an intelligent multi-agent pipeline (AST parsing, Ruff, Bandit, and LLM reasoning) and a real-time <b>React</b> streaming interface. "
        "When mastering backend engineering for this system, you do <b>not</b> need to learn every generic Python/FastAPI concept. "
        "Topics like MongoDB, Celery, Jinja HTML templates, or WebSockets are completely absent here. Instead, this guide provides a deep, "
        "easy-to-understand explanation of the exact architectural pillars that power Nexarion.",
        body_style
    ))

    # Architecture Overview Table
    arch_summary_data = [
        [Paragraph("<b>Architectural Layer</b>", table_header_style), Paragraph("<b>Core Technologies</b>", table_header_style), Paragraph("<b>Function in NEXARION</b>", table_header_style)],
        [Paragraph("<b>1. Multi-Agent Engine</b>", table_body_bold), Paragraph("Python OOP, AST, Subprocess, Linters", table_body_style), Paragraph("Parses Python code trees; runs deterministic security (Bandit) & quality (Ruff) checks.", table_body_style)],
        [Paragraph("<b>2. API & Routing Layer</b>", table_body_bold), Paragraph("FastAPI, APIRouter, ASGI (Uvicorn)", table_body_style), Paragraph("Exposes REST endpoints, validates payloads with Pydantic, and manages dependency injection.", table_body_style)],
        [Paragraph("<b>3. Real-Time Streaming</b>", table_body_bold), Paragraph("Server-Sent Events (SSE), Generators", table_body_style), Paragraph("Streams tokens from LLMs (NVIDIA NIM / Ollama) directly into the React chat workspace.", table_body_style)],
        [Paragraph("<b>4. Persistence & Auth</b>", table_body_bold), Paragraph("SQLAlchemy ORM, SQLite/PostgreSQL, JWT", table_body_style), Paragraph("Stores reviews, conversations, messages, and audits; secures endpoints via Bearer tokens.", table_body_style)],
        [Paragraph("<b>5. Quality & Operations</b>", table_body_bold), Paragraph("Pytest, TestClient, Docker, GitHub Actions", table_body_style), Paragraph("Guarantees code health, containerizes environments, and automates testing in CI/CD.", table_body_style)],
    ]
    t_arch = Table(arch_summary_data, colWidths=[110, 150, 262])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Curriculum Priority Matrix: Must-Learn vs. Skip", h1_style))
    story.append(Paragraph(
        "To maximize learning efficiency, this guide categorizes the standard FastAPI curriculum into three precise tiers:",
        body_style
    ))

    t_matrix_data = [
        [Paragraph("<b>Priority Level</b>", table_header_style), Paragraph("<b>Included Topics</b>", table_header_style), Paragraph("<b>Why It Matters / Guidance</b>", table_header_style)],
        [
            Paragraph("<font color='#059669'><b>TIER 1:<br/>Absolute Must</b></font>", table_body_bold),
            Paragraph("• Python OOP & Inheritance<br/>• Python <code>ast</code> Module<br/>• Pydantic v2 & Field Validation<br/>• FastAPI Routing & <code>Depends()</code><br/>• <code>StreamingResponse</code> (SSE)<br/>• SQLAlchemy ORM & Sessions<br/>• JWT Authentication & Hashing<br/>• Pytest & <code>TestClient</code>", table_body_style),
            Paragraph("These form 90% of daily Nexarion development. Every route, agent, database model, and streaming chat relies on these core concepts.", table_body_style)
        ],
        [
            Paragraph("<font color='#2563EB'><b>TIER 2:<br/>Secondary / Ops</b></font>", table_body_bold),
            Paragraph("• Pydantic Settings & <code>.env</code><br/>• Lifespan Handlers<br/>• Structured Trace Logging<br/>• Docker & Multi-stage Builds<br/>• CI/CD GitHub Actions Workflows", table_body_style),
            Paragraph("Crucial for packaging, deployment, configuration, and production stability. You touch these when standing up the system or debugging infrastructure.", table_body_style)
        ],
        [
            Paragraph("<font color='#DC2626'><b>TIER 3:<br/>Safe to Skip</b></font>", table_body_bold),
            Paragraph("• MongoDB / Motor (NoSQL)<br/>• WebSockets (uses SSE instead)<br/>• Celery & Redis Queues<br/>• HTML Templates / Jinja2<br/>• Cookies & Form Data Login", table_body_style),
            Paragraph("Nexarion uses pure JSON REST APIs, relational SQL databases, in-memory caching, and standard HTTP/2 streaming. Do not waste time studying these.", table_body_style)
        ]
    ]
    t_mat = Table(t_matrix_data, colWidths=[90, 180, 252])
    t_mat.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_mat)

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 2: PHASE 1 — PYTHON PREREQUISITES FOR MULTI-AGENT SYSTEMS
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 1: Python Prerequisites for Multi-Agent Systems", h1_style))
    story.append(Paragraph(
        "Building a multi-agent system requires strong foundations in Object-Oriented Programming (OOP), code parsing, and type safety. "
        "Here is exactly how these concepts operate inside Nexarion.",
        body_style
    ))

    story.append(Paragraph("1. Object-Oriented Programming & The Agent Hierarchy", h2_style))
    story.append(Paragraph(
        "<b>Analogy:</b> Think of a hospital. All doctors undergo common medical training, but a cardiologist and a neurologist specialize in different organs. "
        "In Nexarion, every reviewer is an Agent. Rather than rewriting boilerplate execution logic, all agents inherit from a single abstract parent class: <code>BaseAgent</code>.",
        body_style
    ))

    code_oop = [
        "# src/code_review/agents/base.py",
        "class BaseAgent(ABC):",
        "    def __init__(self, name: str, enabled: bool = True):",
        "        self.name = name",
        "        self.enabled = enabled",
        "",
        "    @abstractmethod",
        "    def review(self, diff: str, files: list[str]) -> list[Finding]:",
        "        \"\"\"Every child agent MUST implement its own review logic.\"\"\"",
        "        pass",
        "",
        "# src/code_review/agents/ast_agent.py (Child Class)",
        "class ASTAgent(BaseAgent):",
        "    def review(self, diff: str, files: list[str]) -> list[Finding]:",
        "        # Concrete AST inspection logic goes here",
        "        return [Finding(rule='SYN001', message='Syntax issue detected')]"
    ]
    story.append(make_code_box(code_oop))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Abstract Syntax Trees (AST): Inspecting Code Without Running It", h2_style))
    story.append(Paragraph(
        "<b>What is an AST?</b> Python source code is just raw text. An <i>Abstract Syntax Tree</i> breaks text into a structured tree of tokens "
        "(functions, variables, loops, conditionals).<br/>"
        "<b>Why it matters in Nexarion:</b> If a user submits malicious code (e.g. <code>os.system('rm -rf /')</code>), we cannot run the code to test it! "
        "The <code>ast</code> module scans the tree safely in memory. If it discovers a dangerous node like <code>Call(func=Name(id='eval'))</code>, "
        "it flags a security risk immediately.",
        body_style
    ))

    code_ast = [
        "import ast",
        "code_snippet = 'def calculate(a, b): return eval(a + b)'",
        "tree = ast.parse(code_snippet) # Generates syntax tree in memory",
        "for node in ast.walk(tree):",
        "    if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'eval':",
        "        print('CRITICAL: Dynamic eval() execution detected on line', node.lineno)"
    ]
    story.append(make_code_box(code_ast))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Modern Python Type Hints (`typing`)", h2_style))
    story.append(Paragraph(
        "Python 3.12 introduces concise union syntax (<code>str | None</code> instead of <code>Optional[str]</code>). "
        "FastAPI uses these type annotations to automatically validate client inputs and generate OpenAPI documentation. "
        "If an endpoint specifies <code>user_id: str</code>, sending an integer or missing parameter triggers an immediate 422 Unprocessable Entity error.",
        body_style
    ))

    story.append(Paragraph("4. Defensive Exception Handling & The Normalizer Pattern", h2_style))
    story.append(Paragraph(
        "When an AI model is overloaded or times out, raw Python tracebacks (e.g., <code>ConnectionResetError: [Errno 104]</code>) "
        "must never leak to the frontend. In Nexarion, <code>error_normalizer.py</code> intercepts all unexpected runtime exceptions and maps them "
        "to polite, user-friendly messages with a clear <code>retryable: bool</code> flag.",
        body_style
    ))
    story.append(make_callout(
        "Core Rule for Nexarion Agents",
        "Never run untrusted user code directly with <code>exec()</code> or <code>eval()</code>. Always inspect using <code>ast.walk()</code> "
        "or execute sandboxed linters via <code>subprocess.run(['ruff', 'check', ...], capture_output=True)</code>.",
        bg_color="#ECFDF5", border_color="#10B981"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 3: PHASE 2 & 3 — FASTAPI FUNDAMENTALS & PYDANTIC V2
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 2 & 3: FastAPI Architecture & Pydantic Data Validation", h1_style))
    story.append(Paragraph(
        "FastAPI is an asynchronous web framework built on top of Starlette and Pydantic. It provides automatic validation, "
        "high concurrency, and integrated OpenAPI specs.",
        body_style
    ))

    story.append(Paragraph("1. Understanding ASGI vs WSGI", h2_style))
    story.append(Paragraph(
        "Older Python frameworks like Django and Flask traditionally used <b>WSGI</b> (Web Server Gateway Interface), where each incoming request "
        "blocks an entire operating system thread. If a request waits 15 seconds for an LLM to generate tokens, the server worker is completely frozen.<br/>"
        "FastAPI uses <b>ASGI</b> (Asynchronous Server Gateway Interface) powered by <b>Uvicorn</b>. Using Python's event loop, ASGI handles "
        "thousands of active streaming connections concurrently on a single process without blocking.",
        body_style
    ))

    story.append(Paragraph("2. Anatomy of a FastAPI Path Operation", h2_style))
    story.append(Paragraph(
        "FastAPI routes consist of four essential building blocks:",
        body_style
    ))
    story.append(Paragraph("• <b>Path Parameter:</b> Identifies a specific resource (e.g. <code>/api/conversations/{conversation_id}</code>).", bullet_style))
    story.append(Paragraph("• <b>Query Parameter:</b> Filters or paginates lists (e.g. <code>?include_archived=true&page=2</code>).", bullet_style))
    story.append(Paragraph("• <b>Request Body:</b> JSON payload validated through a Pydantic schema.", bullet_style))
    story.append(Paragraph("• <b>Response Model:</b> Filters outgoing data so internal secrets or database hashes are never exposed.", bullet_style))

    story.append(Spacer(1, 2))
    story.append(Paragraph("3. Pydantic v2: The Data Armor of Nexarion", h2_style))
    story.append(Paragraph(
        "<b>Analogy:</b> Pydantic is like the passport control bouncer. Every piece of data entering or leaving the backend must show valid identification.<br/>"
        "In Nexarion's <code>schemas.py</code>, Pydantic schemas enforce type safety, trim whitespace, and guard against malformed data:",
        body_style
    ))

    code_pydantic = [
        "# src/code_review/web/schemas.py",
        "from pydantic import BaseModel, Field, field_validator",
        "",
        "class MessageCreateRequest(BaseModel):",
        "    content: str = Field(..., min_length=1, max_length=10000, description='User prompt')",
        "    provider: str | None = Field(default='llm', description='AI Provider: llm or ollama')",
        "    model: str | None = None",
        "",
        "    @field_validator('provider')",
        "    @classmethod",
        "    def sanitize_provider(cls, val: str | None) -> str:",
        "        if not val or val.lower().strip() not in ('llm', 'nvidia', 'ollama'):",
        "            return 'llm'  # Safe automatic fallback",
        "        return val.lower().strip()"
    ]
    story.append(make_code_box(code_pydantic))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Request vs. Response Model Separation", h2_style))
    story.append(Paragraph(
        "A critical security rule in FastAPI is <b>never returning raw SQLAlchemy models directly</b>. "
        "A database <code>UserRecord</code> contains <code>password_hash</code>. If serialized directly, the client could see hashed passwords! "
        "Instead, Nexarion defines a separate <code>UserResponse</code> schema containing only public fields (`id`, `name`, `email`, `created_at`).",
        body_style
    ))
    story.append(make_callout(
        "Serialization Note: model_dump()",
        "In Pydantic v2, use <code>model.model_dump()</code> to convert a schema into a Python dictionary, and <code>model.model_dump_json()</code> "
        "to produce a JSON string. (The legacy v1 <code>.dict()</code> method is deprecated).",
        bg_color="#EFF6FF", border_color="#3B82F6"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 4: PHASE 4 & 5 — REAL-TIME STREAMING (SSE) & DEPENDENCY INJECTION
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 4 & 5: Real-Time Streaming & Dependency Injection", h1_style))
    story.append(Paragraph(
        "Nexarion's chat experience relies on two core FastAPI superpowers: <b>StreamingResponse (SSE)</b> for real-time AI replies, "
        "and <b>Depends()</b> for clean, modular dependency injection.",
        body_style
    ))

    story.append(Paragraph("1. Server-Sent Events (SSE) via `StreamingResponse`", h2_style))
    story.append(Paragraph(
        "<b>Why SSE instead of WebSockets?</b> WebSockets are bidirectional and stateful, requiring complex connection handshakes and ping/pong heartbeats. "
        "AI text generation is fundamentally <i>one-directional</i>: the user sends a prompt, and the server streams tokens back. "
        "SSE operates over standard HTTP/2, supports automatic browser reconnection, and works seamlessly through proxies and firewalls.",
        body_style
    ))

    code_sse = [
        "# src/code_review/web/routes/conversation_routes.py",
        "from fastapi.responses import StreamingResponse",
        "",
        "@router.post('/api/conversations/stream')",
        "def create_conversation_stream(payload: ConversationCreateRequest, ...):",
        "    def event_generator():",
        "        # 1. Send initialization metadata event",
        "        yield f'event: init\\ndata: {json.dumps({\"id\": conv.id})}\\n\\n'",
        "",
        "        # 2. Stream tokens from the model chunk-by-chunk",
        "        for token in client.stream_chat(prompt):",
        "            yield f'event: token\\ndata: {json.dumps({\"chunk\": token})}\\n\\n'",
        "",
        "        # 3. Finalize and persist assistant response to the database",
        "        yield f'event: done\\ndata: {json.dumps({\"status\": \"complete\"})}\\n\\n'",
        "",
        "    return StreamingResponse(event_generator(), media_type='text/event-stream')"
    ]
    story.append(make_code_box(code_sse))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Dependency Injection: The `Depends()` Magic", h2_style))
    story.append(Paragraph(
        "<b>Analogy:</b> Imagine dining at a luxury restaurant. When you order pasta, you do not visit the kitchen, boil water, or clean dishes. "
        "The kitchen delivers the prepared dish to your table. In FastAPI, <code>Depends()</code> does the exact same thing for database sessions "
        "and user credentials.",
        body_style
    ))

    code_depends = [
        "# Database session dependency",
        "def get_db() -> Iterator[Session]:",
        "    db = SessionLocal()",
        "    try:",
        "        yield db       # Hand session to route",
        "    finally:",
        "        db.close()     # Automatically closed when request finishes!",
        "",
        "# Using dependencies in route handlers",
        "@router.get('/api/reviews')",
        "def list_reviews(",
        "    db: Annotated[Session, Depends(get_db)],                     # Injected DB",
        "    user: Annotated[UserRecord, Depends(get_current_user)]       # Injected Auth",
        "):",
        "    return db.query(ReviewRecord).filter_by(user_id=user.id).all()"
    ]
    story.append(make_code_box(code_depends))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Cross-Origin Resource Sharing (CORS)", h2_style))
    story.append(Paragraph(
        "Because the React frontend runs on <code>http://localhost:5173</code> while FastAPI runs on <code>http://localhost:8000</code>, "
        "browsers block API requests by default for security. Nexarion attaches <code>CORSMiddleware</code> in <code>app.py</code> with allowed headers, "
        "methods, and credentials, allowing the web app to communicate securely.",
        body_style
    ))
    story.append(make_callout(
        "Critical SSE Gotcha",
        "Always format SSE data lines with double newlines: <code>yield f'event: token\\ndata: {json_str}\\n\\n'</code>. "
        "If the trailing <code>\\n\\n</code> is missing, browsers will buffer the chunks indefinitely instead of rendering them in real time!",
        bg_color="#FEF2F2", border_color="#EF4444"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 5: PHASE 6 — DATABASE INTEGRATION WITH SQLALCHEMY ORM
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 6: Database Integration with SQLAlchemy ORM", h1_style))
    story.append(Paragraph(
        "Nexarion relies on <b>SQLAlchemy 2.0</b>, the industry-standard Object-Relational Mapping (ORM) library for Python. "
        "An ORM allows developers to interact with database tables as standard Python classes, eliminating the risk of raw SQL injection vulnerabilities.",
        body_style
    ))

    story.append(Paragraph("1. Relational Data Models & Foreign Key Cascades", h2_style))
    story.append(Paragraph(
        "Nexarion organizes its persistence into clean, relational models located in <code>models.py</code>:",
        body_style
    ))

    code_orm = [
        "# src/code_review/web/models.py",
        "class ConversationRecord(Base):",
        "    __tablename__ = 'conversations'",
        "",
        "    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))",
        "    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=True)",
        "    title = Column(String(255), default='New Conversation')",
        "    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))",
        "",
        "    # One-to-Many Relationship with Messages",
        "    messages = relationship('MessageRecord', back_populates='conversation', cascade='all, delete-orphan')",
        "",
        "class MessageRecord(Base):",
        "    __tablename__ = 'messages'",
        "    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))",
        "    conversation_id = Column(String(36), ForeignKey('conversations.id', ondelete='CASCADE'))",
        "    role = Column(String(20), nullable=False)  # 'user' | 'assistant'",
        "    content = Column(Text, nullable=False)"
    ]
    story.append(make_code_box(code_orm))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. The SQLAlchemy Unit of Work Lifecycle", h2_style))
    story.append(Paragraph(
        "Understanding database transaction state is essential to prevent ghost records and database locks:",
        body_style
    ))
    story.append(Paragraph("• <b>`db.add(instance)`:</b> Stages the Python object in the local session memory.", bullet_style))
    story.append(Paragraph("• <b>`db.flush()`:</b> Sends SQL INSERT/UPDATE commands to the database engine to generate IDs, but does NOT finalize the transaction yet.", bullet_style))
    story.append(Paragraph("• <b>`db.commit()`:</b> Permanently writes all staged changes to disk and ends the transaction.", bullet_style))
    story.append(Paragraph("• <b>`db.rollback()`:</b> Reverts all uncommitted changes if an error occurred during execution.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("3. SQLite vs. PostgreSQL Deployment Strategy", h2_style))
    story.append(Paragraph(
        "Nexarion is architected to run seamlessly on both SQLite and PostgreSQL without altering business logic:",
        body_style
    ))

    t_db_comp = [
        [Paragraph("<b>Feature</b>", table_header_style), Paragraph("<b>SQLite (Local Development)</b>", table_header_style), Paragraph("<b>PostgreSQL (Production Cloud)</b>", table_header_style)],
        [Paragraph("<b>Storage</b>", table_body_bold), Paragraph("Single local file (<code>code_review.db</code>)", table_body_style), Paragraph("Dedicated server / managed database container", table_body_style)],
        [Paragraph("<b>Setup</b>", table_body_bold), Paragraph("Zero configuration; built into standard Python", table_body_style), Paragraph("Requires host, port, user credentials via <code>DATABASE_URL</code>", table_body_style)],
        [Paragraph("<b>Concurrency</b>", table_body_bold), Paragraph("Single-writer lock; ideal for local development & tests", table_body_style), Paragraph("High multi-user concurrency with row-level locking", table_body_style)],
    ]
    t_db = Table(t_db_comp, colWidths=[90, 216, 216])
    t_db.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_db)
    story.append(Spacer(1, 4))
    story.append(make_callout(
        "Cascade Deletes in Action",
        "Because <code>cascade='all, delete-orphan'</code> is set on <code>ConversationRecord.messages</code>, deleting a conversation "
        "automatically deletes all 50+ associated chat messages in a single atomic SQL transaction. No dangling orphaned data!",
        bg_color="#ECFDF5", border_color="#10B981"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 6: PHASE 7 — AUTHENTICATION, JWT & SECURITY
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 7: Authentication, JWT & Security", h1_style))
    story.append(Paragraph(
        "Authentication confirms <i>who you are</i>, while authorization determines <i>what you can access</i>. "
        "Nexarion implements a stateless, token-based security architecture.",
        body_style
    ))

    story.append(Paragraph("1. Password Hashing with Bcrypt & Salt", h2_style))
    story.append(Paragraph(
        "<b>Why can't we store passwords in plain text?</b> If a database backup is leaked, all user accounts are compromised immediately.<br/>"
        "Nexarion hashes passwords using <b>Bcrypt</b>. Bcrypt automatically applies a random <i>salt</i> (cryptographic noise) and runs hundreds of "
        "computation rounds. This makes rainbow-table lookups and brute-force attacks computationally impossible.",
        body_style
    ))

    code_bcrypt = [
        "from passlib.context import CryptContext",
        "pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')",
        "",
        "# During Sign-up:",
        "hashed = pwd_context.hash('SecretPassword123')",
        "# Result: $2b$12$e8kPqL8d9w9Fj... (One-way hash stored in DB)",
        "",
        "# During Login:",
        "is_valid = pwd_context.verify('SecretPassword123', hashed) # True"
    ]
    story.append(make_code_box(code_bcrypt))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. JSON Web Tokens (JWT) Architecture", h2_style))
    story.append(Paragraph(
        "<b>How Stateless Auth Works:</b> After a user logs in, the backend issues an encrypted, signed string called a <b>JWT</b>. "
        "The server does not need to store the session in memory. The token itself contains the user ID and expiration timestamp, signed by the server's secret key.",
        body_style
    ))

    jwt_structure = [
        [Paragraph("<b>JWT Component</b>", table_header_style), Paragraph("<b>Example Content</b>", table_header_style), Paragraph("<b>Description</b>", table_header_style)],
        [Paragraph("<b>1. Header</b>", table_body_bold), Paragraph("<code>{\"alg\": \"HS256\", \"typ\": \"JWT\"}</code>", table_body_style), Paragraph("Specifies the hashing algorithm used.", table_body_style)],
        [Paragraph("<b>2. Payload</b>", table_body_bold), Paragraph("<code>{\"sub\": \"user-123\", \"exp\": 1731000000}</code>", table_body_style), Paragraph("Stores identity and expiration (never store passwords here!).", table_body_style)],
        [Paragraph("<b>3. Signature</b>", table_body_bold), Paragraph("<code>HMACSHA256(header + payload, SECRET)</code>", table_body_style), Paragraph("Guarantees the client did not tamper with the data.", table_body_style)],
    ]
    t_jwt = Table(jwt_structure, colWidths=[90, 216, 216])
    t_jwt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_jwt)
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. The Auth Dependency Pipeline", h2_style))
    story.append(Paragraph(
        "In <code>auth.py</code>, Nexarion implements <code>get_current_user</code> using FastAPI's <code>OAuth2PasswordBearer</code>. "
        "When an incoming HTTP request contains <code>Authorization: Bearer &lt;token&gt;</code>, this dependency automatically extracts the token, "
        "decodes it with the secret key, fetches the matching user record, and attaches it to the route.",
        body_style
    ))

    code_auth_dep = [
        "# src/code_review/web/auth.py",
        "def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):",
        "    try:",
        "        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])",
        "        user_id = payload.get('sub')",
        "    except JWTError:",
        "        raise HTTPException(status_code=401, detail='Invalid or expired token')",
        "    user = db.query(UserRecord).filter_by(id=user_id).first()",
        "    if not user:",
        "        raise HTTPException(status_code=401, detail='User account not found')",
        "    return user"
    ]
    story.append(make_code_box(code_auth_dep))
    story.append(Spacer(1, 4))
    story.append(make_callout(
        "Guest Mode Support",
        "Nexarion also features <code>get_current_user_optional</code>. If a user is not logged in, the route does not throw an error; "
        "it simply returns <code>None</code>, allowing guest users to test the code reviewer without forcing an immediate sign-up.",
        bg_color="#EFF6FF", border_color="#3B82F6"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 7: PHASE 8 — ADVANCED FASTAPI & SYSTEM OBSERVABILITY
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 8: Advanced FastAPI & System Observability", h1_style))
    story.append(Paragraph(
        "Production AI applications require advanced lifecycle hooks, telemetry, and structured performance tracing. "
        "Here are the advanced engineering patterns embedded in Nexarion.",
        body_style
    ))

    story.append(Paragraph("1. Lifespan Management (`@asynccontextmanager`)", h2_style))
    story.append(Paragraph(
        "Modern FastAPI applications manage startup and shutdown routines through a <b>Lifespan context manager</b> rather than deprecated "
        "<code>@app.on_event('startup')</code> hooks. On startup, Nexarion validates database schemas and verifies connectivity to cloud inference APIs.",
        body_style
    ))

    code_lifespan = [
        "# src/code_review/web/app.py",
        "@asynccontextmanager",
        "async def lifespan(app: FastAPI):",
        "    # [STARTUP] Run DB table creations and warm up LLM clients",
        "    logger.info('Initializing Nexarion multi-agent services...')",
        "    init_db()",
        "    yield",
        "    # [SHUTDOWN] Close thread pools and flush remaining logs",
        "    logger.info('Shutting down Nexarion gracefully.')",
        "",
        "app = FastAPI(title='Nexarion API', lifespan=lifespan)"
    ]
    story.append(make_code_box(code_lifespan))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Performance Telemetry & TTFT (Time To First Token)", h2_style))
    story.append(Paragraph(
        "User experience in AI products depends on immediate responsiveness. Nexarion measures three key timing metrics for every review and chat stream:",
        body_style
    ))
    story.append(Paragraph("• <b>TTFT (Time To First Token):</b> The duration from when the user hits 'Send' until the first streamed character reaches the UI (typically &lt; 1.5s).", bullet_style))
    story.append(Paragraph("• <b>Gen Time (Generation Duration):</b> The total time the LLM spent producing the full completion.", bullet_style))
    story.append(Paragraph("• <b>DB Time (Commit Latency):</b> How quickly the final message and memory embeddings were persisted to disk.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("3. Structured Tracing with Unique Trace IDs", h2_style))
    story.append(Paragraph(
        "When hundreds of users send concurrent chat requests, server logs can become an unreadable tangle. "
        "Nexarion tags every streaming session with a unique UUID (e.g., <code>trace-8f1a2b3c</code>). Every log line output during that stream prints "
        "the trace identifier, making root-cause diagnosis effortless:",
        body_style
    ))

    code_trace = [
        "[INFO] [TRACE: trace-8f1a2b3c] Starting AI stream: conv=919e22a2, provider=llm, model=default",
        "[INFO] [TRACE: trace-8f1a2b3c] First token rendered at TTFT=1.428s",
        "[INFO] [TRACE: trace-8f1a2b3c] Stream finalized: TTFT=1.428s, Gen=2.188s, DB=0.045s, Total=2.233s, Tokens=142"
    ]
    story.append(make_code_box(code_trace))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. In-Memory Thread-Safe Caching", h2_style))
    story.append(Paragraph(
        "Running LLM reviews on identical Git diffs wastes API quota and time. Nexarion implements an in-memory SHA-256 hash cache in <code>cache.py</code>. "
        "If a developer requests a review for a diff that was analyzed 2 minutes ago, Nexarion returns the cached findings instantly (0 ms latency).",
        body_style
    ))
    story.append(make_callout(
        "Telemetry Payload in done Event",
        "Nexarion transmits performance metrics directly to the client in the final SSE payload: "
        "<code>{\"metrics\": {\"ttft_ms\": 1428, \"total_ms\": 2233, \"chunks\": 142}}</code>. "
        "The React frontend displays these metrics in the review header.",
        bg_color="#EFF6FF", border_color="#3B82F6"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 8: PHASE 9 — TESTING WITH PYTEST & TESTCLIENT
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 9: Testing with Pytest & TestClient", h1_style))
    story.append(Paragraph(
        "Automated testing ensures that modifying one agent or route does not break other parts of the application. "
        "Nexarion maintains a comprehensive automated test suite spanning unit tests, integration tests, and streaming tests.",
        body_style
    ))

    story.append(Paragraph("1. Fast In-Memory API Testing with `TestClient`", h2_style))
    story.append(Paragraph(
        "<b>Why TestClient is revolutionary:</b> You do not need to boot a live Uvicorn server on a network port to test endpoints. "
        "FastAPI's <code>TestClient</code> passes synthetic HTTP requests directly into the ASGI application in memory. Tests run in milliseconds.",
        body_style
    ))

    code_test = [
        "# tests/test_web_api.py",
        "from fastapi.testclient import TestClient",
        "from code_review.web.app import app",
        "",
        "client = TestClient(app)",
        "",
        "def test_health_check_endpoint():",
        "    response = client.get('/health')",
        "    assert response.status_code == 200",
        "    assert response.json()['status'] == 'healthy'",
        "",
        "def test_unauthenticated_request_rejected():",
        "    response = client.post('/api/reviews', json={'diff': 'dummy'})",
        "    assert response.status_code == 401  # Blocked by auth dependency!"
    ]
    story.append(make_code_box(code_test))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Mocking External Services (`unittest.mock.patch`)", h2_style))
    story.append(Paragraph(
        "When running CI/CD pipelines, we cannot rely on live internet connections or paid API keys. "
        "<b>Mocking</b> replaces external API calls with controlled test doubles:",
        body_style
    ))

    code_mock = [
        "from unittest.mock import patch, MagicMock",
        "",
        "def test_llm_stream_with_mock():",
        "    mock_client = MagicMock()",
        "    mock_client.is_available.return_value = True",
        "    mock_client.stream_chat.return_value = iter(['Hello', ' world!'])",
        "",
        "    with patch('code_review.web.routes.conversation_routes.get_llm_client', return_value=mock_client):",
        "        res = client.post('/api/conversations/stream', json={'initial_message': 'Hi'})",
        "        assert res.status_code == 200",
        "        lines = list(res.iter_lines())",
        "        assert any('Hello' in line for line in lines)"
    ]
    story.append(make_code_box(code_mock))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. How to Test Server-Sent Events (SSE) Lines", h2_style))
    story.append(Paragraph(
        "To test a streaming endpoint, use <code>res.iter_lines()</code> to iterate through chunks. "
        "Verify that the stream starts with <code>event: init</code>, yields sequential <code>event: token</code> data, and concludes with <code>event: done</code>.",
        body_style
    ))
    story.append(make_callout(
        "Nexarion Test Suite Command",
        "Execute the complete test suite locally using: <code>python -m pytest tests/ -v</code>. "
        "All 57+ unit and integration tests run in under 4 seconds when external network calls are mocked properly.",
        bg_color="#ECFDF5", border_color="#10B981"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 9: PHASE 10 — PRODUCTION DEPLOYMENT, DOCKER & CI/CD
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Phase 10: Production Deployment, Docker & CI/CD", h1_style))
    story.append(Paragraph(
        "The final phase of engineering is taking code from a local laptop and deploying it reliably into production. "
        "Nexarion utilizes <b>Pydantic Settings</b>, <b>Multi-Stage Dockerfiles</b>, and <b>GitHub Actions</b>.",
        body_style
    ))

    story.append(Paragraph("1. Configuration Management with `pydantic-settings`", h2_style))
    story.append(Paragraph(
        "<b>Rule: Never hardcode secrets or URLs in source code.</b> "
        "In <code>config.py</code>, Nexarion defines a <code>Settings</code> class inheriting from <code>BaseSettings</code>. "
        "It automatically reads from operating system environment variables or local <code>.env</code> files with type validation:",
        body_style
    ))

    code_config = [
        "# src/code_review/config.py",
        "from pydantic_settings import BaseSettings",
        "",
        "class Settings(BaseSettings):",
        "    app_env: str = 'development'",
        "    database_url: str = 'sqlite:///./code_review.db'",
        "    jwt_secret: str = 'insecure-secret-key-change-in-prod'",
        "    nvidia_api_key: str = ''",
        "    nvidia_model: str = 'nvidia/nemotron-3-ultra-550b-a55b'",
        "",
        "    class Config:",
        "        env_file = '.env'",
        "        env_file_encoding = 'utf-8'"
    ]
    story.append(make_code_box(code_config))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Multi-Stage Dockerfile Architecture", h2_style))
    story.append(Paragraph(
        "A naive Dockerfile installs Node.js, npm, Python, compilers, and test suites into a massive 1.8 GB image. "
        "Nexarion uses a <b>Multi-Stage Build</b> to create a lean, secure 280 MB production container:",
        body_style
    ))

    docker_stages = [
        [Paragraph("<b>Build Stage</b>", table_header_style), Paragraph("<b>Base Image</b>", table_header_style), Paragraph("<b>Output & Purpose</b>", table_header_style)],
        [Paragraph("<b>Stage 1: Frontend</b>", table_body_bold), Paragraph("<code>node:20-alpine</code>", table_body_style), Paragraph("Runs <code>npm run build</code> to compile TypeScript and Tailwind into static HTML/JS/CSS assets in <code>/dist</code>.", table_body_style)],
        [Paragraph("<b>Stage 2: Final Runtime</b>", table_body_bold), Paragraph("<code>python:3.12-slim</code>", table_body_style), Paragraph("Copies only the compiled <code>/dist</code> assets from Stage 1 into the Python web server. Discards Node.js completely!", table_body_style)],
    ]
    t_dock = Table(docker_stages, colWidths=[100, 140, 282])
    t_dock.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_dock)
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. The CI/CD Pipeline (GitHub Actions)", h2_style))
    story.append(Paragraph(
        "Located in <code>.github/workflows/ci.yml</code>, automated workflows run every time code is pushed. "
        "The pipeline acts as an automated quality gate through 4 sequential stages:",
        body_style
    ))
    story.append(Paragraph("<b>Stage 1: Lint & Format Check</b> — Runs <code>ruff check .</code> to enforce PEP 8 style standards.", bullet_style))
    story.append(Paragraph("<b>Stage 2: Static Security Audit</b> — Runs <code>bandit -r src/</code> to catch insecure dependencies.", bullet_style))
    story.append(Paragraph("<b>Stage 3: Automated Test Suite</b> — Runs <code>pytest --cov</code> to guarantee 100% test pass rates.", bullet_style))
    story.append(Paragraph("<b>Stage 4: Container Build & Deploy</b> — Builds the Docker image and deploys to cloud hosting.", bullet_style))
    story.append(make_callout(
        "Production Health Check Endpoint",
        "Nexarion exposes <code>GET /health</code>. Cloud orchestrators (Kubernetes, AWS ECS, Render) ping this route every 30 seconds. "
        "If the container fails to respond with HTTP 200, the orchestrator automatically restarts the instance.",
        bg_color="#EFF6FF", border_color="#3B82F6"
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 10: ACTIONABLE STUDY CHECKLIST & NEXT STEPS
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Nexarion Engineering Mastery Checklist", h1_style))
    story.append(Paragraph(
        "Use this sequential checklist as your personal study tracker. Once you master these practical tasks, "
        "you will be fully capable of building, extending, and maintaining any part of the Nexarion ecosystem.",
        body_style
    ))

    checklist_data = [
        [Paragraph("<b>Step</b>", table_header_style), Paragraph("<b>Practical Milestone</b>", table_header_style), Paragraph("<b>Verification Exercise in Nexarion</b>", table_header_style)],
        [
            Paragraph("<b>Step 1</b>", table_body_bold),
            Paragraph("<b>Create a Custom Agent</b>", table_body_style),
            Paragraph("Create <code>DocumentationAgent</code> inheriting from <code>BaseAgent</code>. Use the <code>ast</code> module to check if all top-level functions have docstrings.", table_body_style)
        ],
        [
            Paragraph("<b>Step 2</b>", table_body_bold),
            Paragraph("<b>Add a Pydantic Endpoint</b>", table_body_style),
            Paragraph("Add a new route <code>POST /api/agents/{agent_id}/calibrate</code> in <code>agent_routes.py</code> with a validated Pydantic request schema.", table_body_style)
        ],
        [
            Paragraph("<b>Step 3</b>", table_body_bold),
            Paragraph("<b>Implement Route Dependency</b>", table_body_style),
            Paragraph("Protect the calibration endpoint using <code>Depends(get_current_user)</code> so only authenticated users can trigger it.", table_body_style)
        ],
        [
            Paragraph("<b>Step 4</b>", table_body_bold),
            Paragraph("<b>Write a Streaming Generator</b>", table_body_style),
            Paragraph("Trace how <code>_create_streaming_response()</code> yields tokens and inspect the frontend <code>readSSEStream()</code> reader in <code>api.ts</code>.", table_body_style)
        ],
        [
            Paragraph("<b>Step 5</b>", table_body_bold),
            Paragraph("<b>Add an ORM Relationship</b>", table_body_style),
            Paragraph("Add an <code>AgentMetricRecord</code> table in <code>models.py</code> with a foreign key pointing to <code>ReviewRecord</code>. Test queries via <code>get_db</code>.", table_body_style)
        ],
        [
            Paragraph("<b>Step 6</b>", table_body_bold),
            Paragraph("<b>Write Automated Pytest</b>", table_body_style),
            Paragraph("Write a test in <code>tests/</code> using <code>TestClient</code> to verify your new endpoint returns 200 when authorized and 401 when unauthorized.", table_body_style)
        ],
        [
            Paragraph("<b>Step 7</b>", table_body_bold),
            Paragraph("<b>Build Docker Container</b>", table_body_style),
            Paragraph("Execute <code>docker build -t nexarion-app .</code> and run the container locally to verify both React and FastAPI boot together.", table_body_style)
        ],
    ]
    t_chk = Table(checklist_data, colWidths=[55, 175, 292])
    t_chk.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_chk)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Summary: What You Have Achieved", h1_style))
    story.append(Paragraph(
        "By filtering out irrelevant web development distractions (NoSQL databases, message brokers, template engines) and focusing on "
        "<b>OOP Agent design</b>, <b>FastAPI Dependency Injection</b>, <b>SQLAlchemy ORM</b>, <b>SSE Token Streaming</b>, and <b>Docker containerization</b>, "
        "you now possess a precise, industry-ready roadmap to master modern AI engineering.",
        body_style
    ))
    story.append(Spacer(1, 4))

    story.append(make_callout(
        "Official Documentation & Codebase References",
        "• <b>FastAPI Core:</b> <code>https://fastapi.tiangolo.com</code><br/>"
        "• <b>Pydantic v2:</b> <code>https://docs.pydantic.dev/latest</code><br/>"
        "• <b>SQLAlchemy 2.0:</b> <code>https://docs.sqlalchemy.org/en/20</code><br/>"
        "• <b>Nexarion Source:</b> Inspect <code>src/code_review/web/routes/conversation_routes.py</code> for the primary streaming reference implementation.",
        bg_color="#F8FAFC", border_color="#64748B"
    ))

    # Build the document using the NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated: {filename}")


if __name__ == "__main__":
    out_pdf = "docs/Nexarion_Master_Engineering_Curriculum_Guide.pdf"
    build_pdf(out_pdf)
    root_pdf = "Nexarion_Master_Engineering_Curriculum_Guide.pdf"
    shutil.copy(out_pdf, root_pdf)
    print(f"Copied to root: {root_pdf}")

    # Verify page count with pypdf
    reader = pypdf.PdfReader(out_pdf)
    print(f"Total page count: {len(reader.pages)}")

