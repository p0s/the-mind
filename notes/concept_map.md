# Concept Map

This file is a lightweight dependency + disambiguation graph for the project.
It is intentionally terse: it exists to prevent drift and conflation across chapters.

Format conventions:
- `A -> B` means: understanding A is a prerequisite for cleanly stating B.
- `A ~ B` means: closely related (often co-appearing), but not identical.
- `A != B` means: do not conflate (explicitly document the distinction in prose).

## Dependency Spine (minimum chain)

Computationalist functionalism -> Model -> Representation -> World-model -> Agent -> Control -> Learning -> Valence -> Self-model -> Attention -> Consciousness -> Social minds

## Core Nodes (definitions live in notes/glossary.md)

### Modeling & Representation
- Computationalist functionalism -> Object (as functional role)
- Strong computationalism ~ Church-Turing (boundary condition for realizable representational languages)
- Representation -> World-model
- Representation -> Self-model
- World-model ~ Simulator
- Abstraction ~ Compression (abstraction as compressed structure for control)
- Invariance -> Object (objects track invariances at a chosen level of description)
- World-model != Territory (model vs reality)
- Model != Data (model as structure that supports prediction/control)

### Agency & Control
- Agent -> Control
- Control -> Policy
- Control -> Goal/Value representation
- Control -> Error signals (as information about deviation)
- Goal -> Error signal (goals/constraints induce error variables for control)
- Governance -> Policy arbitration (meta-control over which policies/loops dominate)
- Agent ~ Controller
- Agent != Organism (the organism implements an agent; not identical as an abstraction)

### Learning & Compression
- Learning -> Model update
- Learning -> Policy update
- Learning ~ Compression (learning as structure discovery that reduces description length / increases predictive power)
- Understanding ~ Compression + usability for control
- Credit assignment -> Learning (how outcomes reinforce the right internal structure)
- Learning != Memorization (memorization can be a component; not the same function)
- Self-organization ~ Learning (self-organization is structure formation; learning is a family of update rules within it)
- Self-organization -> Consciousness (in the "early learning scaffold" framing)

### Valence, Value, Emotion
- Valence -> Credit assignment / reinforcement of policy
- Value ~ Preference structure
- Valence != Pleasure (phenomenology can correlate; not identical)
- Value != Reward (reward as signal; value as learned structure in the model)
- Norm ~ Commitment (constraints beyond immediate valence; coordination-relevant)
- Emotion -> Control modulation (a family of control signals; not a single thing)
- Habit ~ Policy (habits as stabilized low-friction policies)

### Attention & Workspace
- Attention -> Selection (what gets amplified/kept)
- Attention -> Working memory
- Working memory -> Global/broadcast mechanisms (if used)
- Attention != Consciousness (often correlated; not identical)
- Attention != Salience (salience is one driver of attention; not the whole mechanism)

### Self, Narrative, Identity
- Self-model -> First-person perspective
- Self-model -> Narrative control (temporal coherence, justification, planning)
- Self-model != Self (the "self" as experienced is a representation; not an entity behind the representation)
- Narrative != Truth (narratives are control/communication artifacts; not truth guarantees)

### Consciousness (triangulation discipline)
- Consciousness -> Phenomenology (what it is like)
- Consciousness -> Function (what it does in the system)
- Consciousness -> Mechanism (how it can be implemented)
- Phenomenology != Mechanism != Function (never collapse the three)
- Consciousness ~ Interface/Broadcast (candidate functional roles; avoid premature identity claims)
- Consciousness -> Nowness (modeled present / coherence bubble)
- First-person perspective ~ Consciousness (often co-occurring) but != (not strictly required)
- Attention schema ~ Global workspace (two convergent framings; neither should be treated as a final identity claim)
- Consciousness -> Suffering (as a control/valence phenomenon; avoid moralizing)
- Consciousness -> Enlightenment (as a representational reconfiguration of self-modeling)
- Machine consciousness hypothesis -> Self-organization (two-part conjecture about biological + artificial conditions)

### Multi-agent / Culture
- Social modeling -> Theory of mind
- Language -> Shared compression / coordination medium
- Culture -> Multi-agent control (norms, institutions, contracts)
- Alignment -> Value learning + governance (as a downstream application; not the core)

## High-risk Conflations (must be disambiguated in text)

- Consciousness != Intelligence
- Consciousness != Attention
- Understanding != Prediction accuracy (prediction is part; "understanding" includes usable abstraction)
- Value != Utility function (utility is a formal abstraction; value is a learned control structure)
- Agent != Optimizer (optimization can be local/approximate/learned; avoid over-idealization)
