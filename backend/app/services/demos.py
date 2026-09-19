from __future__ import annotations

"""Prepared judge demo scenarios - deterministic utterances."""

SCENARIOS = {
    "success": {
        "name": "Successful Recovery",
        "lead_id": "EN-1001",
        "description": "Customer cooperates; Energy journey completes.",
        "utterances": [
            "Yes, that's fine.",
            "Origin Energy",
            "Both electricity and gas",
            "No solar",
            "Two people",
            "Medium usage",
            "Yes, that looks right.",
        ],
    },
    "messy": {
        "name": "Messy Human",
        "lead_id": "EN-1002",
        "description": "Interruptions, busy, correction, then continues.",
        "utterances": [
            "Sure, go ahead.",
            "Wait, before that.",
            "I'm actually at work.",
            "Okay, let's continue quickly - apartment.",
            "Actually I meant house, not apartment.",
            "I rent it",
            "AGL",
            "Just electricity",
            "No I don't have solar",
            "Three",
            "High",
            "Yes confirm",
        ],
    },
    "dnc": {
        "name": "DNC Blocked Before Dial",
        "lead_id": "EN-1004",
        "description": "Lead sits on the Do-Not-Call register; the dial never happens.",
        "utterances": [],
    },
    "handoff": {
        "name": "Frustrated Customer to Warm Handoff",
        "lead_id": "EN-1003",
        "description": "Frustration + explicit human request; handoff brief.",
        "utterances": [
            "Yeah okay.",
            "I own it",
            "I've already told you this twice. Just give me a person.",
        ],
    },
}
