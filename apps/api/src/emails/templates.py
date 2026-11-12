"""Email templates: plain HTML with inline CSS (what email clients render), plus a text version.

One layout for every email: the "botdesk" wordmark as text (no images to block), one short
paragraph, one button, the link again as text, and a line for people who didn't ask for it.
Anything a person typed (names, organization names) is escaped before it goes into HTML.
"""

from html import escape

type Email = tuple[str, str, str]  # (subject, html, text)

INK = "#0E0E14"
ACCENT = "#3B30FF"
MUTED = "#5B5B6B"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
IGNORE_LINE = "If you didn't ask for this, ignore this email."


def _layout(*, paragraph_html: str, button: str, url: str) -> str:
    link = escape(url, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F6F6F8;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F6F6F8;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#FFFFFF;border-radius:12px;padding:32px;font-family:{FONT};color:{INK};">
        <tr><td style="font-size:22px;font-weight:800;letter-spacing:-0.5px;color:{INK};padding-bottom:24px;">botdesk</td></tr>
        <tr><td style="font-size:16px;line-height:24px;color:{INK};padding-bottom:24px;">{paragraph_html}</td></tr>
        <tr><td style="padding-bottom:24px;">
          <a href="{link}" style="display:inline-block;background:{ACCENT};color:#FFFFFF;font-size:15px;font-weight:600;text-decoration:none;padding:12px 20px;border-radius:8px;">{escape(button)}</a>
        </td></tr>
        <tr><td style="font-size:13px;line-height:20px;color:{MUTED};padding-bottom:16px;">Or open this link:<br><a href="{link}" style="color:{ACCENT};word-break:break-all;">{link}</a></td></tr>
        <tr><td style="font-size:13px;line-height:20px;color:{MUTED};">{IGNORE_LINE}</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _text(*, paragraph: str, button: str, url: str) -> str:
    return f"botdesk\n\n{paragraph}\n\n{button}: {url}\n\n{IGNORE_LINE}\n"


def _one_line(subject: str) -> str:
    """Names go into the subject; a line break there must not start a new header."""
    return " ".join(subject.split())


def password_reset_email(*, url: str, minutes: int) -> Email:
    paragraph = (
        f"Someone asked to reset the password for your BotDesk account. The link works for {minutes} minutes, once."
    )
    button = "Reset password"
    return (
        "Reset your BotDesk password",
        _layout(paragraph_html=escape(paragraph), button=button, url=url),
        _text(paragraph=paragraph, button=button, url=url),
    )


def invitation_email(*, inviter_name: str, org_name: str, url: str) -> Email:
    paragraph = f"{inviter_name} invited you to join {org_name} on BotDesk, where your team works with AI bots."
    paragraph_html = (
        f"<strong>{escape(inviter_name)}</strong> invited you to join <strong>{escape(org_name)}</strong> "
        "on BotDesk, where your team works with AI bots."
    )
    button = "Accept invite"
    return (
        _one_line(f"{inviter_name} invited you to {org_name} on BotDesk"),
        _layout(paragraph_html=paragraph_html, button=button, url=url),
        _text(paragraph=paragraph, button=button, url=url),
    )
