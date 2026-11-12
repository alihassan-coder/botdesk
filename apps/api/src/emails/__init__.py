"""The emails BotDesk sends. Each function returns `(subject, html, text)`."""

from src.emails.templates import Email, invitation_email, password_reset_email

__all__ = ["Email", "invitation_email", "password_reset_email"]
