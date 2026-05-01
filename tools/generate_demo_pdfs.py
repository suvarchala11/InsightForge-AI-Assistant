from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


def write_pdf(path: Path, title: str, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", style="B", size=16)
    pdf.multi_cell(0, 10, title)
    pdf.ln(2)

    pdf.set_font("Helvetica", size=11)
    for p in paragraphs:
        p = (p or "").strip()
        if not p:
            continue
        pdf.multi_cell(0, 6, p)
        pdf.ln(3)

    pdf.output(str(path))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data"

    documents: list[tuple[str, str, list[str]]] = [
        (
            "executive_report_q1_2025.pdf",
            "Q1 2025 Executive Strategy Report (PDF)",
            [
                "Executive Summary: Q1 2025 showed strong growth in Sci-Fi and Fantasy.",
                "Trend Analysis: 'Stellar Run' is trending recently due to a viral TikTok campaign that resonated with younger viewers.",
                "Comedy performance has been weak due to market saturation and a lack of breakout original scripts.",
                "Recommendations: Reallocate 20% of Comedy marketing budget to Sci-Fi/Fantasy; fast-track the Stellar Run sequel; explore interactive content for Asia-Pacific.",
                "Policy Note: User watch history must be aggregated for any third-party reporting.",
            ],
        ),
        (
            "campaign_summary_2024_2025.pdf",
            "Campaign Performance Summary 2024-2025 (PDF)",
            [
                "Dark Orbit vs Last Kingdom: Dark Orbit used heavy TV ad spend ($800k) and achieved ~40% ROI; Last Kingdom used community-first social media ($300k) and achieved ~250% ROI.",
                "Audience Segments: Premium subscribers aged 25-34 in North America and Canada are the most engaged.",
                "Next Steps: Reduce expensive TV for niche genres; increase social media influencer partnerships.",
            ],
        ),
        (
            "audience_behavior_report_q1_2025.pdf",
            "Audience Behavior Report (PDF)",
            [
                "Key Segment: Premium 18-34 viewers show the highest binge rates for Sci-Fi bundles.",
                "Engagement Insight: Asia-Pacific shows high average engagement and responds well to interactive content formats.",
                "Actionable Note: Focus on short-form social campaigns to drive initial discovery for Sci-Fi releases.",
            ],
        ),
        (
            "policy_guidelines_internal.pdf",
            "Internal Policy Guidelines (PDF)",
            [
                "Privacy: Never expose raw watch history to the model; only allow aggregated queries via controlled tools.",
                "Budget Control: Marketing budgets exceeding $500k require VP approval.",
                "Compliance: Ensure all new productions pass a diversity and inclusion audit before greenlight.",
            ],
        ),
    ]

    for filename, title, paragraphs in documents:
        out_path = data_dir / filename
        write_pdf(out_path, title, paragraphs)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
