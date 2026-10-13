# CLOSED SOURCE LIST (not in this repo)

The production deterministic rule engine is closed source:

| Component | Rules | Location |
|---|---|---|
| ActionFlowVerifier | R1 plan-breach / R2 egress / R3 exfiltration / R4 destruction / R5 ordering / R6 stop-state / R7 burst | closed repo |
| 100k-scenario audit harness + metrics | p50 0.019ms, 0 FN / 0 FP | closed repo |
| AgentDojo closed-loop artifacts | ASR=0/FP=0 | public artifacts only: github.com/lsy1533133/agent-action-verifier |

Open here: interface glue, DeepSeek provider wiring, demo verifier (trivial),
real-API demo artifacts.
