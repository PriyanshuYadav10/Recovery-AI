import asyncio
from app.services.demos import SCENARIOS
from app.ai.conversation_manager import ConversationManager
from app.metrics.engine import MetricsEngine
from app.ai.groq_provider import GroqProvider


async def run_all():
    metrics = MetricsEngine()
    results = {}
    for key, spec in SCENARIOS.items():
        mgr = ConversationManager(metrics=metrics, groq=GroqProvider(api_key=""), voice_mode="SIMULATED")
        turn = await mgr.start(spec["lead_id"], voice_mode="SIMULATED")
        for utt in spec["utterances"]:
            if turn.ended:
                break
            turn = await mgr.handle_utterance(utt)
        results[key] = {
            "state": mgr.sm.state.value,
            "ended": turn.ended,
            "escalated": turn.escalated,
            "payload_status": mgr.payload.status if mgr.payload else None,
            "handoff": bool(mgr.handoff_brief),
        }
    return results


if __name__ == "__main__":
    out = asyncio.run(run_all())
    for k, v in out.items():
        print(k, v)
    assert out["success"]["payload_status"] == "completed"
    assert out["messy"]["payload_status"] == "completed"
    assert out["handoff"]["handoff"] is True
    print("DEMO SCRIPT OK")
