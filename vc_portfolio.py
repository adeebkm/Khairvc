"""
VC Portfolio Configuration
Fake portfolio data for testing deal flow analysis
"""
from typing import List, Dict, Optional

# Fake Portfolio Companies
PORTFOLIO_COMPANIES = [
    {
        'name': 'TechFlow Inc',
        'founder': 'John Smith',
        'founder_linkedin': 'https://linkedin.com/in/johnsmith',
        'founder_school': 'Stanford University',
        'founder_previous_companies': ['Google', 'Meta'],
        'stage_invested': 'Seed',
        'sector': 'SaaS',
        'status': 'Active'
    },
    {
        'name': 'DataVault',
        'founder': 'Sarah Chen',
        'founder_linkedin': 'https://linkedin.com/in/sarahchen',
        'founder_school': 'MIT',
        'founder_previous_companies': ['Amazon', 'Microsoft'],
        'stage_invested': 'Series A',
        'sector': 'AI/ML',
        'status': 'Active'
    },
    {
        'name': 'FinTech Solutions',
        'founder': 'Michael Rodriguez',
        'founder_linkedin': 'https://linkedin.com/in/michaelrodriguez',
        'founder_school': 'Harvard Business School',
        'founder_previous_companies': ['Goldman Sachs', 'Stripe'],
        'stage_invested': 'Seed',
        'sector': 'Fintech',
        'status': 'Active'
    },
    {
        'name': 'CloudScale',
        'founder': 'Emily Watson',
        'founder_linkedin': 'https://linkedin.com/in/emilywatson',
        'founder_school': 'UC Berkeley',
        'founder_previous_companies': ['Salesforce', 'Oracle'],
        'stage_invested': 'Series A',
        'sector': 'Infrastructure',
        'status': 'Active'
    },
    {
        'name': 'HealthTech Innovations',
        'founder': 'David Kim',
        'founder_linkedin': 'https://linkedin.com/in/davidkim',
        'founder_school': 'Stanford Medical School',
        'founder_previous_companies': ['Pfizer', 'Johnson & Johnson'],
        'stage_invested': 'Seed',
        'sector': 'Healthcare',
        'status': 'Active'
    },
]

# Firm Team Members
FIRM_TEAM = [
    {
        'name': 'Alex Johnson',
        'role': 'Partner',
        'school': 'Stanford University',
        'previous_companies': ['Google', 'Sequoia Capital'],
        'linkedin': 'https://linkedin.com/in/alexjohnson'
    },
    {
        'name': 'Maria Garcia',
        'role': 'Principal',
        'school': 'MIT',
        'previous_companies': ['Amazon', 'Andreessen Horowitz'],
        'linkedin': 'https://linkedin.com/in/mariagarcia'
    },
    {
        'name': 'Robert Lee',
        'role': 'Partner',
        'school': 'Harvard Business School',
        'previous_companies': ['Goldman Sachs', 'Accel Partners'],
        'linkedin': 'https://linkedin.com/in/robertlee'
    },
    {
        'name': 'Jennifer Park',
        'role': 'Associate',
        'school': 'UC Berkeley',
        'previous_companies': ['Microsoft', 'Bessemer Venture Partners'],
        'linkedin': 'https://linkedin.com/in/jenniferpark'
    },
]

# Limited Partners (LPs)
LIMITED_PARTNERS = [
    {
        'name': 'TechFamily Foundation',
        'type': 'Family Business',
        'description': 'Multi-generational tech family business',
        'network_level': 'High'
    },
    {
        'name': 'Wealthy Individual Network',
        'type': 'High Network Individual',
        'description': 'Group of high-net-worth individuals',
        'network_level': 'Very High'
    },
    {
        'name': 'Legacy Enterprises',
        'type': 'Family Business',
        'description': 'Age-old business with accumulated wealth',
        'network_level': 'High'
    },
]

# Investment Criteria
INVESTMENT_CRITERIA = {
    'stages': ['Seed', 'Series A'],
    'sectors': ['SaaS', 'AI/ML', 'Fintech', 'Healthcare', 'Infrastructure'],
    'pre_traction': True,  # Fund invests pre-traction
    'minimum_check_size': 500000,
    'maximum_check_size': 5000000,
    'preferred_geographies': ['US', 'Canada'],
}

# Fund Name
FUND_NAME = 'Acme Ventures'
FUND_FOCUS = 'Early-stage B2B SaaS, AI/ML, and Fintech companies'

# Elite Schools (for comparison)
ELITE_SCHOOLS = [
    'Stanford University',
    'MIT',
    'Harvard University',
    'Harvard Business School',
    'UC Berkeley',
    'Princeton University',
    'Yale University',
    'Columbia University',
    'Cornell University',
    'University of Pennsylvania',
    'Wharton School',
]


class PortfolioMatcher:
    """Match incoming deals against portfolio"""
    
    def __init__(self):
        self.portfolio_companies = PORTFOLIO_COMPANIES
        self.firm_team = FIRM_TEAM
        self.lps = LIMITED_PARTNERS
        self.elite_schools = ELITE_SCHOOLS
        self.investment_criteria = INVESTMENT_CRITERIA
    
    def find_founder_linkedin(self, founder_name: str, email: str, subject: str, body: str) -> Optional[str]:
        """
        Extract or search for founder LinkedIn
        For now, search in email body for LinkedIn URLs
        TODO: Implement actual LinkedIn search API
        """
        import re
        
        # Search for LinkedIn URLs in email
        linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        matches = re.findall(linkedin_pattern, body.lower())
        
        if matches:
            return f"https://www.{matches[0]}"
        
        # TODO: Implement LinkedIn search by name
        # This would require LinkedIn API or web scraping
        return None
    
    def check_portfolio_overlap(self, founder_name: str, founder_school: Optional[str], 
                                previous_companies: List[str]) -> Dict:
        """
        Check if founder has connections to portfolio
        Returns overlap analysis
        """
        overlaps = {
            'worked_at_portfolio_companies': [],
            'same_school_as_portfolio_founders': [],
            'same_school_as_firm_team': [],
            'worked_at_same_companies_as_team': [],
        }
        
        # Check portfolio company overlaps
        portfolio_company_names = [c['name'].lower() for c in self.portfolio_companies]
        portfolio_previous_companies = set()
        for company in self.portfolio_companies:
            portfolio_previous_companies.update([c.lower() for c in company.get('founder_previous_companies', [])])
        
        for prev_company in previous_companies:
            if prev_company.lower() in portfolio_company_names:
                overlaps['worked_at_portfolio_companies'].append(prev_company)
            if prev_company.lower() in portfolio_previous_companies:
                overlaps['worked_at_portfolio_companies'].append(prev_company)
        
        # Check school overlaps
        if founder_school:
            founder_school_lower = founder_school.lower()
            
            # Check against portfolio founders
            for company in self.portfolio_companies:
                if company.get('founder_school', '').lower() == founder_school_lower:
                    overlaps['same_school_as_portfolio_founders'].append({
                        'company': company['name'],
                        'founder': company['founder']
                    })
            
            # Check against firm team
            for member in self.firm_team:
                if member.get('school', '').lower() == founder_school_lower:
                    overlaps['same_school_as_firm_team'].append({
                        'name': member['name'],
                        'role': member['role']
                    })
        
        # Check company overlaps with firm team
        team_previous_companies = set()
        for member in self.firm_team:
            team_previous_companies.update([c.lower() for c in member.get('previous_companies', [])])
        
        for prev_company in previous_companies:
            if prev_company.lower() in team_previous_companies:
                overlaps['worked_at_same_companies_as_team'].append(prev_company)
        
        return overlaps
    
    def calculate_scores(self, founder_info: Dict, deal_info: Dict, portfolio_overlaps: Dict) -> Dict:
        """
        Calculate deal scores:
        1. Risk score
        2. Portfolio comparison score
        3. Founder quality + market score
        4. Pre/post traction score
        """
        scores = {
            'risk_score': 0.0,
            'portfolio_comparison_score': 0.0,
            'founder_market_score': 0.0,
            'traction_score': 0.0,
            'overall_score': 0.0,
        }
        
        # 1. Risk Score (0-100, lower is riskier)
        # Based on stage, traction, market validation
        stage = deal_info.get('stage', 'Seed')
        has_traction = deal_info.get('has_traction', False)
        has_round_info = deal_info.get('has_round_info', False)
        
        risk_score = 50  # Base risk
        if stage == 'Seed':
            risk_score -= 20  # Seed is riskier
        if not has_traction:
            risk_score -= 15  # Pre-traction is riskier
        if has_traction:
            risk_score += 15  # Traction reduces risk
        if has_round_info and deal_info.get('has_lead_investor'):
            risk_score += 10  # Lead investor reduces risk
        
        scores['risk_score'] = max(0, min(100, risk_score))
        
        # 2. Portfolio Comparison Score (0-100)
        # Compare founder to portfolio founders
        portfolio_score = 50  # Base
        
        # School comparison
        founder_school = founder_info.get('school')
        if founder_school:
            is_elite = any(elite.lower() in founder_school.lower() for elite in self.elite_schools)
            
            # Count elite schools in portfolio
            portfolio_elite_count = sum(1 for c in self.portfolio_companies 
                                       if any(elite.lower() in c.get('founder_school', '').lower() 
                                             for elite in self.elite_schools))
            
            if is_elite:
                portfolio_score += 15  # Elite school matches portfolio
            elif portfolio_elite_count > len(self.portfolio_companies) / 2:
                portfolio_score -= 10  # Portfolio prefers elite, founder isn't
        
        # Company overlap bonus
        if portfolio_overlaps.get('worked_at_portfolio_companies'):
            portfolio_score += 20  # Strong signal
        if portfolio_overlaps.get('same_school_as_portfolio_founders'):
            portfolio_score += 10
        if portfolio_overlaps.get('same_school_as_firm_team'):
            portfolio_score += 10
        
        scores['portfolio_comparison_score'] = max(0, min(100, portfolio_score))
        
        # 3. Founder Quality + Market Score (0-100)
        founder_score = 50  # Base
        
        # Founder experience
        previous_companies = founder_info.get('previous_companies', [])
        if len(previous_companies) > 0:
            founder_score += min(20, len(previous_companies) * 5)
        
        # Market size (from deal info - would need to extract from deck)
        market_size = deal_info.get('market_size', 'unknown')
        if market_size == 'large':
            founder_score += 15
        elif market_size == 'medium':
            founder_score += 5
        
        # White space (from deal info)
        has_white_space = deal_info.get('has_white_space', False)
        if has_white_space:
            founder_score += 10
        else:
            founder_score -= 5  # Competitive market
        
        scores['founder_market_score'] = max(0, min(100, founder_score))
        
        # 4. Traction Score (0-100)
        # Based on pre/post traction preference
        traction_score = 50  # Base
        
        if self.investment_criteria.get('pre_traction', True):
            # Fund invests pre-traction
            if not has_traction:
                traction_score += 20  # Matches fund preference
            else:
                traction_score += 10  # Traction is good but not required
        else:
            # Fund requires traction
            if has_traction:
                traction_score += 30
            else:
                traction_score -= 20
        
        scores['traction_score'] = max(0, min(100, traction_score))
        
        # Overall Score (weighted average)
        scores['overall_score'] = (
            scores['risk_score'] * 0.2 +
            scores['portfolio_comparison_score'] * 0.3 +
            scores['founder_market_score'] * 0.3 +
            scores['traction_score'] * 0.2
        )
        
        return scores
    
    def analyze_founder(self, founder_name: str, founder_email: str, 
                       email_subject: str, email_body: str) -> Dict:
        """
        Complete founder analysis including LinkedIn extraction, 
        portfolio matching, and scoring
        """
        # Extract LinkedIn
        linkedin_url = self.find_founder_linkedin(founder_name, founder_email, email_subject, email_body)
        
        # TODO: Parse LinkedIn to extract:
        # - School
        # - Previous companies
        # - Experience
        # For now, use placeholder data
        founder_info = {
            'name': founder_name,
            'email': founder_email,
            'linkedin': linkedin_url,
            'school': None,  # Would extract from LinkedIn
            'previous_companies': [],  # Would extract from LinkedIn
        }
        
        # Extract from email body if mentioned
        import re
        body_lower = email_body.lower()
        
        # Check for school mentions
        for school in self.elite_schools:
            if school.lower() in body_lower:
                founder_info['school'] = school
                break
        
        # Check for company mentions
        common_companies = ['Google', 'Meta', 'Amazon', 'Microsoft', 'Apple', 
                          'Stripe', 'Goldman Sachs', 'Salesforce', 'Oracle']
        for company in common_companies:
            if company.lower() in body_lower:
                founder_info['previous_companies'].append(company)
        
        return founder_info


