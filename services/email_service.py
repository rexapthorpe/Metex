"""
Email Service
Handles sending HTML emails using Gmail SMTP
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
import config
import os

# Setup Jinja2 for email templates
template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'emails')
jinja_env = Environment(loader=FileSystemLoader(template_dir))


def send_html_email(to_email, subject, template_name, **template_vars):
    """
    Send an HTML email using a Jinja2 template

    Args:
        to_email: Recipient email address
        subject: Email subject line
        template_name: Name of the template file (e.g., 'bid_filled.html')
        **template_vars: Variables to pass to the template

    Returns:
        bool: True if sent successfully, False otherwise
    """
    from_email = config.EMAIL_ADDRESS
    from_password = config.EMAIL_PASSWORD

    try:
        # Render the HTML template
        template = jinja_env.get_template(template_name)
        html_content = template.render(**template_vars)

        # Create message
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = from_email
        message['To'] = to_email

        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)

        # Send email via Gmail SMTP
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, message.as_string())
        server.close()

        print(f"[EMAIL] Sent '{subject}' to {to_email}")
        return True

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email to {to_email}: {e}")
        return False


def send_bid_filled_email(to_email, username, item_description, quantity, price_per_unit,
                          total_amount, partial=False, remaining_quantity=0, orders_url=''):
    """
    Send a "bid filled" notification email

    Args:
        to_email: Buyer's email
        username: Buyer's username
        item_description: Description of the item
        quantity: Quantity filled
        price_per_unit: Price per unit
        total_amount: Total amount for this fill
        partial: Whether this is a partial fill
        remaining_quantity: Remaining unfilled quantity (if partial)
        orders_url: URL to orders page
    """
    return send_html_email(
        to_email=to_email,
        subject='🎉 Your Bid Has Been Filled!',
        template_name='bid_filled.html',
        username=username,
        item_description=item_description,
        quantity=quantity,
        price_per_unit=price_per_unit,
        total_amount=total_amount,
        partial=partial,
        remaining_quantity=remaining_quantity,
        orders_url=orders_url
    )


def send_listing_sold_email(to_email, username, item_description, quantity, price_per_unit,
                            total_amount, shipping_address, partial=False, remaining_quantity=0,
                            sold_tab_url=''):
    """
    Send a "listing sold" notification email

    Args:
        to_email: Seller's email
        username: Seller's username
        item_description: Description of the item sold
        quantity: Quantity sold
        price_per_unit: Price per unit
        total_amount: Total sale amount
        shipping_address: Where to ship the items
        partial: Whether this is a partial sale
        remaining_quantity: Remaining quantity in listing (if partial)
        sold_tab_url: URL to sold items tab
    """
    return send_html_email(
        to_email=to_email,
        subject='💰 Your Listing Has Been Sold!',
        template_name='listing_sold.html',
        username=username,
        item_description=item_description,
        quantity=quantity,
        price_per_unit=price_per_unit,
        total_amount=total_amount,
        shipping_address=shipping_address,
        partial=partial,
        remaining_quantity=remaining_quantity,
        sold_tab_url=sold_tab_url
    )
