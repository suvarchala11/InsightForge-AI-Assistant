


Secure AI Insights Assistant
## Overview
Build a secure AI-powered internal analytics assistant that can answer business questions using
multiple private data sources.
The system should combine:
- Structured data from a relational database
- Unstructured data from PDF reports / internal documents
- CSV / spreadsheet business data
The assistant must provide useful answers while maintaining strong privacy and access
boundaries.
This assignment is designed to evaluate:
- AI engineering capability
- Backend engineering
- Frontend engineering
- Tool/function calling architecture
- Multi-source retrieval systems
- Data handling maturity
- Security thinking
- Code quality
- Deployment readiness

## Business Scenario
A fictional entertainment company stores internal business data across multiple systems.
Leadership wants a smart assistant that can answer questions like:
- Which movies performed best this year?
- Why is a specific title trending?
- Which genre is growing fastest?


- What audience segments are most engaged?
- What actions should leadership take next quarter?
The assistant must use approved internal tools and trusted retrieval methods.

## Core Requirement
The system must work with multiple data sources and combine them intelligently.
## Required Sources
Source A — SQL Database
Use provided relational data.
Source B — PDF Documents
Use provided internal reports.
Source C — CSV / Excel Files
Use provided business data files.

## Mandatory Rules
## 1. Security
Sensitive internal data must be protected.
Your architecture should demonstrate safe handling of private information.
- Tool-Based Access
The AI assistant should use backend tools / functions / services rather than unrestricted raw
data access.
## 3. Explainability
Responses should indicate what sources were used when appropriate.

## Functional Requirements
## Backend


Build APIs / services for:
- data ingestion
- querying structured data
- document retrieval
- AI orchestration
- analytics generation
Use any backend stack such as:
- Python + FastAPI
## Frontend
Build a usable interface with:
- Chat assistant UI
- Filters / selectors
- Insights panel
- Charts / visual summaries
- Query history or tool trace
Use any framework such as:
## • React
## • Next.js
## • Vue

AI Layer
Use any model provider:
- OpenAI
## • Anthropic
- local model
## • Ollama


The model should help answer business questions using your architecture.

## Required Example Questions
Your system should be able to answer questions like:
- Which titles performed best in 2025?
- Why is Stellar Run trending recently?
- Compare Dark Orbit vs Last Kingdom.
- Which city had the strongest engagement last month?
- What explains weak comedy performance?
- What recommendations would you give for leadership?

## Provided Datasets
- SQL / CSV Structured Data
Create random csv data files:
- movies.csv
- viewers.csv
- watch_activity.csv
- reviews.csv
- marketing_spend.csv
- regional_performance.csv
Load these into your chosen database or use directly.

- PDF Documents
Create random demo/use any pdfs for the same:
- Quarterly executive report
- Campaign performance summary


- Content roadmap
- Policy guidelines
- Audience behavior report
Use them as additional knowledge sources.

## Minimum Features
## Required
- Working backend and frontend
- Multi-source answers
- At least one chart or visual summary
- Clean README
- Setup instructions
## Strongly Recommended
- Clean project structure
## • Logging
- Error handling
## • Validation
- Reusable code
- Containerized setup using Docker

## Submission Requirements
Please submit:
- GitHub repository link
- Setup instructions
- Detailed README with architecture overview diagram
- Notes on assumptions / tradeoffs


- (Optional) 3 - 5 minute demo video

## Evaluation Criteria
## Category Weight
## Architecture Quality 25
## Backend Engineering 20
AI / Multi-source Reasoning 20
## Frontend Experience 15
## Security / Data Handling 10
## Code Quality 5
## Documentation 5

## What We Appreciate
- Working prototype
- Thoughtful architecture
- Clean APIs
- Practical UX
- Strong reasoning
- Reliable outputs
- Clear communication
- Good engineering judgment

## Notes
You are free to make reasonable assumptions where details are not explicitly specified.
Please document those assumptions clearly.


We are interested not only in the final output, but also in how you think and structure systems.

## Final Reminder
Build something practical, secure, and maintainable.
Perfect polish is less important than strong engineering choices.
