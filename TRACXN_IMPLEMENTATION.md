# Tracxn-Based Scoring Implementation

## ✅ Completed Features

### 1. Team Background Scoring from Tracxn Excel File
- **Location**: `tracxn_scorer.py` → `analyze_team_background()`
- **How it works**:
  - Reads from second sheet ("Portfolio Companies 1.1") of Tracxn Excel file
  - Extracts founder background (previous companies, education) from email/deck using AI
  - Compares against portfolio companies' team backgrounds in Tracxn
  - Scores based on overlaps:
    - Worked at portfolio companies: +60-90 points
    - Same schools as portfolio founders: +60-90 points
    - Tier 1 companies (FAANG, McKinsey, etc.): +50-70 points
    - Top schools: +10 points
- **Score Range**: 0-100

### 2. White Space Analysis using OpenAI API
- **Location**: `tracxn_scorer.py` → `analyze_white_space()`
- **How it works**:
  - Uses GPT-4o to analyze startup pitch
  - Identifies subsector/industry
  - Estimates number of funded startups in subsector (last 2-3 years)
  - Assesses market size (Small/Medium/Large)
  - Evaluates competition intensity (Low/Medium/High)
  - Identifies white space: Low funded startups (<20) AND Large market = White space
- **Scoring Logic**:
  - Low competition: +30 points
  - Medium competition: +10 points
  - High competition: -20 points
  - Large market: +20 points
  - Medium market: +5 points
  - Small market: -10 points
  - Few funded startups (<10): +25 points
  - Many funded startups (>50): -15 points
- **Note**: Uses OpenAI's web search capabilities (if available) to find real-time funding data. The model is instructed to search for current data from sources like Crunchbase, PitchBook, and VC reports. If web search tools aren't available, falls back to GPT-4o's extensive knowledge base (up to April 2024) of funding rounds and market trends.

### 3. Overall Score Calculation
- **Location**: `tracxn_scorer.py` → `calculate_score()`
- **Formula**: Weighted average
  - 60% team background score
  - 40% white space score
- **Score Range**: 0-100

### 4. Email Replies Based on Score
- **Location**: `email_classifier.py` → `generate_deal_flow_reply()`
- **How it works**:
  - Score >= 75: Warm, encouraging, shows genuine interest
  - Score 60-74: Professional, positive, but not overly enthusiastic
  - Score 50-59: Professional but neutral
  - Score < 50: Polite but brief, not overly encouraging
- **Key Feature**: Responds DIRECTLY to founder based on score. Does NOT redirect to other VC people unless score is very low (<40).

### 5. Database Integration
- **New Fields in `Deal` model**:
  - `team_background_score`: Float (0-100)
  - `white_space_score`: Float (0-100)
  - `overall_score`: Float (0-100)
  - `white_space_analysis`: Text (JSON with subsector, competition, market size)
- **Old scores** (kept for backward compatibility, not actively used):
  - `risk_score`, `portfolio_comparison_score`, `founder_market_score`, `traction_score`

## 📋 Requirements Checklist

- [x] Team background scoring from Tracxn Excel file
- [x] White space analysis using OpenAI API (analyzes funded startups count and market size)
- [x] Score generation based on 2 things (60% team + 40% white space)
- [x] Email replies respond directly to founder based on score
- [x] Old scoring system removed from active use (kept in DB for compatibility)
- [x] Tracxn file reading (second sheet, correct header row)

## 🔧 Configuration

### Environment Variables
- `TRACXN_FILE_PATH`: Path to Tracxn Excel file (default: `TracxnExport-FundProfilePage-PortfolioCompaniesExport-Nov-05-2025.xlsx`)
- `OPENAI_API_KEY`: Required for white space analysis and team background extraction

### Dependencies
- `pandas==2.0.3`: For reading Excel files
- `openpyxl==3.1.2`: For Excel file parsing

## 📝 Usage Flow

1. **Email Classification**: Email is classified as Deal Flow
2. **Team Background Analysis**:
   - Extracts founder background from email/deck
   - Compares against Tracxn portfolio companies
   - Generates team background score (0-100)
3. **White Space Analysis**:
   - Analyzes startup pitch using GPT-4o
   - Estimates funded startups count, market size, competition
   - Generates white space score (0-100)
4. **Overall Score**: Weighted average (60% team + 40% white space)
5. **Reply Generation**: AI generates reply based on overall score, responding directly to founder

## 🎯 Key Improvements Over Old System

1. **Data-Driven**: Uses actual portfolio data from Tracxn instead of hardcoded portfolio
2. **Market Intelligence**: Analyzes funding trends and competition intensity
3. **Direct Communication**: Replies go directly to founder, not redirected to VC people
4. **Score-Based Responses**: Reply tone and content adapt based on calculated scores

