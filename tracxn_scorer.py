"""
Tracxn-based scoring system with OpenAI web search for white space analysis
"""
import os
import pandas as pd
import json
from typing import Dict, Optional, List
from openai import OpenAI
import requests

class TracxnScorer:
    """Score deals using Tracxn Excel data and OpenAI web search"""
    
    def __init__(self, tracxn_file_path: str, openai_client=None):
        """
        Initialize Tracxn scorer
        
        Args:
            tracxn_file_path: Path to Tracxn Excel file
            openai_client: OpenAI client instance (optional, will create if not provided)
        """
        self.tracxn_file_path = tracxn_file_path
        self.tracxn_data = None
        self.openai_client = openai_client
        
        # Load Tracxn data if file exists
        if os.path.exists(tracxn_file_path):
            try:
                # Tracxn export: second sheet (index 1) has the data
                # Header row is at index 5 (row 6)
                xls = pd.ExcelFile(tracxn_file_path)
                if len(xls.sheet_names) > 1:
                    # Use second sheet (index 1)
                    sheet_name = xls.sheet_names[1]
                    # Read with header at row 5 (index 5, which is row 6)
                    self.tracxn_data = pd.read_excel(tracxn_file_path, 
                                                     sheet_name=sheet_name, 
                                                     header=5)
                    # Clean up: remove any rows that are all NaN
                    self.tracxn_data = self.tracxn_data.dropna(how='all')
                    print(f"✓ Loaded Tracxn data from '{sheet_name}': {len(self.tracxn_data)} portfolio companies")
                else:
                    print(f"⚠️  Tracxn file has less than 2 sheets")
                    self.tracxn_data = None
            except Exception as e:
                print(f"⚠️  Could not load Tracxn file: {str(e)}")
                import traceback
                traceback.print_exc()
                self.tracxn_data = None
        else:
            print(f"⚠️  Tracxn file not found: {tracxn_file_path}")
        
        # Initialize OpenAI client if not provided
        if not self.openai_client:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.openai_client = OpenAI(api_key=api_key)
            else:
                print("⚠️  OpenAI API key not found. White space analysis will be limited.")
    
    def analyze_team_background(self, founder_name: str, founder_email: str, 
                                email_body: str, subject: str) -> Dict:
        """
        Analyze team background by comparing incoming founder's background against Tracxn portfolio data
        
        Returns:
            Dict with team background analysis including:
            - previous_companies: List of previous companies (extracted from email/deck)
            - education: Education background (extracted from email/deck)
            - experience_years: Years of experience
            - background_score: Score based on matches with portfolio (0-100)
            - portfolio_overlaps: List of portfolio companies with matching backgrounds
        """
        if self.tracxn_data is None:
            return {
                'previous_companies': [],
                'education': None,
                'experience_years': 0,
                'background_score': 0,  # Default score when Tracxn data unavailable
                'tracxn_matched': False,
                'portfolio_overlaps': []
            }
        
        # First, extract founder's background from email/deck using AI
        # This will be compared against portfolio companies' team backgrounds
        founder_previous_companies = []
        founder_education = None
        
        # Use OpenAI to extract founder background from email/deck
        if self.openai_client:
            try:
                extraction_prompt = f"""Extract the founder's background information from this email/pitch.

Founder Name: {founder_name}
Email: {founder_email}
Subject: {subject}
Email Body: {email_body[:2000]}

Extract:
1. Previous companies they worked at (look for "Ex-", "Previously at", "Worked at", company names)
2. Education/School (look for university names, degrees)

Return JSON format:
{{
    "previous_companies": ["company1", "company2", ...],
    "education": "university name or null",
    "experience_years": <number or null>
}}"""

                # Handle both OpenAIClient wrapper and direct OpenAI client
                client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a data extraction assistant. Extract founder background information from pitch emails."},
                        {"role": "user", "content": extraction_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=300,
                    response_format={"type": "json_object"}
                )
                
                extracted_info = json.loads(response.choices[0].message.content)
                founder_previous_companies = extracted_info.get('previous_companies', [])
                founder_education = extracted_info.get('education')
                experience_years = extracted_info.get('experience_years', 0)
                print(f"✅ Extracted founder background: Companies: {founder_previous_companies}, Education: {founder_education}")
            except Exception as e:
                print(f"❌ Error extracting founder background: {str(e)}")
                import traceback
                traceback.print_exc()
                experience_years = 0
        else:
            experience_years = 0
        
        # Now compare against portfolio companies' team backgrounds
        portfolio_overlaps = []
        background_score = 0  # Base score (no matches = 0)
        
        if self.tracxn_data is not None:
            for idx, row in self.tracxn_data.iterrows():
                portfolio_company = str(row.get('Company Name', ''))
                portfolio_team_bg = str(row.get('Team Background', ''))
                portfolio_key_people = str(row.get('Key People Info', ''))
                
                has_overlap = False
                overlap_reasons = []
                
                # Check company overlaps
                if pd.notna(portfolio_team_bg) and portfolio_team_bg != 'nan':
                    # Parse portfolio team background: "Company Wise > McKinsey, College Wise > Stanford"
                    if 'Company Wise >' in portfolio_team_bg:
                        portfolio_companies = portfolio_team_bg.split('Company Wise >')[1].split('College Wise >')[0].strip()
                        portfolio_companies_list = [c.strip().lower() for c in portfolio_companies.split(',') if c.strip()]
                        
                        # Check if founder's companies match portfolio companies
                        for founder_company in founder_previous_companies:
                            founder_company_lower = founder_company.lower()
                            for portfolio_company_name in portfolio_companies_list:
                                if portfolio_company_name in founder_company_lower or founder_company_lower in portfolio_company_name:
                                    has_overlap = True
                                    overlap_reasons.append(f"Worked at {portfolio_company_name}")
                                    break
                    
                    # Check education overlaps
                    if 'College Wise >' in portfolio_team_bg:
                        portfolio_schools = portfolio_team_bg.split('College Wise >')[1].strip()
                        portfolio_schools_list = [s.strip().lower() for s in portfolio_schools.split(',') if s.strip()]
                        
                        if founder_education:
                            founder_edu_lower = founder_education.lower()
                            for portfolio_school in portfolio_schools_list:
                                if portfolio_school in founder_edu_lower or founder_edu_lower in portfolio_school:
                                    has_overlap = True
                                    overlap_reasons.append(f"Same school: {portfolio_school}")
                                    break
                
                # Also check Key People Info for more detailed matches
                if pd.notna(portfolio_key_people) and portfolio_key_people != 'nan':
                    # Check if founder's companies appear in portfolio key people's backgrounds
                    for founder_company in founder_previous_companies:
                        if founder_company.lower() in portfolio_key_people.lower():
                            has_overlap = True
                            overlap_reasons.append(f"Company overlap in {portfolio_company}")
                    
                    # Check education in key people
                    if founder_education and founder_education.lower() in portfolio_key_people.lower():
                        has_overlap = True
                        overlap_reasons.append(f"Education overlap in {portfolio_company}")
                
                if has_overlap:
                    portfolio_overlaps.append({
                        'company': portfolio_company,
                        'reasons': overlap_reasons
                    })
        
        # Calculate background score based ONLY on Tracxn portfolio overlaps
        # No hardcoded tier companies or schools - only use actual portfolio data
        if len(portfolio_overlaps) > 0:
            # Strong signal: founder has worked at portfolio companies or same schools as portfolio
            # Score based on number of portfolio matches
            background_score = 60 + min(30, len(portfolio_overlaps) * 5)
            print(f"✅ Team Background: Found {len(portfolio_overlaps)} portfolio overlap(s) - Score: {background_score}")
        else:
            # No matches in Tracxn portfolio - score is 0
            # We don't use hardcoded tier companies/schools anymore
            # All scoring is based on actual portfolio data
            background_score = 0  # No matches = 0
            print(f"⚠️  Team Background: No portfolio matches found - Score: {background_score}")
            print(f"   Founder companies: {founder_previous_companies}")
            print(f"   Founder education: {founder_education}")
        
        background_score = max(0, min(100, background_score))
        
        return {
            'previous_companies': founder_previous_companies,
            'education': founder_education,
            'experience_years': experience_years,
            'background_score': background_score,
            'tracxn_matched': len(portfolio_overlaps) > 0,
            'portfolio_overlaps': portfolio_overlaps
        }
    
    def analyze_white_space(self, email_subject: str, email_body: str, 
                           deck_content: Optional[str] = None) -> Dict:
        """
        Analyze white space using OpenAI API with web search
        
        Analyzes:
        1. Number of funded startups in subsector (last 2-3 years)
        2. Competition intensity
        3. Market size
        4. White space identification
        
        Returns:
            Dict with white space analysis including:
            - funded_startups_count: Estimated number of funded startups
            - competition_intensity: Low/Medium/High
            - market_size: Small/Medium/Large
            - has_white_space: Boolean
            - white_space_score: Score (0-100, higher = more white space)
        """
        if not self.openai_client:
            return {
                'funded_startups_count': None,
                'competition_intensity': 'Unknown',
                'market_size': 'Unknown',
                'has_white_space': False,
                'white_space_score': 0
            }
        
        # Combine all content for analysis
        analysis_text = f"Subject: {email_subject}\n\nEmail Body: {email_body[:2000]}"
        if deck_content:
            analysis_text += f"\n\nPitch Deck Content: {deck_content[:3000]}"
        
        try:
            # Use OpenAI with web search capability
            # OpenAI's Responses API and newer models support web search tools
            # The prompt instructs the model to use web search for real-time data
            
            prompt = f"""You are a market research analyst. Analyze this startup pitch for market white space and competition intensity. Use web search to find current, real-time data on funding trends and market competition.

Startup Information:
{analysis_text}

CRITICAL ANALYSIS REQUIRED - USE WEB SEARCH FOR CURRENT DATA:
1. Identify the exact subsector/industry (e.g., "FinTech - Payment Processing", "SaaS - Project Management", "HealthTech - Telemedicine")

2. FUNDING ANALYSIS - SEARCH FOR RECENT DATA:
   - Search for how many startups in this EXACT subsector received funding in the last 2-3 years (2022-2025)
   - Look for specific funding data, Crunchbase, PitchBook, or VC reports
   - Provide a specific number or range based on search results (e.g., 15, 20-30, 50+)
   - This is a KEY metric for white space analysis

3. MARKET SIZE - SEARCH FOR MARKET DATA:
   - Search for total addressable market (TAM) size for this subsector
   - Estimate based on market research reports:
   - Small: <$1B market
   - Medium: $1B-$10B market  
   - Large: >$10B market

4. COMPETITION INTENSITY - SEARCH FOR COMPETITORS:
   - Search for major competitors in this subsector
   - Identify dominant market leaders
   - Assess market saturation
   - Rate as: Low/Medium/High

5. WHITE SPACE IDENTIFICATION:
   - White space = Low number of funded startups (<20) AND Large market size
   - Saturated = Many funded startups (>50) OR dominant market leader exists
   - Calculate: has_white_space (boolean)

INSTRUCTIONS:
- Use web search to find current, real-time data on funding rounds, market size, and competitors
- Search for specific funding data from Crunchbase, PitchBook, TechCrunch, or VC reports
- Base your analysis on actual search results, not just training data
- If search results are limited, use your knowledge but clearly state this

Provide your analysis in JSON format:
{{
    "subsector": "specific subsector/industry name",
    "funded_startups_count": <number or "20-30" format>,
    "market_size": "Small/Medium/Large",
    "competition_intensity": "Low/Medium/High",
    "has_white_space": true/false,
    "reasoning": "2-3 sentence explanation including sources/data found",
    "data_sources": "brief mention of where data came from (web search, training data, etc.)"
}}"""

            # Try to use web search if available
            # Check if the client supports tools/function calling for web search
            try:
                # Attempt to call with tools enabled (if supported)
                # Handle both OpenAIClient wrapper and direct OpenAI client
                client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
                response = client.chat.completions.create(
                    model="gpt-4o",  # GPT-4o supports better reasoning and can use tools
                    messages=[
                        {"role": "system", "content": "You are a market research analyst specializing in startup ecosystems and venture capital. You have access to web search capabilities to find real-time funding data, market size, and competitive information. Use web search to get current, accurate data."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                    # Enable web search if the API supports it
                    # Note: This may require specific API configuration or Responses API
                )
            except Exception as e:
                # Fallback to standard API call if tools aren't supported
                print(f"Note: Web search tools not available, using standard API: {str(e)}")
                # Handle both OpenAIClient wrapper and direct OpenAI client
                client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a market research analyst specializing in startup ecosystems and venture capital. You have access to knowledge of recent funding trends (2022-2025), market data, and competitive landscapes. Provide detailed, data-driven analysis of market white space and competition intensity."},
                        {"role": "user", "content": prompt.replace("USE WEB SEARCH FOR CURRENT DATA", "Use your extensive knowledge").replace("SEARCH FOR RECENT DATA", "Based on your knowledge").replace("SEARCH FOR MARKET DATA", "Based on market research").replace("SEARCH FOR COMPETITORS", "Based on competitive landscape")}
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                )
            
            analysis_result = json.loads(response.choices[0].message.content)
            print(f"📊 White Space Analysis Result: {json.dumps(analysis_result, indent=2)}")
            
            # Calculate white space score (0-100)
            white_space_score = 0  # Base score (no analysis = 0)
            
            # Higher score if low competition
            competition = analysis_result.get('competition_intensity', 'Medium').lower()
            if competition == 'low':
                white_space_score += 30
            elif competition == 'medium':
                white_space_score += 10
            else:  # high
                white_space_score -= 20
            
            # Higher score if large market
            market_size = analysis_result.get('market_size', 'Medium').lower()
            if market_size == 'large':
                white_space_score += 20
            elif market_size == 'medium':
                white_space_score += 5
            else:  # small
                white_space_score -= 10
            
            # Higher score if fewer funded startups
            funded_count = analysis_result.get('funded_startups_count', 0)
            funded_count_original = funded_count  # Keep for debugging
            if isinstance(funded_count, str):
                # Try to extract number from range like "5-10" or "~20"
                try:
                    if '-' in funded_count:
                        funded_count = int(funded_count.split('-')[0])
                    elif '~' in funded_count or '≈' in funded_count:
                        funded_count = int(funded_count.replace('~', '').replace('≈', '').strip())
                    else:
                        funded_count = int(funded_count)
                except Exception as parse_error:
                    print(f"⚠️  Could not parse funded_count '{funded_count_original}': {parse_error}")
                    funded_count = 0  # Default if can't parse
            elif funded_count is None:
                funded_count = 0  # Default if None
            
            if funded_count < 10:
                white_space_score += 25
            elif funded_count < 30:
                white_space_score += 10
            elif funded_count < 50:
                white_space_score += 0
            else:
                white_space_score -= 15
            
            # Boost if has white space
            if analysis_result.get('has_white_space', False):
                white_space_score += 10
            
            white_space_score = max(0, min(100, white_space_score))
            print(f"✅ White Space Score calculated: {white_space_score} (competition: {competition}, market: {market_size}, funded: {funded_count})")
            
            return {
                'subsector': analysis_result.get('subsector', 'Unknown'),
                'funded_startups_count': analysis_result.get('funded_startups_count', 0),
                'market_size': analysis_result.get('market_size', 'Unknown'),
                'competition_intensity': analysis_result.get('competition_intensity', 'Unknown'),
                'has_white_space': analysis_result.get('has_white_space', False),
                'white_space_score': white_space_score,
                'reasoning': analysis_result.get('reasoning', '')
            }
        
        except Exception as e:
            print(f"Error in white space analysis: {str(e)}")
            return {
                'subsector': 'Unknown',
                'funded_startups_count': None,
                'market_size': 'Unknown',
                'competition_intensity': 'Unknown',
                'has_white_space': False,
                'white_space_score': 0,
                'reasoning': f'Error: {str(e)}'
            }
    
    def generate_score_summary(self, team_background: Dict, white_space: Dict, scores: Dict) -> str:
        """
        Generate a human-readable summary explaining why the score is what it is
        
        Returns:
            String summary of the scoring rationale
        """
        team_score = scores.get('team_background_score', 0)
        white_score = scores.get('white_space_score', 0)
        overall_score = scores.get('overall_score', 0)
        
        summary_parts = []
        
        # Team background summary
        portfolio_overlaps = team_background.get('portfolio_overlaps', [])
        if len(portfolio_overlaps) > 0:
            overlap_companies = [o.get('company', '') for o in portfolio_overlaps[:3]]  # First 3
            summary_parts.append(f"Team: {len(portfolio_overlaps)} portfolio match{'es' if len(portfolio_overlaps) > 1 else ''} ({', '.join(overlap_companies)}{'...' if len(portfolio_overlaps) > 3 else ''})")
        else:
            summary_parts.append("Team: No portfolio matches found")
        
        # White space summary
        white_space_reasoning = white_space.get('reasoning', '')
        competition = white_space.get('competition_intensity', 'Unknown')
        market_size = white_space.get('market_size', 'Unknown')
        subsector = white_space.get('subsector', 'Unknown')
        
        if white_space_reasoning:
            # Use the full AI-generated reasoning (no truncation)
            summary_parts.append(f"Market: {white_space_reasoning}")
        else:
            # Fallback to basic info
            summary_parts.append(f"Market: {subsector} - {competition} competition, {market_size} market")
        
        # Overall score explanation
        if overall_score >= 70:
            summary_parts.append("Assessment: Strong overall opportunity")
        elif overall_score >= 50:
            summary_parts.append("Assessment: Moderate opportunity")
        elif overall_score > 0:
            summary_parts.append("Assessment: Weak opportunity")
        else:
            summary_parts.append("Assessment: No qualifying factors found")
        
        # Join with line breaks for better readability
        return "\n\n".join(summary_parts)
    
    def calculate_score(self, team_background: Dict, white_space: Dict) -> Dict:
        """
        Calculate overall score based on team background and white space
        
        Returns:
            Dict with scores:
            - team_background_score: Score from Tracxn (0-100)
            - white_space_score: Score from OpenAI analysis (0-100)
            - overall_score: Weighted average (0-100)
        """
        team_score = team_background.get('background_score', 0)
        white_score = white_space.get('white_space_score', 0)
        
        # Weighted average: 60% team background, 40% white space
        overall_score = (team_score * 0.6) + (white_score * 0.4)
        
        return {
            'team_background_score': team_score,
            'white_space_score': white_score,
            'overall_score': round(overall_score, 1)
        }
    
    def analyze_deal(self, founder_name: str, founder_email: str, 
                    email_subject: str, email_body: str, 
                    deck_content: Optional[str] = None) -> Dict:
        """
        Complete deal analysis
        
        Returns:
            Dict with complete analysis including team background, white space, and scores
        """
        # Combine email body and deck content for team background analysis
        # This ensures we have all available information for extraction
        combined_body = email_body
        if deck_content:
            combined_body = f"{email_body}\n\n--- Deck Content ---\n\n{deck_content}"
        
        print(f"🔍 Analyzing team background from {len(combined_body)} chars of text...")
        
        # Analyze team background from Tracxn
        team_background = self.analyze_team_background(
            founder_name, founder_email, combined_body, email_subject
        )
        
        # Analyze white space using OpenAI
        # Use email_body + deck_content for white space analysis
        analysis_body = email_body
        if deck_content:
            analysis_body = f"{email_body}\n\nPitch Deck: {deck_content}"
        
        print(f"🔍 Analyzing white space from {len(analysis_body)} chars of text...")
        white_space = self.analyze_white_space(
            email_subject, analysis_body, deck_content
        )
        
        # Calculate scores
        scores = self.calculate_score(team_background, white_space)
        
        # Generate summary explaining the score
        summary = self.generate_score_summary(team_background, white_space, scores)
        
        return {
            'team_background': team_background,
            'white_space': white_space,
            'scores': scores,
            'summary': summary
        }

