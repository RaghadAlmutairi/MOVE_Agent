"""Pydantic schemas for the report, competitors, personas and the router plan."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


REVENUE_MODELS = Literal[
    "SUBSCRIPTION", "USAGE_BASED", "FREEMIUM", "FREE_TIER", "LICENSE",
    "ONE_TIME", "ADS", "OPEN_SOURCE", "COMMISSION", "ENTERPRISE_CONTRACT",
    "UNKNOWN",
]


class SwotItem(BaseModel):
    point: str
    source_ids: List[str] = Field(default_factory=list)


class SWOT(BaseModel):
    strengths: List[SwotItem] = Field(default_factory=list, max_length=5)
    weaknesses: List[SwotItem] = Field(default_factory=list, max_length=5)
    opportunities: List[SwotItem] = Field(default_factory=list, max_length=5)
    threats: List[SwotItem] = Field(default_factory=list, max_length=5)


class Competitor(BaseModel):
    name: str
    entity_type: Literal["COMPANY", "PRODUCT", "SERVICE", "ALTERNATIVE", "UNKNOWN"]
    parent_company: str = ""
    official_website: str = ""
    directness: Literal["DIRECT", "INDIRECT", "SUBSTITUTE", "UNKNOWN"] = "UNKNOWN"
    value_proposition: str = ""
    target_audience: str = ""

    serves_businesses: bool = False
    serves_consumers: bool = False
    serves_government: bool = False
    is_marketplace: bool = False
    business_model_evidence: str = ""

    revenue_models: List[REVENUE_MODELS] = Field(default_factory=list, max_length=5)

    positioning: str = ""
    pricing_signal: str = ""
    # Product-catalog comparison fields (populated for product_competitors)
    top_products: List[str] = Field(default_factory=list, max_length=5)
    key_features: List[str] = Field(default_factory=list, max_length=6)
    differentiators_usp: List[str] = Field(default_factory=list, max_length=5)
    swot: Optional[SWOT] = None
    source_ids: List[str] = Field(default_factory=list)


class PorterForce(BaseModel):
    force: Literal[
        "Competitive Rivalry", "Threat of New Entrants", "Threat of Substitutes",
        "Bargaining Power of Buyers", "Bargaining Power of Suppliers",
    ]
    intensity: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
    rationale: str


class Psychographics(BaseModel):
    values: List[str] = Field(default_factory=list, max_length=4)
    attitudes: List[str] = Field(default_factory=list, max_length=4)
    interests: List[str] = Field(default_factory=list, max_length=4)
    personality_traits: List[str] = Field(default_factory=list, max_length=4)


class Persona(BaseModel):
    persona_name: str
    role_title: str = ""
    segment: str = ""
    goals: List[str] = Field(default_factory=list, max_length=4)
    pain_points: List[str] = Field(default_factory=list, max_length=4)
    buying_triggers: List[str] = Field(default_factory=list, max_length=3)
    objections: List[str] = Field(default_factory=list, max_length=3)
    # Proposed TOP SOCIAL CHANNELS to reach this persona (LinkedIn, Reddit, X, ...)
    channels: List[str] = Field(default_factory=list, max_length=4)
    decision_power: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    messaging_angle: str = ""
    # ICP enrichment
    psychographics: Psychographics = Field(default_factory=Psychographics)
    buying_process: str = ""


class ReportCore(BaseModel):
    title: str
    executive_summary: str
    subject_swot: SWOT
    market_trends: List[str] = Field(default_factory=list, max_length=6)
    opportunities: List[str] = Field(default_factory=list, max_length=5)
    risks: List[str] = Field(default_factory=list, max_length=5)
    recommendations: List[str] = Field(default_factory=list, max_length=5)
    confidence_level: Literal["low", "medium", "high"]


class CompetitorBlock(BaseModel):
    company_competitors: List[Competitor] = Field(default_factory=list, max_length=4)
    product_competitors: List[Competitor] = Field(default_factory=list, max_length=4)
    alternative_solutions: List[Competitor] = Field(default_factory=list, max_length=2)


class PersonaBlock(BaseModel):
    buyer_personas: List[Persona] = Field(default_factory=list, max_length=4)


class Report(BaseModel):
    title: str
    executive_summary: str
    subject_swot: SWOT
    company_competitors: List[Competitor] = Field(default_factory=list, max_length=4)
    product_competitors: List[Competitor] = Field(default_factory=list, max_length=4)
    alternative_solutions: List[Competitor] = Field(default_factory=list, max_length=2)
    buyer_personas: List[Persona] = Field(default_factory=list, max_length=4)
    market_trends: List[str] = Field(default_factory=list, max_length=6)
    opportunities: List[str] = Field(default_factory=list, max_length=5)
    risks: List[str] = Field(default_factory=list, max_length=5)
    recommendations: List[str] = Field(default_factory=list, max_length=5)
    confidence_level: Literal["low", "medium", "high"]


class ToolPlan(BaseModel):
    subject_entity: str = ""
    subject_type: Literal[
        "COMPANY", "PRODUCT", "PLATFORM_MARKETPLACE", "BOTH", "UNKNOWN",
    ] = "UNKNOWN"
    industry: str = ""
    market: str
    geography: str = "global"
    scope_is_user_restricted: bool = False
    prohibited_narrowing: List[str] = Field(default_factory=list)
    required_tools: List[Literal[
        "competitive_landscape_tool", "market_analysis_tool", "customer_intelligence_tool",
        "internal_knowledge_tool",
    ]]


# ======================= GTM STRATEGY AGENT (parallel: Foundation/Activation/Execution) =======================
# ---- Foundation ----
class SlotStatement(BaseModel):
    for_who: str = ""
    who_need: str = ""
    category: str = ""
    promise: str = ""
    unlike: str = ""
    proof: str = ""


class ICP(BaseModel):
    primary_segment: str = ""
    firmographics: str = ""
    technographics: str = ""
    why_now: str = ""
    buying_committee: List[str] = Field(default_factory=list, max_length=10)


class Beachhead(BaseModel):
    segment: str = ""
    rationale: str = ""
    entry_wedge: str = ""
    expansion_path: List[str] = Field(default_factory=list, max_length=8)
    market_sizing_logic: str = ""


class CompetitiveEdge(BaseModel):
    competitor: str
    where_we_win: List[str] = Field(default_factory=list, max_length=5)
    where_they_win: List[str] = Field(default_factory=list, max_length=4)
    dont_compete_on: str = ""
    sharpest_message: str = ""


class GTMFoundation(BaseModel):
    north_star: str = ""                       # one-line strategic headline (cover subtitle)
    positioning_statement: str = ""
    slot_statement: SlotStatement = Field(default_factory=SlotStatement)
    icp: ICP = Field(default_factory=ICP)
    top_pains: List[str] = Field(default_factory=list, max_length=8)
    trigger_events: List[str] = Field(default_factory=list, max_length=6)
    disqualifiers: List[str] = Field(default_factory=list, max_length=6)
    secondary_segments: List[str] = Field(default_factory=list, max_length=6)
    beachhead: Beachhead = Field(default_factory=Beachhead)
    competitive_differentiation: List[CompetitiveEdge] = Field(default_factory=list, max_length=6)


# ---- Activation ----
class PricingStrategy(BaseModel):
    packaging_logic: str = ""
    tiers: List[str] = Field(default_factory=list, max_length=6)
    anchor_strategy: str = ""
    commercial_motion: str = ""
    pricing_levers: List[str] = Field(default_factory=list, max_length=8)
    pricing_risks: List[str] = Field(default_factory=list, max_length=6)


class GTMMotion(BaseModel):
    primary: str = ""
    secondary: str = ""
    rationale: str = ""
    motion_risks: List[str] = Field(default_factory=list, max_length=6)


class ChannelPlay(BaseModel):
    channel: str
    funnel_role: str = ""
    why: str = ""
    leading_indicator: str = ""
    invest: str = ""


class PersonaMessaging(BaseModel):
    persona: str
    core_promise: str = ""
    primary_channel: str = ""
    cta: str = ""
    pillars: List[str] = Field(default_factory=list, max_length=5)
    proof_points: List[str] = Field(default_factory=list, max_length=5)
    objection_handling: List[str] = Field(default_factory=list, max_length=5)


class ContentEngine(BaseModel):
    cadence: str = ""
    distribution_strategy: str = ""
    tofu: List[str] = Field(default_factory=list, max_length=6)
    mofu: List[str] = Field(default_factory=list, max_length=6)
    bofu: List[str] = Field(default_factory=list, max_length=6)


class GTMActivation(BaseModel):
    pricing: PricingStrategy = Field(default_factory=PricingStrategy)
    motion: GTMMotion = Field(default_factory=GTMMotion)
    channel_plays: List[ChannelPlay] = Field(default_factory=list, max_length=8)
    messaging_by_persona: List[PersonaMessaging] = Field(default_factory=list, max_length=6)
    content_engine: ContentEngine = Field(default_factory=ContentEngine)


# ---- Execution ----
class SalesStage(BaseModel):
    stage: str
    objective: str = ""
    key_questions: List[str] = Field(default_factory=list, max_length=5)
    exit_criteria: str = ""
    traps: List[str] = Field(default_factory=list, max_length=4)


class SalesPlaybook(BaseModel):
    qualification_framework: str = ""
    stages: List[SalesStage] = Field(default_factory=list, max_length=7)
    must_have_collateral: List[str] = Field(default_factory=list, max_length=8)


class DemandLever(BaseModel):
    lever: str
    logic: str = ""


class DemandGen(BaseModel):
    levers: List[DemandLever] = Field(default_factory=list, max_length=6)
    campaign_concepts: List[str] = Field(default_factory=list, max_length=6)


class Metric(BaseModel):
    metric: str
    why: str = ""
    target_band: str = ""
    cadence: str = ""


class MetricsPlan(BaseModel):
    north_star_metric: str = ""
    north_star_why: str = ""
    input_metrics: List[Metric] = Field(default_factory=list, max_length=8)
    funnel_kpis: List[Metric] = Field(default_factory=list, max_length=8)
    health_metrics: List[Metric] = Field(default_factory=list, max_length=6)


class RoadmapWorkstream(BaseModel):
    workstream: str
    deliverable: str = ""
    owner: str = ""
    success_signal: str = ""
    deps: str = ""


class RoadmapPhase(BaseModel):
    phase: str
    objective: str = ""
    workstreams: List[RoadmapWorkstream] = Field(default_factory=list, max_length=8)


class StrategicRisk(BaseModel):
    risk: str
    likelihood: str = ""
    impact: str = ""
    mitigation: str = ""
    owner: str = ""


class GTMExecution(BaseModel):
    sales_playbook: SalesPlaybook = Field(default_factory=SalesPlaybook)
    demand_gen: DemandGen = Field(default_factory=DemandGen)
    metrics: MetricsPlan = Field(default_factory=MetricsPlan)
    roadmap_90day: List[RoadmapPhase] = Field(default_factory=list, max_length=4)
    risks: List[StrategicRisk] = Field(default_factory=list, max_length=6)


# ---- Merged strategy (no confidence field by design) ----
class GTMStrategy(BaseModel):
    north_star: str = ""
    foundation: GTMFoundation = Field(default_factory=GTMFoundation)
    activation: GTMActivation = Field(default_factory=GTMActivation)
    execution: GTMExecution = Field(default_factory=GTMExecution)


# ============== COMPETITOR CANDIDATES (discover -> verify -> synthesize) ==============
class CompetitorCandidate(BaseModel):
    name: str
    entity_type: Literal["COMPANY", "PRODUCT", "SERVICE", "PLATFORM", "UNKNOWN"] = "UNKNOWN"
    likely_domain: str = ""
    evidence_source_ids: List[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"


class CompetitorCandidateBlock(BaseModel):
    candidates: List[CompetitorCandidate] = Field(default_factory=list, max_length=12)


# ============================ CONTENT AGENT (third agent) ============================
class LinkedInPost(BaseModel):
    kind: Literal["THOUGHT_LEADERSHIP", "INDUSTRY_INSIGHT", "PRODUCT_AWARENESS"]
    hook: str                                         # ≤12-word scroll-stopper line
    body: str                                         # ≥150 words, white-space-friendly prose
    engagement_question: str = ""                     # closing provocative question
    cta: str = ""                                     # single specific action line
    hashtags: List[str] = Field(default_factory=list, max_length=6)


class BlogDraft(BaseModel):
    kind: Literal["SEO", "EDUCATIONAL"]
    title: str
    target_keyword: str = ""                          # primary keyword phrase
    secondary_keywords: List[str] = Field(default_factory=list, max_length=5)
    meta_description: str = ""                        # 140-160 chars, includes keyword
    outline: List[str] = Field(default_factory=list, max_length=9)   # 6-9 H2/H3 headings
    body: str                                         # ≥550 words of fully written prose
    cta: str = ""                                     # closing call-to-action sentence


class EmailDraft(BaseModel):
    kind: Literal["OUTBOUND", "NURTURE", "LAUNCH"]
    subject: str                                      # curiosity-driving subject line
    preview: str = ""                                 # 80-110 char preview text
    body: str                                         # ≥280 words, full send-ready email
    cta: str = ""                                     # button/link label (single action)


class ContentBundle(BaseModel):
    phase: Literal["A", "B"] = "A"
    positioning_line: str = ""
    messaging_pillars: List[str] = Field(default_factory=list, max_length=5)
    linkedin_posts: List[LinkedInPost] = Field(default_factory=list, max_length=3)
    blog_drafts: List[BlogDraft] = Field(default_factory=list, max_length=2)
    email_drafts: List[EmailDraft] = Field(default_factory=list, max_length=3)
