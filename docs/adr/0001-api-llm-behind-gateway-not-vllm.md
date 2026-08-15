# ADR-0001: Use provider APIs behind a gateway instead of self-hosting with vLLM

Status: accepted

## Context

The reference architecture we started from includes a model-serving layer
(vLLM / SGLang). vLLM is an inference engine for serving open-weight models
(Llama, Qwen, Mistral) on your own GPUs, exposing an OpenAI-compatible
endpoint. This project uses frontier models (Claude) via provider APIs, so
model serving happens on the provider's side — there is nothing for vLLM to
do in that path.

## Decision

Call provider APIs through an AI gateway (LiteLLM). No self-hosted model
serving in this repo.

## Consequences

- One fewer GPU-dependent component; the whole stack runs on a laptop.
- The gateway keeps the app provider-agnostic: adding a vLLM backend later is
  a config change in the gateway, not a code change in the agent.

## When we would add vLLM

- Data-residency or privacy requirements that forbid sending data to a
  provider API.
- Cost at scale: sustained high token volume on a task a fine-tuned 7–14B
  open model handles well.
- Latency-critical paths where a small local model beats a network round-trip.

In that case vLLM plugs in as another `model_list` entry in
`gateway/litellm-config.yaml` (LiteLLM routes to any OpenAI-compatible
endpoint), and routing/fallback policy lives at the gateway — the agent code
does not change.
