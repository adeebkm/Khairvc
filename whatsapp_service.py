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
        self.api_version = os.getenv('WHATSAPP_API_VERSION', 'v21.0')
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
        Send initial deal flow alert
        
        Args:
            deal: Deal object
            user_whatsapp_number: User's WhatsApp number
            
        Returns:
            dict: API response
        """
        # Format the message
        deck_status = "✅ Yes" if deal.has_deck else "❌ No"
        team_status = "✅ Yes" if deal.has_team_info else "❌ No"
        traction_status = "✅ Yes" if deal.has_traction else "❌ No"
        round_status = "✅ Yes" if deal.has_round_info else "❌ No"
        
        deck_link_text = deal.deck_link if deal.deck_link else "No deck attached"
        if len(deck_link_text) > 50:
            deck_link_text = deck_link_text[:47] + "..."
        
        message = f"""🚀 *NEW DEAL FLOW ALERT*

*Founder:* {deal.founder_name or 'Unknown'}
*Email:* {deal.founder_email or 'Unknown'}
*Subject:* {deal.subject or 'No subject'}

*Deck:* {deck_link_text}

*Four Basics:*
• Deck: {deck_status}
• Team Info: {team_status}
• Traction: {traction_status}
• Round Info: {round_status}

*State:* {deal.state}

Reply STOP to stop follow-ups."""
        
        return self.send_message(user_whatsapp_number, message)
    
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

