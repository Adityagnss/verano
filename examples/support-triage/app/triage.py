"""A small support-desk helper: routes each ticket to a team and drafts a reply."""

from openai import OpenAI

client = OpenAI()

TRIAGE_PROMPT = """You are a support triage assistant for an online shop.
Read the customer's ticket and reply with exactly one word: billing, shipping or technical.

billing   - charges, refunds, invoices, payment problems
shipping  - delivery, tracking, lost or damaged parcels
technical - the website or app not working, login problems, bugs"""


def classify_ticket(ticket: str) -> str:
    """Which team should handle this ticket?"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=5,
        messages=[
            {"role": "system", "content": TRIAGE_PROMPT},
            {"role": "user", "content": f"Ticket: {ticket}"},
        ],
    )
    return response.choices[0].message.content.strip().lower()


def draft_reply(ticket: str, tone: str) -> str:
    """A first reply for the agent to edit. Two inputs: the ticket and the tone."""
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.7,
        messages=[
            {"role": "system", "content": "You write short, kind first replies to customer support tickets."},
            {"role": "user", "content": f"Write a {tone} reply to this ticket:\n{ticket}"},
        ],
    )
    return response.choices[0].message.content
