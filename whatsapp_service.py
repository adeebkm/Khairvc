"""
WhatsApp Business Cloud API service for sending deal flow alerts
Uses Meta's free WhatsApp Business Cloud API
"""
import os
import requests
import json
from typing import Optional, Dict
from datetime import datetime

class WhatsAppService:
    """Service for sending WhatsApp messages via Meta Business Cloud API"""
    
    def __init__(self):
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.access_token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.api_version = os.getenv('WHATSAPP_API_VERSION', 'v23.0')  # Updated to v23.0
        self.template_name = os.getenv('WHATSAPP_TEMPLATE_NAME', 'deal_flow_alert')  # Updated to deal_flow_alert
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        
        if not self.phone_number_id or not self.access_token:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN must be set")
    
    def send_message(self, to_number: str, message: str) -> Dict:
        """
        Send a WhatsApp message
        
        Args:
            to_number: Recipient WhatsApp number (format: +1234567890)
            message: Message text to send
            
        Returns:
            dict: API response
        """
        # Remove any spaces or dashes from phone number
        to_number = to_number.replace(' ', '').replace('-', '')
        
        # Ensure it starts with +
        if not to_number.startswith('+'):
            to_number = '+' + to_number
        
        url = f"{self.base_url}/messages"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'messaging_product': 'whatsapp',
            'to': to_number,
            'type': 'text',
            'text': {
                'body': message
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"WhatsApp API error: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {json.dumps(error_detail)}"
                    
                    # Check for token expiration
                    if e.response.status_code == 401:
                        error_data = error_detail.get('error', {})
                        if 'expired' in str(error_data).lower() or error_data.get('code') == 190:
                            error_msg = f"WhatsApp access token has EXPIRED. Please get a new token from Meta Developer Console and update WHATSAPP_ACCESS_TOKEN in Railway.\n\nSteps:\n1. Go to https://developers.facebook.com/apps/\n2. Select your app → WhatsApp → API Setup\n3. Generate a new access token\n4. Update WHATSAPP_ACCESS_TOKEN in Railway web service environment variables\n\nOriginal error: {error_msg}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            raise Exception(error_msg)
    
    def send_deal_alert(self, deal, user_whatsapp_number: str) -> Dict:
        """
        Send initial deal flow alert using WhatsApp template message
        
        Args:
            deal: Deal object
            user_whatsapp_number: User's WhatsApp number
            
        Returns:
            dict: API response
        """
        # Clean up phone number
        to_number = user_whatsapp_number.replace(' ', '').replace('-', '')
        if not to_number.startswith('+'):
            to_number = '+' + to_number
        
        url = f"{self.base_url}/messages"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Prepare deal information
        subject = deal.subject or 'No subject'
        sender = deal.founder_email or 'Unknown'
        founder_name = deal.founder_name or 'Unknown'
        
        # Get snippet from classification if available
        snippet = ''
        if deal.classification:
            snippet = deal.classification.snippet or ''
            # Limit snippet to 200 chars for WhatsApp
            if len(snippet) > 200:
                snippet = snippet[:197] + '...'
        
        deck_link = deal.deck_link or 'No deck'
        # Truncate deck link if too long
        if len(deck_link) > 50:
            deck_link = deck_link[:47] + '...'
        
        deal_state = deal.state or 'New'
        
        # Build template payload
        # If using custom template, include parameters
        if self.template_name != 'hello_world':
            # Check how many variables the template expects by trying different formats
            # First, try 3-variable format (subject, sender, details)
            # If that fails, fall back to 6-variable format
            
            # Combine details into one field to reduce variable count
            details_parts = []
            if founder_name and founder_name != 'Unknown':
                details_parts.append(f"Founder: {founder_name}")
            if snippet:
                details_parts.append(snippet[:150])  # Limit snippet for combined field
            if deck_link and deck_link != 'No deck':
                details_parts.append(f"Deck: {deck_link[:40]}")
            if deal_state:
                details_parts.append(f"State: {deal_state}")
            
            # Join details with periods/spaces instead of newlines (WhatsApp doesn't allow newlines in parameters)
            details_text = ". ".join(details_parts) if details_parts else "No additional details"
            # Remove any remaining newlines or tabs
            details_text = details_text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
            # Limit total details to 300 chars
            if len(details_text) > 300:
                details_text = details_text[:297] + "..."
            
            # Try 3-variable format first (most common)
            # Template variables: {{subject}}, {{sender}}, {{details}}
            # Note: Template uses language 'en' not 'en_US' for deal_flow_alert
            # IMPORTANT: For NAMED parameter format, must include 'parameter_name' field
            payload = {
                'messaging_product': 'whatsapp',
                'to': to_number,
                'type': 'template',
                'template': {
                    'name': self.template_name,
                    'language': {
                        'code': 'en'  # Changed from 'en_US' to 'en' for deal_flow_alert template
                    },
                    'components': [
                        {
                            'type': 'body',
                            'parameters': [
                                {'type': 'text', 'parameter_name': 'subject', 'text': subject[:50]},  # {{subject}}
                                {'type': 'text', 'parameter_name': 'sender', 'text': sender[:50]},   # {{sender}}
                                {'type': 'text', 'parameter_name': 'details', 'text': details_text[:300]}  # {{details}}
                            ]
                        }
                    ]
                }
            }
        else:
            # Fallback to hello_world template (no parameters)
            payload = {
                'messaging_product': 'whatsapp',
                'to': to_number,
                'type': 'template',
                'template': {
                    'name': 'hello_world',
                    'language': {
                        'code': 'en_US'
                    }
                }
            }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            # Log deal info for reference
            template_used = self.template_name if self.template_name != 'hello_world' else 'hello_world (fallback)'
            print(f"📱 Sent WhatsApp template ({template_used}) for: {subject}")
            print(f"   Founder: {founder_name}")
            print(f"   Deck: {'Yes' if deal.has_deck else 'No'}")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"WhatsApp API error: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {json.dumps(error_detail)}"
                    
                    error_data = error_detail.get('error', {})
                    error_code = error_data.get('code')
                    error_message = error_data.get('message', '')
                    
                    # Check for specific error codes
                    if e.response.status_code == 401:
                        if 'expired' in str(error_data).lower() or error_code == 190:
                            error_msg = f"WhatsApp access token has EXPIRED. Please get a new token from Meta Developer Console and update WHATSAPP_ACCESS_TOKEN in Railway.\n\nSteps:\n1. Go to https://developers.facebook.com/apps/\n2. Select your app → WhatsApp → API Setup\n3. Generate a new access token\n4. Update WHATSAPP_ACCESS_TOKEN in Railway web service environment variables\n\nOriginal error: {error_msg}"
                    elif error_code == 100 and 'Parameter name is missing or empty' in error_message:
                        # This error occurs with MARKETING templates using NAMED parameters
                        error_msg = f"WhatsApp template error: MARKETING templates with NAMED parameters may have API limitations.\n\nSOLUTION: Recreate the template as UTILITY category with positional parameters ({{1}}, {{2}}, {{3}}) instead of named parameters ({{subject}}, {{sender}}, {{details}}).\n\nTemplate should be:\n- Category: UTILITY (not MARKETING)\n- Parameters: {{1}}, {{2}}, {{3}} (positional, not named)\n- Language: en\n\nOriginal error: {error_msg}"
                    elif error_code == 132001:
                        # Template not found
                        error_msg = f"WhatsApp template '{self.template_name}' not found. Please verify:\n1. Template name is correct\n2. Template is APPROVED (not pending)\n3. Language code matches (use 'en' not 'en_US')\n4. Template is associated with the correct WABA\n\nOriginal error: {error_msg}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            raise Exception(error_msg)
    
    def send_followup(self, deal, user_whatsapp_number: str, followup_count: int) -> Dict:
        """
        Send follow-up reminder
        
        Args:
            deal: Deal object
            user_whatsapp_number: User's WhatsApp number
            followup_count: Number of follow-ups sent so far
            
        Returns:
            dict: API response
        """
        # Format updated time
        if deal.updated_at:
            updated_str = deal.updated_at.strftime('%Y-%m-%d %H:%M')
        else:
            updated_str = "Never"
        
        message = f"""⏰ *Deal Flow Follow-up #{followup_count}*

*Deal:* {deal.subject or 'No subject'}
*Founder:* {deal.founder_name or 'Unknown'}
*State:* {deal.state}

*Last updated:* {updated_str}

This is a reminder to review and respond to this deal flow.

Reply STOP to stop follow-ups."""
        
        return self.send_message(user_whatsapp_number, message)
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify webhook for incoming messages (Meta requires this)
        
        Args:
            mode: Verification mode from Meta
            token: Verification token (should match WHATSAPP_VERIFY_TOKEN)
            challenge: Challenge string from Meta
            
        Returns:
            str: Challenge string if verification succeeds, None otherwise
        """
        verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN')
        
        if mode == 'subscribe' and token == verify_token:
            return challenge
        return None
    
    def handle_incoming_message(self, webhook_data: Dict) -> Dict:
        """
        Handle incoming WhatsApp messages (e.g., STOP command)
        
        Args:
            webhook_data: Webhook payload from Meta
            
        Returns:
            dict: Processing result
        """
        try:
            entry = webhook_data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            messages = value.get('messages', [])
            
            if not messages:
                return {'status': 'no_messages'}
            
            message = messages[0]
            from_number = message.get('from', '')
            message_text = message.get('text', {}).get('body', '').strip().upper()
            
            # Handle STOP command
            if message_text == 'STOP':
                # Find user by WhatsApp number and disable follow-ups for their deals
                from models import User, Deal, db
                user = User.query.filter_by(whatsapp_number=from_number).first()
                
                if user:
                    # Stop follow-ups for all user's deals
                    deals = Deal.query.filter_by(user_id=user.id).all()
                    for deal in deals:
                        deal.whatsapp_stopped = True
                    db.session.commit()
                    
                    # Send confirmation
                    self.send_message(from_number, "✅ You have unsubscribed from deal flow follow-ups. Reply START to re-enable.")
                    return {'status': 'stopped', 'user_id': user.id}
            
            # Handle START command
            elif message_text == 'START':
                from models import User, Deal, db
                user = User.query.filter_by(whatsapp_number=from_number).first()
                
                if user:
                    deals = Deal.query.filter_by(user_id=user.id).all()
                    for deal in deals:
                        deal.whatsapp_stopped = False
                    db.session.commit()
                    
                    self.send_message(from_number, "✅ You have re-enabled deal flow follow-ups.")
                    return {'status': 'started', 'user_id': user.id}
            
            return {'status': 'processed', 'message': message_text}
            
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

