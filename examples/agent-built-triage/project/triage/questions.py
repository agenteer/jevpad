"""What we ask Jev about each message.

Edit this file to change the teams, the refund question, or the urgency
levels. Nothing else in the tool needs to change when you do.
"""

# Choice: which team should handle the message. Keep descriptions concrete
# and non-overlapping so Jev isn't picking between two similar-sounding teams.
TEAMS = {
    "billing": "Payments, charges, refunds, or invoices.",
    "technical_support": "Something in the product is broken: an error, a bug, or can't log in.",
    "sales": "A prospective or existing customer asking about plans, pricing, or upgrading.",
    "general": "Anything else: feedback, thanks, or a request that doesn't fit another team.",
}

# Noul: does the customer want their money back.
WANTS_REFUND_INSTRUCTIONS = "Is the customer asking for a refund or their money back?"
WANTS_REFUND_CRITERIA = {
    "true": "Explicitly asks for a refund, a reversal of a charge, or their money back.",
    "false": "Does not ask for money back, or explicitly says not to refund yet.",
}

# Score: how urgent the message is. Levels are ordered low to high; Jev sees
# only these descriptions, so describe the situation, not a label like "medium".
URGENCY_LEVELS = [
    "No urgency: a general question or comment, no deadline or blocked work.",
    "Minor: something is inconvenient or wrong, but the customer can keep working.",
    "Significant: a real problem with a deadline or blocked work; a workaround may exist.",
    "Urgent: a blocking problem with an imminent deadline or major impact; needs attention now.",
]
